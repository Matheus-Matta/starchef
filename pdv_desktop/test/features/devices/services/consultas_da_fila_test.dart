import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/devices/services/consultas_da_fila.dart';

/// A fila remota pede ao servidor só o que este terminal imprime sozinho.
///
/// Antes vinham os 100 pendentes do restaurante inteiro e o agente descartava
/// todos os de impressora com impressão automática desligada — de novo a cada
/// consulta, porque descartar não muda nada no servidor (6.000 linhas de log
/// em 50 minutos).
void main() {
  test('impressora automática pede tudo; a manual, só a nota de pesagem', () {
    final consultas = consultasDaFila(
      restaurantId: 'rest-1',
      impressoras: [
        {'id': 'cozinha', 'auto_print': true},
        {'id': 'bar', 'auto_print': true},
        {'id': 'caixa', 'auto_print': false},
      ],
    );

    expect(consultas, hasLength(2));
    expect(consultas[0]['printer__in'], 'cozinha,bar');
    expect(consultas[0].containsKey('job_type'), isFalse);
    expect(consultas[1]['printer__in'], 'caixa');
    expect(consultas[1]['job_type'], 'weigh_ticket');
    for (final consulta in consultas) {
      expect(consulta['restaurant'], 'rest-1');
      expect(consulta['status__in'], 'scheduled,pending,rendered');
      expect(consulta['ordering'], '-created_at');
    }
  });

  test('sem impressora endereçável não há consulta nenhuma', () {
    expect(consultasDaFila(restaurantId: 'rest-1', impressoras: []), isEmpty);
  });
}
