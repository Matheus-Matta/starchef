import '../../../core/data/local_id.dart';
import '../../../core/network/api_client.dart';

/// Lança a pesagem NA COMANDA, numa ida só ao servidor.
///
/// Eram duas em sequência: registrar a leitura (`/scales/readings/`) e só então
/// lançar com o id dela. O lançamento (`checkout-command`) aceita o peso direto
/// e cria a leitura na mesma transação — o mesmo caminho do reenvio offline —,
/// então a primeira ida só somava espera com a tela girando.
class LancamentoDaPesagem {
  LancamentoDaPesagem(this.api, {required this.accessToken});

  final ApiClient api;
  final String accessToken;

  /// Devolve o trabalho de impressão da etiqueta (já reservado para esta
  /// estação, ou `null` sem ele) e o número da comanda onde o prato entrou.
  ///
  /// [comanda] `null` é a comanda automática: o servidor escolhe a próxima
  /// livre (`fila_da_comanda.py`).
  Future<({Map<String, dynamic>? printJob, String? comanda})> lancar({
    String? id,
    required String balanca,
    required String? comanda,
    String? produto,
    required double pesoKg,
    required List<Map<String, dynamic>> extras,
    required bool imprimir,
  }) async {
    final resultado = await api.post(
      '/scales/$balanca/checkout-command/',
      body: {
        // O UUID desta pesagem: se a loja gravar e cair antes de responder,
        // o desvio para a nuvem é a MESMA pesagem (`pesagem_por_uuid.py`).
        // O MESMO em toda tentativa do mesmo prato (`id_da_pesagem.dart`).
        'id': id ?? LocalId.uuid(),
        'command_code': ?comanda,
        if (comanda == null) 'comanda_automatica': true,
        // O produto por quilo escolhido na estação; sem ele, o da balança.
        'weighed_product': ?produto,
        'weight_kg': pesoKg.toStringAsFixed(3),
        'tare_kg': '0.000',
        'extras': extras,
        // Sem impressora vinculada não há ticket a emitir: pedir impressão
        // faria o servidor recusar o lançamento inteiro.
        'print': imprimir,
        // A própria estação imprime (`etiqueta_da_pesagem.dart`): o trabalho
        // nasce reservado para ela, e nenhum outro PC o pega.
        'imprime_aqui': imprimir,
      },
      accessToken: accessToken,
    );
    final job = resultado['print_job'];
    final comandaUsada = resultado['command'];
    return (
      printJob: job is! Map || '${job['id'] ?? ''}'.trim().isEmpty
          ? null
          : Map<String, dynamic>.from(job),
      comanda: comandaUsada is Map ? '${comandaUsada['number']}' : null,
    );
  }
}
