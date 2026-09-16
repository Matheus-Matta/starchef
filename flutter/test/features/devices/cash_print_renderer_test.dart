import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/devices/domain/local_print_renderer.dart';

/// Os comprovantes do caixa saem pelo mesmo caminho do recibo, com a mesma
/// largura e a mesma coluna de valor. O que se fixa aqui é o conteúdo que o
/// operador confere no papel: valores, quem fez, quem autorizou, e o
/// fechamento com a gaveta e as vendas por forma.
void main() {
  final restaurant = {
    'trade_name': 'StarChef',
    'cnpj': '00.000.000/0001-00',
    'address': 'Rua Principal, 100',
    'city': 'Sao Paulo',
    'state': 'SP',
  };

  final session = {
    'id': 'sessao-1',
    'cash_station_name': 'Caixa 02',
    'opened_by_name': 'Carlos Silva',
    'opened_terminal_label': 'Balcao 01',
    'opened_at': '2026-09-15T11:00:22Z',
    'opening_amount': '150.00',
    'notes': 'Turno da manha',
  };

  List<String> linesOf(String text) => text.split('\n');

  String amountLine(String text, String label) =>
      linesOf(text).firstWhere((line) => line.startsWith(label));

  test('abertura mostra o troco inicial, o caixa e o operador', () {
    final text = CashPrintRenderer.opening(
      session: session,
      restaurant: restaurant,
      operatorName: 'Carlos Silva',
      now: DateTime(2026, 9, 15, 8, 0, 25),
    );

    expect(text, contains('COMPROVANTE DE ABERTURA DE CAIXA'));
    expect(text, contains('Caixa: Caixa 02'));
    expect(text, contains('Operador: Carlos Silva'));
    expect(text, contains('Terminal: Balcao 01'));
    expect(text, contains('Obs: Turno da manha'));
    final amount = amountLine(text, 'Valor inserido (troco)');
    expect(amount.length, LocalPrintRenderer.receiptWidth);
    expect(amount.trimRight(), endsWith('R\$ 150.00'));
    expect(text, contains('Assinatura: '));
    expect(text, contains('Impresso em 15/09/2026 08:00:25'));
  });

  test('sangria imprime o valor positivo, destino e quem autorizou', () {
    final text = CashPrintRenderer.movement(
      movement: {
        'movement_type': 'withdrawal',
        // Retirada é NEGATIVA na sessão; no papel sai o valor retirado.
        'amount': '-800.00',
        'reason': 'Recolhimento de excesso',
        'destination': 'Cofre central',
        'created_at': '2026-09-15T17:30:15Z',
      },
      session: session,
      restaurant: restaurant,
      operatorName: 'Carlos Silva',
      authorizedBy: 'Paulo',
      managerReason: 'Malote das 14h',
    );

    expect(text, contains('COMPROVANTE DE SANGRIA DE CAIXA'));
    expect(amountLine(text, 'Valor retirado').trimRight(), endsWith('R\$ 800.00'));
    expect(text, contains('Motivo: Recolhimento de excesso'));
    expect(text, contains('Destino: Cofre central'));
    expect(text, contains('Autorizado por: Paulo'));
    expect(text, contains('Justificativa: Malote das 14h'));
    expect(text, contains('Assinatura do responsavel:'));
  });

  test('suprimento imprime a origem', () {
    final text = CashPrintRenderer.movement(
      movement: {
        'movement_type': 'supply',
        'amount': '50.00',
        'reason': 'Troco para a tarde',
        'source': 'Cofre',
      },
      session: session,
      restaurant: restaurant,
    );

    expect(text, contains('COMPROVANTE DE SUPRIMENTO DE CAIXA'));
    expect(amountLine(text, 'Valor inserido').trimRight(), endsWith('R\$ 50.00'));
    expect(text, contains('Origem: Cofre'));
    expect(text, isNot(contains('Autorizado por')));
  });

  test('fechamento separa a gaveta das vendas por forma', () {
    final text = CashPrintRenderer.closing(
      session: {
        ...session,
        'status': 'closed_with_difference',
        'closed_at': '2026-09-15T21:00:00Z',
        'expected_amount': '550.00',
        'actual_amount': '540.00',
        'difference_amount': '-10.00',
        'closing_notes': 'Faltou uma nota de 10',
        'movements': [
          {'movement_type': 'opening', 'amount': '150.00', 'status': 'approved'},
          {'movement_type': 'sale', 'amount': '700.00', 'status': 'approved'},
          {'movement_type': 'sale', 'amount': '500.00', 'status': 'approved'},
          {'movement_type': 'withdrawal', 'amount': '-800.00', 'status': 'approved'},
          // Troco de um cartão: retirada ligada ao pagamento.
          {
            'movement_type': 'withdrawal',
            'amount': '-5.00',
            'status': 'approved',
            'payment': 'pag-4',
          },
          // Sangria ainda aguardando autorização não conta.
          {'movement_type': 'withdrawal', 'amount': '-999.00', 'status': 'pending'},
        ],
        'sales': [
          {'method_type': 'cash', 'amount': '700.00'},
          {'method_type': 'cash', 'amount': '500.00'},
          {'method_type': 'card', 'card_subtype': 'credit', 'amount': '650.00'},
          {'method_type': 'card', 'card_subtype': 'debit', 'amount': '400.00'},
          {'method_type': 'pix', 'amount': '350.00'},
        ],
      },
      restaurant: restaurant,
      operatorName: 'Carlos Silva',
    );

    expect(text, contains('RELATORIO DE FECHAMENTO DE CAIXA'));
    expect(text, contains('Abertura: 15/09/2026'));
    expect(text, contains('Fechamento: 15/09/2026'));
    String amount(String label) => amountLine(text, label).trimRight();
    expect(amount('(+) Abertura (troco)'), endsWith('R\$ 150.00'));
    expect(amount('(+) Vendas em dinheiro'), endsWith('R\$ 1200.00'));
    expect(amount('(-) Sangrias'), endsWith('R\$ 800.00'));
    expect(amount('(-) Troco de outras formas'), endsWith('R\$ 5.00'));
    expect(amount('(=) Esperado em caixa'), endsWith('R\$ 550.00'));
    expect(amount('Valor contado'), endsWith('R\$ 540.00'));
    expect(amount('Diferenca'), endsWith('R\$ -10.00'));
    expect(amount('Dinheiro'), endsWith('R\$ 1200.00'));
    expect(amount('Cartao credito'), endsWith('R\$ 650.00'));
    expect(amount('Cartao debito'), endsWith('R\$ 400.00'));
    expect(amount('PIX'), endsWith('R\$ 350.00'));
    expect(amount('Total de vendas'), endsWith('R\$ 2600.00'));
    expect(amount('Comprovantes (nao dinheiro)'), endsWith('R\$ 1400.00'));
    expect(text, contains('Recebimentos: 5'));
    expect(text, contains('Status: FECHADO COM DIVERGENCIA'));
    expect(text, contains('Obs: Faltou uma nota de 10'));
    expect(text, contains('Assinatura do gerente:'));
    // Nenhuma linha estoura a bobina.
    for (final line in linesOf(text)) {
      expect(line.length, lessThanOrEqualTo(LocalPrintRenderer.receiptWidth));
    }
  });

  test('sessão só local (sem movimento de abertura) usa opening_amount', () {
    final text = CashPrintRenderer.closing(
      session: {
        ...session,
        'status': 'closed',
        'movements': const [],
        'sales': const [],
      },
      restaurant: restaurant,
    );

    expect(amountLine(text, '(+) Abertura (troco)').trimRight(), endsWith('R\$ 150.00'));
    expect(amountLine(text, '(=) Esperado em caixa').trimRight(), endsWith('R\$ 150.00'));
    expect(text, contains('Recebimentos: 0'));
  });
}
