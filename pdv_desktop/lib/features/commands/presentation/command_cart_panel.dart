import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../../core/theme/app_theme.dart';

/// O que a comanda tem PENDENTE — o carrinho da tela de comandas.
///
/// É o mesmo desenho do carrinho da venda, e de propósito: quem alterna entre
/// as duas telas no turno não deve reaprender onde as coisas estão. O que muda
/// são os botões.
///
/// **Não existe pagamento aqui.** A comanda é um bloco de notas: ela anota e
/// manda para a produção. Cobrar é gesto do caixa, no pedido — e um botão de
/// pagamento nesta tela convidaria o garçom a fechar a conta de uma mesa que
/// ainda está comendo.
///
/// Só o PENDENTE aparece. O que já foi cobrado continua no histórico do
/// cartão, mas mostrá-lo aqui faria a comanda reutilizada parecer cheia com a
/// conta do cliente anterior.
class CommandCartPanel extends StatelessWidget {
  const CommandCartPanel({
    super.key,
    required this.comanda,
    required this.itens,
    required this.carregando,
    required this.enviando,
    required this.imprimindo,
    required this.onSendToKitchen,
    required this.onPrintReceipt,
    required this.onVoidItem,
  });

  final Map<String, dynamic>? comanda;
  final List<Map<String, dynamic>> itens;
  final bool carregando;
  final bool enviando;
  final bool imprimindo;
  final VoidCallback onSendToKitchen;
  final VoidCallback onPrintReceipt;
  final ValueChanged<Map<String, dynamic>> onVoidItem;

  /// Há o que mandar para a produção?
  ///
  /// Só o item que ainda NÃO foi: reenviar o que a cozinha já recebeu faria o
  /// prato sair duas vezes.
  bool get _temPendenteDeCozinha =>
      itens.any((item) => '${item['status'] ?? ''}' == 'pending');

  double get _total => itens.fold(
    0,
    (soma, item) => soma + (num.tryParse('${item['total_price'] ?? 0}') ?? 0),
  );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final numero = comanda?['number'];
    return ClipRRect(
      borderRadius: AppTheme.radius,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border.all(color: scheme.outlineVariant),
          borderRadius: AppTheme.radius,
        ),
        child: Column(
          children: [
            Container(height: 3, color: scheme.primary),
            _cabecalho(context, numero),
            Divider(height: 1, color: scheme.outlineVariant),
            Expanded(child: _corpo(context)),
            Divider(height: 1, color: scheme.outlineVariant),
            _rodape(context),
          ],
        ),
      ),
    );
  }

  Widget _cabecalho(BuildContext context, Object? numero) {
    final scheme = Theme.of(context).colorScheme;
    final mesa = comanda?['current_table_number'];
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 9),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            comanda == null ? 'Nenhuma comanda' : 'Comanda $numero',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 2),
          Text(
            [
              if (comanda?['code'] != null) '${comanda?['code']}',
              if (mesa != null) 'Mesa $mesa',
              if (comanda?['customer_name'] != null &&
                  '${comanda?['customer_name']}'.isNotEmpty)
                '${comanda?['customer_name']}',
            ].join(' · '),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: scheme.onSurfaceVariant,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _corpo(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (comanda == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'Passe o cartão ou escolha uma comanda à esquerda.',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
        ),
      );
    }
    if (carregando) {
      return const Center(child: CircularProgressIndicator());
    }
    if (itens.isEmpty) {
      // Comanda livre mostra VAZIO, e não uma lista com o consumo de outra
      // pessoa. O histórico continua existindo — só não é isto que a tela do
      // atendimento pergunta.
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            'Nada lançado nesta comanda.\nToque num produto para anotar.',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 6),
      itemCount: itens.length,
      separatorBuilder: (_, _) =>
          Divider(height: 1, color: scheme.outlineVariant),
      itemBuilder: (_, indice) =>
          _Linha(item: itens[indice], onVoid: () => onVoidItem(itens[indice])),
    );
  }

  Widget _rodape(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final habilitado = comanda != null && itens.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.fromLTRB(17, 13, 17, 16),
      child: Column(
        children: [
          // Comanda SEM VALOR não mostra valor.
          //
          // "Total pendente R$ 0,00" num cartão vazio é ruído: ele ocupa a
          // linha mais visível do painel para dizer que não há nada — e o
          // operador aprende a não ler aquela linha, que é justamente a que
          // precisa ser lida quando houver conta.
          //
          // As duas pontas CEDEM: o rótulo reticencia e o número encolhe antes
          // de estourar. Um estouro aqui esconderia justamente o valor que o
          // operador lê em voz alta para o cliente.
          if (_total > 0)
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Flexible(
                  child: Text(
                    'Total pendente',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
                  ),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerRight,
                    child: Text(
                      ValueFormatters.money(_total),
                      maxLines: 1,
                      style: TextStyle(
                        color: scheme.primary,
                        fontSize: 24,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          if (_total > 0) const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            height: 46,
            child: FilledButton.icon(
              onPressed: habilitado && _temPendenteDeCozinha && !enviando
                  ? onSendToKitchen
                  : null,
              icon: enviando
                  ? const SizedBox(
                      width: 15,
                      height: 15,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.outdoor_grill_outlined, size: 18),
              label: Text(enviando ? 'Enviando…' : 'Enviar à cozinha'),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            height: 42,
            child: OutlinedButton.icon(
              onPressed: habilitado && !imprimindo ? onPrintReceipt : null,
              icon: imprimindo
                  ? const SizedBox(
                      width: 15,
                      height: 15,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.receipt_long_outlined, size: 17),
              label: Text(imprimindo ? 'Gerando…' : 'Recibo da comanda'),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'A cobrança é feita no pedido, pelo caixa.',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _Linha extends StatelessWidget {
  const _Linha({required this.item, required this.onVoid});

  final Map<String, dynamic> item;
  final VoidCallback onVoid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final naCozinha = '${item['status'] ?? ''}' != 'pending';
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 8, 8, 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 34,
            child: Text(
              '${ValueFormatters.number(item['quantity']).toStringAsFixed(0)}x',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${item['product_name'] ?? ''}'),
                if ('${item['customer_note'] ?? ''}'.isNotEmpty)
                  Text(
                    '${item['customer_note']}',
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 11,
                    ),
                  ),
                // O operador precisa ver o que JÁ foi para a produção: é o que
                // decide se cancelar custa um cupom na impressora do setor.
                if (naCozinha)
                  Text(
                    'na cozinha',
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
              ],
            ),
          ),
          Text(
            ValueFormatters.money(item['total_price']),
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          IconButton(
            onPressed: onVoid,
            icon: const Icon(Icons.close_rounded, size: 17),
            tooltip: 'Cancelar item',
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }
}
