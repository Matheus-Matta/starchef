import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/table_occupancy.dart';

/// A mesa não pode ter dois estados ao mesmo tempo.
///
/// O defeito: a lista lia a coluna `status` e o detalhe contava os cartões. Uma
/// mesa com `occupied` velho no banco aparecia **Ocupada** na grade e livre ao
/// abrir — mesma mesa, um clique de diferença.
void main() {
  Map<String, dynamic> mesa({String status = 'free', int comandas = 0}) => {
    'number': '12',
    'status': status,
    'active_commands': List.generate(comandas, (i) => {'id': 'c-$i'}),
  };

  test('sem comanda vinculada a mesa está livre, doa a coluna o que disser', () {
    // O caso relatado: `occupied` que sobrou de um desvínculo.
    expect(tableIsOccupied(mesa(status: 'occupied')), isFalse);
    expect(tableStatusLabel(mesa(status: 'occupied')), 'Livre');
  });

  test('com cartão sentado está ocupada, mesmo com a coluna atrasada', () {
    expect(tableIsOccupied(mesa(status: 'free', comandas: 1)), isTrue);
    expect(tableStatusLabel(mesa(status: 'free', comandas: 2)), 'Ocupada');
  });

  test('reserva e limpeza são decisão de pessoa e sobrevivem', () {
    // Derivá-las do vínculo apagaria a reserva de uma mesa que ainda não
    // recebeu ninguém.
    expect(tableStatusLabel(mesa(status: 'reserved')), 'Reservada');
    expect(tableStatusLabel(mesa(status: 'cleaning')), 'Em limpeza');
  });

  test('ocupada vence reserva: tem gente sentada ali agora', () {
    expect(tableStatusLabel(mesa(status: 'reserved', comandas: 1)), 'Ocupada');
  });

  test('payload sem o campo de comandas não quebra a grade', () {
    expect(tableIsOccupied({'number': '3'}), isFalse);
    expect(tableStatusLabel({'number': '3'}), 'Livre');
  });
}
