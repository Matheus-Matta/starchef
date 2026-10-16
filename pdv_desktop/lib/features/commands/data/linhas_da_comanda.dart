import 'command_repository.dart';

/// Uma linha que a comanda da pesagem imprime para marcar à mão: um produto
/// do cardápio ou uma linha em branco, para escrever o que não está na lista.
///
/// A lista é do RESTAURANTE (`linhas_da_comanda`), não do terminal: todas as
/// balanças da casa imprimem o mesmo papel. O backend monta o texto
/// (`apps/printers/comanda_da_pesagem.py`); aqui só se edita a lista.
class LinhaDaComanda {
  const LinhaDaComanda.produto(String this.produtoId) : emBranco = false;
  const LinhaDaComanda.emBranco() : produtoId = null, emBranco = true;

  final String? produtoId;
  final bool emBranco;

  static LinhaDaComanda? fromJson(Object? json) {
    if (json is! Map) return null;
    if (json['tipo'] == 'branco') return const LinhaDaComanda.emBranco();
    final produto = '${json['produto'] ?? ''}'.trim();
    if (json['tipo'] == 'produto' && produto.isNotEmpty) {
      return LinhaDaComanda.produto(produto);
    }
    return null;
  }

  Map<String, dynamic> toJson() => emBranco
      ? const {'tipo': 'branco'}
      : {'tipo': 'produto', 'produto': produtoId};
}

/// As linhas em branco saem SEMPRE no fim do papel; a tela mostra igual.
List<LinhaDaComanda> emOrdemDeImpressao(Iterable<LinhaDaComanda> linhas) => [
  ...linhas.where((linha) => !linha.emBranco),
  ...linhas.where((linha) => linha.emBranco),
];

/// No máximo 20 linhas: o mesmo teto do backend (`MAXIMO_DE_LINHAS`).
const maximoDeLinhasDaComanda = 20;

class LinhasDaComandaRepository {
  const LinhasDaComandaRepository(this._comandas);

  final CommandRepository _comandas;

  Future<List<LinhaDaComanda>> carregar(String restaurantId) async {
    final restaurante = await _comandas.api.get(
      '/restaurants/$restaurantId/',
      accessToken: _comandas.accessToken,
    );
    final bruto = restaurante['linhas_da_comanda'];
    if (bruto is! List) return const [];
    return emOrdemDeImpressao(
      bruto.map(LinhaDaComanda.fromJson).whereType<LinhaDaComanda>(),
    );
  }

  Future<void> salvar(String restaurantId, List<LinhaDaComanda> linhas) =>
      _comandas.api.patch(
        '/restaurants/$restaurantId/',
        body: {
          'linhas_da_comanda': [
            for (final linha in emOrdemDeImpressao(linhas)) linha.toJson(),
          ],
        },
        accessToken: _comandas.accessToken,
      );
}
