// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// A tela de pagamento: resumo à esquerda, teclado à direita.
///
/// Separada da lógica de recebimento (`_PaymentSection`) porque são coisas de
/// ritmo diferente: uma muda quando a regra do caixa muda, a outra quando o
/// desenho muda. O código foi MOVIDO, não reescrito.
mixin _PaymentView on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get selectedCustomer;
  List<Map<String, dynamic>> get paymentMethods;
  List<Map<String, dynamic>> get registeredPayments;
  List<Map<String, dynamic>> get stagedPayments;
  String? get selectedPaymentMethod;
  set selectedPaymentMethod(String? value);
  String? get removingPaymentId;
  TextEditingController get paymentAmount;
  TextEditingController get paymentReference;
  double get paidTotal;
  double get remainingTotal;
  double get changeTotal;
  double get receivedTotal;
  double get pendingChange;
  double get paymentValue;
  String get flowStep;
  set flowStep(String value);
  Map<String, dynamic>? get selectedMethod;
  Widget _couponControl(BuildContext context);
  Widget _ajustesControl(BuildContext context);
  Widget _couponSummaryRow();
  bool get _calculandoTotal;
  Widget _documentoSummaryRow();
  void _goBack();
  void _pressPaymentKey(String key);
  void _typePaymentAmount(String raw);
  Future<void> _addSplitPayment();
  Future<void> _removePayment(Map<String, dynamic> payment);
  Future<void> _completePaidOrder();

  Widget _paymentPage() {
    final selected = selectedPaymentMethod == null || paymentMethods.isEmpty
        ? null
        : paymentMethods.firstWhere(
            (item) => '${item['id']}' == selectedPaymentMethod,
          );
    final needsReference = selected?['requires_reference'] == true;
    return LayoutBuilder(
      builder: (context, constraints) {
        // A janela do PDV pode chegar a 960 px. Com a navegação lateral
        // aberta, reservar 430 px fixos para o teclado deixava o resumo com
        // pouco mais de 200 px. O teclado continua confortável, mas agora
        // cede espaço ao resumo nas larguras menores suportadas.
        final compact = constraints.maxWidth < 980;
        // Recuos curtos: na tela de 1080 px o espaço que sobrava em volta dos
        // dois cartões era o que faltava para o teclado e os ajustes.
        final horizontalPadding = compact ? 6.0 : 8.0;
        final keypadWidth = (constraints.maxWidth * .42)
            .clamp(340.0, 430.0)
            .toDouble();
        return Padding(
          padding: EdgeInsets.all(horizontalPadding),
          child: Row(
            children: [
              Expanded(
                child: ShadCard(
                  radius: AppTheme.radius,
                  shadows: const [],
                  child: Padding(
                    // O TITULO E O BOTAO DE VOLTAR SAIRAM DAQUI.
                    //
                    // 'Pagamento', o numero do pedido e um 'Voltar ao pedido'
                    // com rotulo ocupavam a primeira faixa do resumo dizendo o
                    // que a barra do aplicativo, logo acima, ja diz — e a
                    // barra tem uma seta de voltar desde sempre.
                    padding: const EdgeInsets.all(8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Abre o cupom antes do resumo; o abatimento fica nele.
                        _couponControl(context),
                        const SizedBox(height: 8),
                        // QUEM LANCOU, com o codigo quando houver: "Maria - 4821".
                        //
                        // O caixa confere a conta de um atendimento que nao foi
                        // dele. Num aparelho compartilhado no salao o login e
                        // sempre o mesmo, e o codigo e a unica coisa aqui que
                        // diz quem de fato atendeu aquela mesa.
                        if ('${activeOrder!['operator_label'] ?? ''}'
                            .isNotEmpty)
                          _paymentSummaryRow(
                            'Operador',
                            '${activeOrder!['operator_label']}',
                          ),
                        _paymentSummaryRow(
                          'Subtotal',
                          _money(activeOrder!['subtotal']),
                        ),
                        // Taxa, desconto e documento aparecem AQUI quando
                        // aplicados — é o que confirma o gesto feito nos
                        // campos da direita, abaixo do teclado.
                        if (_number(activeOrder!['service_fee']) > .009)
                          _paymentSummaryRow(
                            'Taxa de serviço',
                            _money(activeOrder!['service_fee']),
                          )
                        else if (activeOrder!['service_fee_enabled'] == false)
                          _paymentSummaryRow('Taxa de serviço', 'não cobrada'),
                        if (_number(activeOrder!['delivery_fee']) > .009)
                          _paymentSummaryRow(
                            'Entrega',
                            _money(activeOrder!['delivery_fee']),
                          ),
                        if (_number(activeOrder!['discount']) > .009)
                          _paymentSummaryRow(
                            'Desconto',
                            '- ${_money(activeOrder!['discount'])}',
                          ),
                        // O DESCONTO DO CUPOM ENTRA ANTES DO TOTAL, junto das
                        // outras linhas que o compoem: depois dele pareceria
                        // um extra, quando e justamente uma parcela.
                        _couponSummaryRow(),
                        _documentoSummaryRow(),
                        _paymentSummaryRow(
                          'Total do pedido',
                          _money(activeOrder!['total']),
                          strong: true,
                        ),
                        _paymentSummaryRow('Valor aplicado', _money(paidTotal)),
                        _paymentSummaryRow(
                          'Total recebido',
                          _money(receivedTotal),
                        ),
                        if (changeTotal > .009)
                          Container(
                            width: double.infinity,
                            margin: const EdgeInsets.only(top: 8),
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.green.withValues(alpha: .12),
                              borderRadius: AppTheme.radius,
                              border: Border.all(
                                color: Colors.green.withValues(alpha: .45),
                              ),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'TROCO A ENTREGAR',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w800,
                                    color: Colors.green,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  _money(changeTotal),
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w900,
                                    color: Colors.green,
                                  ),
                                ),
                                const Text(
                                  'Entregue o troco e depois conclua o pedido.',
                                ),
                              ],
                            ),
                          ),
                        const Divider(height: 16),
                        _paymentSummaryRow(
                          'Restante',
                          _money(remainingTotal),
                          strong: true,
                        ),
                        const SizedBox(height: 10),
                        Text(
                          stagedPayments.isEmpty
                              ? 'Pagamentos registrados'
                              : 'Pagamentos deste recebimento',
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        if (stagedPayments.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(
                            'Serão enviados ao concluir o pedido.',
                            style: TextStyle(
                              fontSize: 10,
                              color: Theme.of(
                                context,
                              ).colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                        const SizedBox(height: 6),
                        Expanded(
                          child: registeredPayments.isEmpty
                              ? const Center(
                                  child: Text('Nenhum pagamento registrado.'),
                                )
                              : ListView.separated(
                                  itemCount: registeredPayments.length,
                                  separatorBuilder: (_, _) => const Divider(),
                                  itemBuilder: (_, index) {
                                    final payment = registeredPayments[index];
                                    final staged = payment['_staged'] == true;
                                    final change = _number(
                                      payment['change_amount'],
                                    );
                                    final detail = [
                                      if (change > .009)
                                        'Recebido: ${_money(_number(payment['amount']) + change)} · Troco: ${_money(change)}',
                                      // O selo é o que separa "montado aqui"
                                      // de "já está no servidor" — e é o que
                                      // diz por que um deles pode ser
                                      // excluído sem pedir nada a ninguém.
                                      if (staged) 'Ainda não enviado',
                                    ].join(' · ');
                                    return ListTile(
                                      contentPadding: EdgeInsets.zero,
                                      leading: CircleAvatar(
                                        child: Icon(
                                          staged ? Icons.schedule : Icons.check,
                                          size: 18,
                                        ),
                                      ),
                                      title: Text(
                                        '${payment['payment_method_name'] ?? 'Pagamento'}',
                                      ),
                                      subtitle: detail.isEmpty
                                          ? null
                                          : Text(detail),
                                      trailing: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Text(
                                            _money(payment['amount']),
                                            style: const TextStyle(
                                              fontWeight: FontWeight.w800,
                                            ),
                                          ),
                                          if (payment['id'] != null)
                                            IconButton(
                                              tooltip: 'Excluir pagamento',
                                              icon:
                                                  removingPaymentId ==
                                                      '${payment['id']}'
                                                  ? const SizedBox(
                                                      width: 18,
                                                      height: 18,
                                                      child:
                                                          CircularProgressIndicator(
                                                            strokeWidth: 2,
                                                          ),
                                                    )
                                                  : const Icon(
                                                      Icons.delete_outline,
                                                      size: 20,
                                                    ),
                                              onPressed:
                                                  removingPaymentId == null
                                                  ? () =>
                                                        _removePayment(payment)
                                                  : null,
                                            ),
                                        ],
                                      ),
                                    );
                                  },
                                ),
                        ),
                        BotaoDoPagamento(
                          calculando: _calculandoTotal,
                          onPressed: remainingTotal <= .009
                              ? _completePaidOrder
                              : null,
                          icon: Icons.check_circle,
                          label: stagedPayments.isEmpty
                              ? 'Concluir pedido'
                              : 'Concluir pedido e receber',
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              SizedBox(width: compact ? 8 : 12),
              SizedBox(
                width: keypadWidth,
                child: ShadCard(
                  radius: AppTheme.radius,
                  shadows: const [],
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: Column(
                      children: [
                        DropdownButtonFormField<String>(
                          // A chave muda com a seleção: o campo guarda o valor
                          // inicial, e sem isso ↑/↓ trocavam a forma sem a
                          // tela mostrar.
                          key: ValueKey('forma-$selectedPaymentMethod'),
                          initialValue: selectedPaymentMethod,
                          isExpanded: true,
                          isDense: true,
                          // O texto do campo, e não o `titleMedium` padrão do
                          // dropdown: mais pesado, destoava do cupom e da referência.
                          style: Theme.of(context).textTheme.bodyLarge,
                          decoration: campoDoPagamento('Forma de pagamento'),
                          items: paymentMethods
                              .map(
                                (item) => DropdownMenuItem(
                                  value: '${item['id']}',
                                  child: Text('${item['name']}'),
                                ),
                              )
                              .toList(),
                          onChanged: (value) =>
                              setState(() => selectedPaymentMethod = value),
                        ),
                        if (needsReference) ...[
                          const SizedBox(height: 8),
                          TextField(
                            controller: paymentReference,
                            decoration: campoDoPagamento(
                              'Referência da transação',
                            ),
                          ),
                        ],
                        const SizedBox(height: 10),
                        TextField(
                          controller: paymentAmount,
                          // Dá para digitar aqui, e não só clicar no teclado
                          // da tela: num caixa com teclado físico o número já
                          // está debaixo dos dedos.
                          onChanged: _typePaymentAmount,
                          keyboardType: const TextInputType.numberWithOptions(
                            decimal: true,
                          ),
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w900,
                          ),
                          decoration: const InputDecoration(
                            labelText: 'Valor do pagamento',
                            prefixText: r'R$ ',
                            contentPadding: EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 10,
                            ),
                          ),
                        ),
                        if (pendingChange > .009) ...[
                          const SizedBox(height: 8),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 9,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.green.withValues(alpha: .12),
                              borderRadius: AppTheme.radius,
                              border: Border.all(
                                color: Colors.green.withValues(alpha: .45),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text(
                                  'Troco',
                                  style: TextStyle(fontWeight: FontWeight.w800),
                                ),
                                Text(
                                  _money(pendingChange),
                                  style: const TextStyle(
                                    fontSize: 20,
                                    fontWeight: FontWeight.w900,
                                    color: Colors.green,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                        const SizedBox(height: 8),
                        Expanded(child: PaymentKeypad(onKey: _pressPaymentKey)),
                        const SizedBox(height: 8),
                        // Taxa, CPF/CNPJ e desconto: eram um modal ANTES desta
                        // tela, decididos sem ver o total.
                        _ajustesControl(context),
                        const SizedBox(height: 8),
                        // "Calculando total..." enquanto cupom, desconto,
                        // taxa ou documento estão no servidor: registrar sobre
                        // o total que ainda vai mudar cobraria o valor errado.
                        BotaoDoPagamento(
                          calculando: _calculandoTotal,
                          onPressed: paymentValue > 0 ? _addSplitPayment : null,
                          icon: Icons.add_card,
                          label: pendingChange > .009
                              ? 'Receber e registrar troco'
                              : 'Adicionar pagamento',
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _paymentSummaryRow(
    String label,
    String value, {
    bool strong = false,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: strong ? FontWeight.w800 : FontWeight.w500,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: strong ? 18 : 13,
            fontWeight: FontWeight.w900,
            color: strong ? Theme.of(context).colorScheme.primary : null,
          ),
        ),
      ],
    ),
  );
}
