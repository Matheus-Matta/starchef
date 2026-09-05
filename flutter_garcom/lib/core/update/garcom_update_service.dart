import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';

const _defaultManifestUrl =
    'https://github.com/Matheus-Matta/starchef/releases/latest/download/latest.json';

/// Mesmo `latest.json` que o PDV consulta — o publish-release do Actions
/// grava a versão/URL/SHA-256 do APK do garçom junto, numa chave própria
/// (`garcom`), porque o versionamento é independente
/// (`flutter_garcom/pubspec.yaml`) e não participa de `platforms`.
const garcomUpdateManifestUrl = String.fromEnvironment(
  'GARCOM_UPDATE_MANIFEST_URL',
  defaultValue: _defaultManifestUrl,
);

class GarcomUpdatePackage {
  const GarcomUpdatePackage({
    required this.version,
    required this.url,
    required this.sha256,
    required this.size,
  });

  final String version;
  final Uri url;
  final String sha256;
  final int size;

  factory GarcomUpdatePackage.fromJson(Map<String, dynamic> json) {
    final garcom = json['garcom'];
    if (garcom is! Map) {
      throw const FormatException(
        'Manifesto sem informação de atualização do app do garçom.',
      );
    }
    final version = '${garcom['version'] ?? ''}'.trim();
    if (version.isEmpty) {
      throw const FormatException('Versão do app do garçom ausente.');
    }
    final package = garcom['package'];
    if (package is! Map) {
      throw const FormatException('Pacote do app do garçom ausente.');
    }
    final url = Uri.tryParse('${package['url'] ?? ''}');
    if (url == null || url.scheme != 'https' || url.host.isEmpty) {
      throw const FormatException('URL do APK inválida.');
    }
    final hash = '${package['sha256'] ?? ''}'.trim().toLowerCase();
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) {
      throw const FormatException('SHA-256 do APK inválido.');
    }
    final size = package['size'];
    if (size is! int || size <= 0) {
      throw const FormatException('Tamanho do APK inválido.');
    }
    return GarcomUpdatePackage(
      version: version,
      url: url,
      sha256: hash,
      size: size,
    );
  }
}

enum GarcomUpdatePhase { checking, upToDate, updateAvailable, unavailable }

class GarcomUpdateStatus {
  const GarcomUpdateStatus({required this.phase, this.package, this.detail});

  final GarcomUpdatePhase phase;
  final GarcomUpdatePackage? package;
  final String? detail;
}

class GarcomDownloadedApk {
  const GarcomDownloadedApk({required this.package, required this.file});

  final GarcomUpdatePackage package;
  final File file;
}

/// Consulta o manifesto e baixa/valida o APK novo — o mesmo padrão de
/// integridade do atualizador do PDV (tamanho + SHA-256 antes de aceitar).
class GarcomUpdateService {
  GarcomUpdateService({
    http.Client? client,
    Uri? manifestUri,
    this.timeout = const Duration(seconds: 8),
  }) : _client = client ?? http.Client(),
       _ownsClient = client == null,
       manifestUri = manifestUri ?? Uri.parse(garcomUpdateManifestUrl);

  final http.Client _client;
  final bool _ownsClient;
  final Uri manifestUri;
  final Duration timeout;

  Future<GarcomUpdateStatus> check() async {
    try {
      final installed = await PackageInfo.fromPlatform();
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
        throw const FormatException('Manifesto não é um objeto JSON.');
      }
      final package = GarcomUpdatePackage.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      final hasUpdate =
          compareGarcomVersions(package.version, installed.version) > 0;
      return GarcomUpdateStatus(
        phase: hasUpdate
            ? GarcomUpdatePhase.updateAvailable
            : GarcomUpdatePhase.upToDate,
        package: hasUpdate ? package : null,
      );
    } catch (error) {
      return GarcomUpdateStatus(
        phase: GarcomUpdatePhase.unavailable,
        detail: '$error',
      );
    }
  }

  Future<GarcomDownloadedApk> downloadAndVerify(
    GarcomUpdatePackage package,
    Directory destination, {
    void Function(int received, int total)? onProgress,
  }) async {
    await destination.create(recursive: true);
    final finalFile = File(
      '${destination.path}${Platform.pathSeparator}'
      'starchef-garcom-${package.version}.apk',
    );
    final partialFile = File('${finalFile.path}.part');
    if (await partialFile.exists()) await partialFile.delete();

    IOSink? sink;
    try {
      final request = http.Request('GET', package.url)
        ..headers['Accept'] = 'application/octet-stream';
      final response = await _client.send(request).timeout(timeout);
      if (response.statusCode != 200) {
        throw HttpException(
          'Download respondeu HTTP ${response.statusCode}',
          uri: package.url,
        );
      }
      final announcedLength = response.contentLength;
      if (announcedLength != null && announcedLength != package.size) {
        throw const FormatException('Tamanho anunciado difere do manifesto.');
      }

      sink = partialFile.openWrite();
      var received = 0;
      // Um APK pesa dezenas de MB; o timeout aqui é por trecho recebido, não
      // do download inteiro — do contrário um Wi-Fi lento de loja nunca
      // terminaria de baixar a atualização.
      await for (final chunk in response.stream.timeout(
        const Duration(seconds: 30),
      )) {
        received += chunk.length;
        if (received > package.size) {
          throw const FormatException(
            'Download excedeu o tamanho definido no manifesto.',
          );
        }
        sink.add(chunk);
        onProgress?.call(received, package.size);
      }
      await sink.flush();
      await sink.close();
      sink = null;

      final downloadedSize = await partialFile.length();
      if (downloadedSize != package.size) {
        throw FormatException(
          'Download incompleto: $downloadedSize de ${package.size} bytes.',
        );
      }
      final digest = await sha256.bind(partialFile.openRead()).first;
      if (digest.toString().toLowerCase() != package.sha256) {
        throw const FormatException('SHA-256 do download não confere.');
      }
      if (await finalFile.exists()) await finalFile.delete();
      await partialFile.rename(finalFile.path);
      return GarcomDownloadedApk(package: package, file: finalFile);
    } catch (_) {
      await sink?.close();
      if (await partialFile.exists()) await partialFile.delete();
      rethrow;
    }
  }

  void dispose() {
    if (_ownsClient) _client.close();
  }
}

/// Compara versões `X.Y.Z` simples (sem build number nem pré-release — o
/// app do garçom não usa nenhum dos dois). Positivo quando [left] > [right].
int compareGarcomVersions(String left, String right) {
  final a = _parts(left);
  final b = _parts(right);
  for (var index = 0; index < 3; index++) {
    final comparison = a[index].compareTo(b[index]);
    if (comparison != 0) return comparison;
  }
  return 0;
}

List<int> _parts(String value) {
  final normalized = value.trim().replaceFirst(RegExp(r'^v'), '').split('+')[0];
  final match = RegExp(r'^(\d+)\.(\d+)\.(\d+)').firstMatch(normalized);
  if (match == null) return const [0, 0, 0];
  return [
    for (var index = 1; index <= 3; index++) int.parse(match.group(index)!),
  ];
}
