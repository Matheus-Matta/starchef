part of 'local_print_renderer.dart';

/// Comprovantes do caixa montados **no terminal**: abertura, sangria,
/// suprimento e o relatório de fechamento.
///
/// Saem pelo mesmo caminho do recibo e do DANFE — impressora master das
/// preferências, fila local — e com a mesma largura e coluna de valor de
/// [LocalPrintRenderer], para que o papel do caixa tenha a cara do papel da
/// venda. Não há equivalente no backend: o caixa é do terminal.
abstract final class CashPrintRenderer {
  static const _width = LocalPrintRenderer.receiptWidth;
  static const _rule = '------------------------------------------';
  static const _signature = '______________________________';

  /// Comprovante de abertura (suprimento inicial).
  static String opening({
    required JsonMap session,
    required JsonMap? restaurant,
    String operatorName = '',
    DateTime? now,
  }) {
    final lines = <String>[
      ..._header(restaurant, 'COMPROVANTE DE ABERTURA DE CAIXA'),
      'Data: ${_when(session['opened_at'], now)}',
      ..._sessionLines(session, operatorName),
      _rule,
      LocalPrintRenderer._amountLine(
        'Valor inserido (troco)',
        session['opening_amount'],
      ),
      'Motivo: Fundo de troco inicial',
      ..._noteLines('Obs', session['notes']),
      _rule,
      'Assinatura: $_signature',
      ..._footer(now),
    ];
    return lines.join('\n');
  }

  /// Comprovante de sangria ou suprimento.
  ///
  /// [authorizedBy] é quem liberou o movimento (gerente, ou "senha de ações
  /// do caixa" quando a autorização foi por senha, sem usuário).
  static String movement({
    required JsonMap movement,
    required JsonMap session,
    required JsonMap? restaurant,
    String operatorName = '',
    String authorizedBy = '',
    String managerReason = '',
    DateTime? now,
  }) {
    final isWithdrawal = '${movement['movement_type']}' == 'withdrawal';
    final amount = ValueFormatters.number(movement['amount']).abs();
    final lines = <String>[
      ..._header(
        restaurant,
        isWithdrawal
            ? 'COMPROVANTE DE SANGRIA DE CAIXA'
            : 'COMPROVANTE DE SUPRIMENTO DE CAIXA',
      ),
      'Data: ${_when(movement['created_at'], now)}',
      ..._sessionLines(session, operatorName),
      if (authorizedBy.trim().isNotEmpty)
        LocalPrintRenderer._clip('Autorizado por: ${authorizedBy.trim()}', _width),
      _rule,
      LocalPrintRenderer._amountLine(
        isWithdrawal ? 'Valor retirado' : 'Valor inserido',
        amount,
      ),
      ..._noteLines('Motivo', movement['reason']),
      ..._noteLines(
        isWithdrawal ? 'Destino' : 'Origem',
        movement['destination'] ?? movement['source'],
      ),
      ..._noteLines('Justificativa', managerReason),
      _rule,
      'Assinatura do responsavel:',
      _signature,
      ..._footer(now),
    ];
    return lines.join('\n');
  }

  /// Relatório de fechamento: a gaveta (dinheiro) e as vendas por forma.
  ///
  /// A gaveta sai dos movimentos aprovados, com o sinal que cada um carrega
  /// (a mesma conta do saldo esperado). As vendas por forma saem de `sales`
  /// (`CashRegisterSerializer.sales` / `registerLocalPayment`): é o que o
  /// operador confere contra os comprovantes da maquininha e do PIX.
  static String closing({
    required JsonMap session,
    required JsonMap? restaurant,
    String operatorName = '',
    DateTime? now,
  }) {
    final drawer = _CashDrawer.of(session);
    final sales = _SalesByMethod.of(session);
    final status = '${session['status'] ?? ''}';
    final closedAt = '${session['closed_at'] ?? ''}'.trim();
    final lines = <String>[
      ..._header(restaurant, 'RELATORIO DE FECHAMENTO DE CAIXA'),
      ..._sessionLines(session, operatorName),
      'Abertura: ${_when(session['opened_at'], now)}',
      'Fechamento: '
          '${closedAt.isEmpty ? _when(null, now) : _when(closedAt, now)}',
      _rule,
      LocalPrintRenderer._center('MOVIMENTO DA GAVETA (DINHEIRO)', _width),
      _cents('(+) Abertura (troco)', drawer.opening),
      _cents('(+) Vendas em dinheiro', drawer.cashSales),
      _cents('(+) Suprimentos', drawer.supplies),
      _cents('(-) Sangrias', drawer.withdrawals),
      if (drawer.changeGiven != 0)
        _cents('(-) Troco de outras formas', drawer.changeGiven),
      if (drawer.refunds != 0) _cents('(-) Estornos em dinheiro', drawer.refunds),
      _cents('(=) Esperado em caixa', drawer.expected),
      _cents('Valor contado', drawer.counted),
      _cents('Diferenca', drawer.difference),
      _rule,
      LocalPrintRenderer._center('VENDAS POR FORMA DE PAGAMENTO', _width),
      for (final line in sales.lines) _cents(line.label, line.cents),
      _cents('Total de vendas', sales.total),
      _cents('Comprovantes (nao dinheiro)', sales.total - sales.cash),
      'Recebimentos: ${sales.count}',
      _rule,
      'Status: ${_statusLabel(status)}',
      ..._noteLines('Obs', session['closing_notes'] ?? session['notes']),
      'Assinatura do gerente:',
      _signature,
      ..._footer(now),
    ];
    return lines.join('\n');
  }

  // ------------------------------------------------------------ pedaços

  static List<String> _header(JsonMap? restaurant, String title) => [
    ...LocalPrintRenderer._establishmentLines(
      LocalPrintRenderer._establishmentInfo(restaurant),
    ),
    _rule,
    LocalPrintRenderer._center(title, _width),
    _rule,
  ];

  static List<String> _sessionLines(JsonMap session, String operatorName) {
    final station = '${session['cash_station_name'] ?? session['station'] ?? ''}'
        .trim();
    final terminal = '${session['opened_terminal_label'] ?? ''}'.trim();
    final opener = '${session['opened_by_name'] ?? ''}'.trim();
    final operator = operatorName.trim().isEmpty ? opener : operatorName.trim();
    return [
      if (station.isNotEmpty) LocalPrintRenderer._clip('Caixa: $station', _width),
      if (operator.isNotEmpty)
        LocalPrintRenderer._clip('Operador: $operator', _width),
      if (terminal.isNotEmpty)
        LocalPrintRenderer._clip('Terminal: $terminal', _width),
    ];
  }

  static List<String> _noteLines(String label, Object? value) {
    final text = '${value ?? ''}'.trim();
    if (text.isEmpty) return const [];
    return [LocalPrintRenderer._clip('$label: $text', _width)];
  }

  static List<String> _footer(DateTime? now) => [
    _rule,
    'Impresso em ${LocalPrintRenderer._dateTimeWithSeconds(now ?? DateTime.now())}',
    '',
  ];

  static String _when(Object? raw, DateTime? fallback) {
    final parsed = DateTime.tryParse('${raw ?? ''}')?.toLocal();
    return LocalPrintRenderer._dateTimeWithSeconds(
      parsed ?? fallback ?? DateTime.now(),
    );
  }

  static String _cents(String label, int cents) =>
      LocalPrintRenderer._amountLine(label, DecimalMoney.asNumber(cents));

  static String _statusLabel(String status) =>
      const {
        'closed': 'FECHADO',
        'closed_with_difference': 'FECHADO COM DIVERGENCIA',
        'pending_manager_approval': 'AGUARDANDO APROVACAO GERENCIAL',
        'pending_closing': 'AGUARDANDO FECHAMENTO',
        'open': 'ABERTO',
      }[status] ??
      status.toUpperCase();
}

/// A gaveta em centavos, na mesma conta de `CashRegisterRepository`.
class _CashDrawer {
  const _CashDrawer({
    required this.opening,
    required this.cashSales,
    required this.supplies,
    required this.withdrawals,
    required this.changeGiven,
    required this.refunds,
    required this.expected,
    required this.counted,
    required this.difference,
  });

  final int opening;
  final int cashSales;
  final int supplies;
  final int withdrawals;
  final int changeGiven;
  final int refunds;
  final int expected;
  final int counted;
  final int difference;

  static _CashDrawer of(JsonMap session) {
    var opening = 0;
    var hasOpening = false;
    var cashSales = 0;
    var supplies = 0;
    var withdrawals = 0;
    var changeGiven = 0;
    var refunds = 0;
    for (final raw in session['movements'] as List? ?? const []) {
      if (raw is! Map) continue;
      if ('${raw['status'] ?? 'approved'}' != 'approved') continue;
      final cents = DecimalMoney.minorUnits(raw['amount']).abs();
      switch ('${raw['movement_type']}') {
        case 'opening':
          opening += cents;
          hasOpening = true;
        case 'sale':
          cashSales += cents;
        case 'supply':
          supplies += cents;
        case 'withdrawal':
          // O troco de cartão/PIX sai como retirada ligada ao pagamento.
          if ('${raw['payment'] ?? ''}'.isNotEmpty) {
            changeGiven += cents;
          } else {
            withdrawals += cents;
          }
        case 'refund':
          refunds += cents;
      }
    }
    // Sessão que só existe aqui ainda não tem movimento de abertura.
    if (!hasOpening) opening = DecimalMoney.minorUnits(session['opening_amount']);
    final expected = session['expected_amount'] == null
        ? opening + cashSales + supplies - withdrawals - changeGiven - refunds
        : DecimalMoney.minorUnits(session['expected_amount']);
    final counted = DecimalMoney.minorUnits(session['actual_amount']);
    return _CashDrawer(
      opening: opening,
      cashSales: cashSales,
      supplies: supplies,
      withdrawals: withdrawals,
      changeGiven: changeGiven,
      refunds: refunds,
      expected: expected,
      counted: counted,
      difference: session['difference_amount'] == null
          ? counted - expected
          : DecimalMoney.minorUnits(session['difference_amount']),
    );
  }
}

class _SalesLine {
  const _SalesLine(this.label, this.cents);
  final String label;
  final int cents;
}

/// Vendas agrupadas por forma, na ordem em que o operador confere.
class _SalesByMethod {
  const _SalesByMethod({
    required this.lines,
    required this.total,
    required this.cash,
    required this.count,
  });

  final List<_SalesLine> lines;
  final int total;
  final int cash;
  final int count;

  static const _order = [
    'cash',
    'card:credit',
    'card:debit',
    'card',
    'pix',
    'voucher',
    'other',
  ];

  static const _labels = {
    'cash': 'Dinheiro',
    'card:credit': 'Cartao credito',
    'card:debit': 'Cartao debito',
    'card': 'Cartao',
    'pix': 'PIX',
    'voucher': 'Vale/voucher',
    'other': 'Outras formas',
  };

  static _SalesByMethod of(JsonMap session) {
    final totals = <String, int>{};
    var total = 0;
    var count = 0;
    for (final raw in session['sales'] as List? ?? const []) {
      if (raw is! Map) continue;
      final type = '${raw['method_type'] ?? 'other'}'.trim().toLowerCase();
      final subtype = '${raw['card_subtype'] ?? ''}'.trim().toLowerCase();
      var key = type == 'card' && subtype.isNotEmpty ? 'card:$subtype' : type;
      if (!_labels.containsKey(key)) key = 'other';
      final cents = DecimalMoney.minorUnits(raw['amount']);
      totals[key] = (totals[key] ?? 0) + cents;
      total += cents;
      count += 1;
    }
    return _SalesByMethod(
      lines: [
        for (final key in _order)
          if (totals.containsKey(key)) _SalesLine(_labels[key]!, totals[key]!),
      ],
      total: total,
      cash: totals['cash'] ?? 0,
      count: count,
    );
  }
}
