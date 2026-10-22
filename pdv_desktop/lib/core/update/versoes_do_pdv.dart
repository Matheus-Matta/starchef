import 'dart:convert';

import 'package:http/http.dart' as http;

import 'pdv_update_service.dart';

/// As versões do PDV publicadas, para o operador escolher uma ANTERIOR.
///
/// Um release que saiu com defeito parava a loja até a correção ser publicada:
/// o atualizador só sabe ir para a mais nova. Aqui o PDV lista os releases do
/// GitHub que têm o manifesto do desktop (`latest-desktop.json`) e instala o
/// escolhido pelo MESMO caminho da atualização — tamanho e SHA-256
/// conferidos, troca transacional e volta automática se a versão não abrir.
///
/// Só a MESMA linha da versão instalada (3.x com 3.x): a 1.8.x é outro
/// programa, offline, e instalar o ZIP dela trocaria o PDV inteiro.
class PdvVersaoDisponivel {
  const PdvVersaoDisponivel({
    required this.version,
    required this.tag,
    required this.manifestUrl,
    this.publicadaEm,
  });

  final String version;
  final String tag;
  final Uri manifestUrl;
  final DateTime? publicadaEm;
}

/// `github.com/{dono}/{repo}/releases/latest/download/{arquivo}` do manifesto.
class RepositorioDoManifesto {
  const RepositorioDoManifesto(this.owner, this.repository, this.asset);

  final String owner;
  final String repository;
  final String asset;

  /// `null` para manifesto fora do GitHub: sem API de releases a consultar.
  static RepositorioDoManifesto? de(Uri uri) {
    if (uri.host != 'github.com') return null;
    final partes = uri.pathSegments;
    if (partes.length != 6) return null;
    if (partes[2] != 'releases' ||
        partes[3] != 'latest' ||
        partes[4] != 'download') {
      return null;
    }
    return RepositorioDoManifesto(partes[0], partes[1], partes[5]);
  }
}

/// As versões que este terminal pode instalar, da mais nova para a mais
/// antiga, sem a instalada.
Future<List<PdvVersaoDisponivel>> listarVersoesDoPdv(
  http.Client client, {
  required Uri manifestUri,
  required String instalada,
  Duration timeout = const Duration(seconds: 10),
}) async {
  final origem = RepositorioDoManifesto.de(manifestUri);
  if (origem == null) {
    throw const FormatException(
      'O manifesto deste terminal não está no GitHub: não há lista de versões.',
    );
  }
  final api = Uri.https(
    'api.github.com',
    '/repos/${origem.owner}/${origem.repository}/releases',
    const {'per_page': '100'},
  );
  final resposta = await client
      .get(
        api,
        headers: const {
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
        },
      )
      .timeout(timeout);
  if (resposta.statusCode != 200) {
    throw FormatException('GitHub respondeu HTTP ${resposta.statusCode}');
  }
  final lista = jsonDecode(utf8.decode(resposta.bodyBytes));
  if (lista is! List) throw const FormatException('Lista de releases inválida');
  return versoesDaLista(lista, asset: origem.asset, instalada: instalada);
}

/// A filtragem, separada da rede para poder ser testada.
List<PdvVersaoDisponivel> versoesDaLista(
  List<dynamic> releases, {
  required String asset,
  required String instalada,
}) {
  final linha = _linha(instalada);
  final versoes = <PdvVersaoDisponivel>[];
  for (final release in releases) {
    if (release is! Map || release['draft'] == true) continue;
    final tag = '${release['tag_name'] ?? ''}';
    final version = tag.replaceFirst(RegExp(r'^v'), '');
    if (_linha(version) != linha || version == instalada) continue;
    final manifesto = _assetDoManifesto(release['assets'], asset);
    if (manifesto == null) continue;
    versoes.add(
      PdvVersaoDisponivel(
        version: version,
        tag: tag,
        manifestUrl: manifesto,
        publicadaEm: DateTime.tryParse('${release['published_at'] ?? ''}'),
      ),
    );
  }
  versoes.sort((a, b) => comparePdvVersions(b.version, a.version));
  return versoes;
}

/// A versão principal ("3" de "3.0.115"); `null` quando não é uma versão.
String? _linha(String version) {
  final match = RegExp(r'^(\d+)\.\d+\.\d+').firstMatch(version.trim());
  return match?.group(1);
}

Uri? _assetDoManifesto(Object? assets, String nome) {
  if (assets is! List) return null;
  for (final asset in assets) {
    if (asset is! Map || '${asset['name']}' != nome) continue;
    final url = Uri.tryParse('${asset['browser_download_url'] ?? ''}');
    if (url != null && url.scheme == 'https') return url;
  }
  return null;
}
