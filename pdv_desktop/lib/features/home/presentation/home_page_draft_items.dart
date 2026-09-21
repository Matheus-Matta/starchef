// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// A conta que cada cartão anexado já tem — buscada no servidor.
///
/// Separado do fluxo do rascunho porque é REDE: falha, demora e pode chegar
/// fora de ordem quando quatro cartões são passados em sequência. O fluxo ao
/// lado é só decisão de tela.
mixin _DraftCommandItemsSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  // `draft` já é declarado no mixin compartilhado; aqui é só o uso.

  /// Traz para o carrinho o que a comanda JÁ TEM lançado.
  ///
  /// Sem isto, anexar a comanda 3 mostrava um carrinho vazio — e o caixa não
  /// via os R$ 45 que o garçom tinha lançado nela pelo aplicativo. O cartão só
  /// faz sentido no pedido se a conta dele vier junto.
  ///
  /// Fora do `_work` de propósito: `busy` trava a tela inteira, e o operador
  /// precisa poder continuar passando produtos enquanto a conta da mesa chega.
  /// Uma falha aqui vira recado e NÃO desfaz o vínculo: o cartão continua
  /// anexado, e o servidor recalcula tudo na materialização de qualquer jeito.
  Future<void> _carregarItensDaComanda(Map<String, dynamic> command) async {
    final id = '${command['id'] ?? ''}';
    if (id.isEmpty) return;
    try {
      final dados = await api.get(
        '/commands/$id/items/',
        accessToken: token,
      );
      // O cartão pode ter sido solto enquanto a conta dele vinha. Conferir a
      // LISTA, e não só o primeiro: com quatro anexados, o segundo a responder
      // não é o primeiro da fila.
      final aindaAnexado = draft.commands.any(
        (comanda) => '${comanda['id']}' == id,
      );
      if (!mounted || !aindaAnexado) return;
      final bruto = dados['items'];
      setState(() {
        draft.setCommandItems(
          id,
          bruto is List
              ? bruto
                    .whereType<Map>()
                    .map((item) => Map<String, dynamic>.from(item))
                    .toList()
              : const [],
        );
      });
    } catch (erro) {
      if (mounted) {
        _error(
          erro,
          title: 'Não foi possível ler o que a comanda já tem',
        );
      }
    }
  }
}
