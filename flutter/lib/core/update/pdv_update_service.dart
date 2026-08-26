import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';

const _defaultManifestUrl =
    'https://github.com/Matheus-Matta/starchef/releases/latest/download/latest.json';

/// URL estável do manifesto. O Actions redefine este valor com o repositório
/// que estiver executando o build, evitando amarrar forks ao repositório-base.
const pdvUpdateManifestUrl = String.fromEnvironment(
  'PDV_UPDATE_MANIFEST_URL',
  defaultValue: _defaultManifestUrl,
);

enum PdvUpdatePhase { checking, upToDate, updateAvailable, unavailable }

class PdvInstalledVersion {
  const PdvInstalledVersion({required this.version, this.buildNumber = ''});

  final String version;
  final String buildNumber;

  String get display =>
      buildNumber.trim().isEmpty ? version : '$version+${buildNumber.trim()}';
}

class PdvReleaseArtifact {
  const PdvReleaseArtifact({
    required this.kind,
    required this.format,
    required this.name,
    required this.url,
    required this.sha256,
    required this.recommended,
  });

  final String kind;
  final String format;
  final String name;
  final Uri url;
  final String sha256;
  final bool recommended;

  factory PdvReleaseArtifact.fromJson(Map<String, dynamic> json) {
    final url = Uri.tryParse('${json['url'] ?? ''}');
    final hash = '${json['sha256'] ?? ''}'.trim().toLowerCase();
    if (url == null || !url.hasScheme || url.host.isEmpty) {
      throw const FormatException('URL de artefato inválida');
    }
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) {
      throw const FormatException('SHA-256 de artefato inválido');
    }
    return PdvReleaseArtifact(
      kind: _requiredText(json, 'kind'),
      format: _requiredText(json, 'format'),
      name: _requiredText(json, 'name'),
      url: url,
      sha256: hash,
      recommended: json['recommended'] == true,
    );
  }
}

class PdvReleaseManifest {
  const PdvReleaseManifest({
    required this.version,
    required this.tag,
    required this.releaseUrl,
    required this.platforms,
  });

  final String version;
  final String tag;
  final Uri releaseUrl;
  final Map<String, List<PdvReleaseArtifact>> platforms;

  factory PdvReleaseManifest.fromJson(Map<String, dynamic> json) {
    final schemaVersion = json['schema_version'];
    if (schemaVersion != 1) {
      throw FormatException(
        'Versão de manifesto não suportada: $schemaVersion',
      );
    }

    final version = _requiredText(json, 'version');
    // Valida cedo: um manifesto malformado nunca pode anunciar atualização.
    comparePdvVersions(version, version);
    final releaseUrl = Uri.tryParse('${json['release_url'] ?? ''}');
    if (releaseUrl == null ||
        !releaseUrl.hasScheme ||
        releaseUrl.host.isEmpty) {
      throw const FormatException('URL do release inválida');
    }

    final rawPlatforms = json['platforms'];
    if (rawPlatforms is! Map) {
      throw const FormatException('Plataformas ausentes no manifesto');
    }
    final platforms = <String, List<PdvReleaseArtifact>>{};
    for (final entry in rawPlatforms.entries) {
      final platform = '${entry.key}'.toLowerCase();
      final platformData = entry.value;
      if (platformData is! Map || platformData['packages'] is! List) {
        throw FormatException('Pacotes inválidos para $platform');
      }
      final packages = (platformData['packages'] as List)
          .map(
            (item) => PdvReleaseArtifact.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(growable: false);
      if (packages.isEmpty) {
        throw FormatException('Nenhum pacote publicado para $platform');
      }
      platforms[platform] = packages;
    }

    return PdvReleaseManifest(
      version: version,
      tag: _requiredText(json, 'tag'),
      releaseUrl: releaseUrl,
      platforms: platforms,
    );
  }

  PdvReleaseArtifact? recommendedArtifactFor(String platform) {
    final packages = platforms[platform.toLowerCase()];
    if (packages == null || packages.isEmpty) return null;
    return packages.firstWhere(
      (artifact) => artifact.recommended,
      orElse: () => packages.first,
    );
  }
}

class PdvUpdateStatus {
  const PdvUpdateStatus({
    required this.phase,
    this.installed,
    this.latestVersion,
    this.releaseUrl,
    this.artifact,
    this.detail,
  });

  const PdvUpdateStatus.checking({PdvInstalledVersion? installed})
    : this(phase: PdvUpdatePhase.checking, installed: installed);

  final PdvUpdatePhase phase;
  final PdvInstalledVersion? installed;
  final String? latestVersion;
  final Uri? releaseUrl;
  final PdvReleaseArtifact? artifact;
  final String? detail;
}

typedef PdvInstalledVersionLoader = Future<PdvInstalledVersion> Function();

class PdvUpdateService {
  PdvUpdateService({
    http.Client? client,
    Uri? manifestUri,
    String? platform,
    PdvInstalledVersionLoader? installedVersionLoader,
    this.timeout = const Duration(seconds: 8),
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null,
       manifestUri = manifestUri ?? Uri.parse(pdvUpdateManifestUrl),
       platform = platform ?? _currentPlatform(),
       _installedVersionLoader =
           installedVersionLoader ?? _loadInstalledVersion;

  final http.Client _client;
  final bool _ownsClient;
  final Uri manifestUri;
  final String platform;
  final PdvInstalledVersionLoader _installedVersionLoader;
  final Duration timeout;

  Future<PdvUpdateStatus> check({
    void Function(PdvInstalledVersion installed)? onInstalled,
  }) async {
    PdvInstalledVersion installed;
    try {
      installed = await _installedVersionLoader();
      onInstalled?.call(installed);
    } catch (error) {
      return PdvUpdateStatus(
        phase: PdvUpdatePhase.unavailable,
        detail: 'Não foi possível identificar a versão instalada: $error',
      );
    }

    try {
      final response = await _client
          .get(manifestUri, headers: const {'Accept': 'application/json'})
          .timeout(timeout);
      if (response.statusCode != 200) {
        throw HttpException(
          'GitHub respondeu HTTP ${response.statusCode}',
          uri: manifestUri,
        );
      }
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map) {
        throw const FormatException('Manifesto não é um objeto JSON');
      }
      final manifest = PdvReleaseManifest.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      final artifact = manifest.recommendedArtifactFor(platform);
      if (artifact == null) {
        throw FormatException('Release sem pacote para $platform');
      }
      final hasUpdate =
          comparePdvVersions(manifest.version, installed.version) > 0;
      return PdvUpdateStatus(
        phase: hasUpdate
            ? PdvUpdatePhase.updateAvailable
            : PdvUpdatePhase.upToDate,
        installed: installed,
        latestVersion: manifest.version,
        releaseUrl: manifest.releaseUrl,
        artifact: artifact,
      );
    } catch (error) {
      return PdvUpdateStatus(
        phase: PdvUpdatePhase.unavailable,
        installed: installed,
        detail: 'Não foi possível consultar a versão mais recente: $error',
      );
    }
  }

  void dispose() {
    if (_ownsClient) _client.close();
  }

  static Future<PdvInstalledVersion> _loadInstalledVersion() async {
    final package = await PackageInfo.fromPlatform();
    return PdvInstalledVersion(
      version: package.version,
      buildNumber: package.buildNumber,
    );
  }

  static String _currentPlatform() {
    if (Platform.isWindows) return 'windows';
    if (Platform.isLinux) return 'linux';
    return Platform.operatingSystem.toLowerCase();
  }
}

/// Compara versões semânticas usadas pelas tags `vX.Y.Z`.
/// Retorna positivo quando [left] é mais nova que [right].
int comparePdvVersions(String left, String right) {
  final a = _SemanticVersion.parse(left);
  final b = _SemanticVersion.parse(right);
  for (var index = 0; index < 3; index++) {
    final comparison = a.parts[index].compareTo(b.parts[index]);
    if (comparison != 0) return comparison;
  }
  if (a.preRelease == null && b.preRelease == null) return 0;
  if (a.preRelease == null) return 1;
  if (b.preRelease == null) return -1;

  final length = a.preRelease!.length > b.preRelease!.length
      ? a.preRelease!.length
      : b.preRelease!.length;
  for (var index = 0; index < length; index++) {
    if (index >= a.preRelease!.length) return -1;
    if (index >= b.preRelease!.length) return 1;
    final leftPart = a.preRelease![index];
    final rightPart = b.preRelease![index];
    final leftNumber = int.tryParse(leftPart);
    final rightNumber = int.tryParse(rightPart);
    if (leftNumber != null && rightNumber != null) {
      final comparison = leftNumber.compareTo(rightNumber);
      if (comparison != 0) return comparison;
    } else if (leftNumber != null) {
      return -1;
    } else if (rightNumber != null) {
      return 1;
    } else {
      final comparison = leftPart.compareTo(rightPart);
      if (comparison != 0) return comparison;
    }
  }
  return 0;
}

class _SemanticVersion {
  const _SemanticVersion(this.parts, this.preRelease);

  final List<int> parts;
  final List<String>? preRelease;

  factory _SemanticVersion.parse(String value) {
    final normalized = value
        .trim()
        .replaceFirst(RegExp(r'^v'), '')
        .split('+')[0];
    final match = RegExp(
      r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$',
    ).firstMatch(normalized);
    if (match == null) throw FormatException('Versão inválida: $value');
    return _SemanticVersion([
      for (var index = 1; index <= 3; index++) int.parse(match.group(index)!),
    ], match.group(4)?.split('.'));
  }
}

String _requiredText(Map<String, dynamic> json, String key) {
  final value = '${json[key] ?? ''}'.trim();
  if (value.isEmpty) throw FormatException('Campo obrigatório ausente: $key');
  return value;
}
