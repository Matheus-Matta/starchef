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

  /// Devolve o id do trabalho de impressão da etiqueta, ou `null` sem ele.
  Future<String?> lancar({
    required String balanca,
    required String comanda,
    required double pesoKg,
    required List<Map<String, dynamic>> extras,
    required bool imprimir,
  }) async {
    final resultado = await api.post(
      '/scales/$balanca/checkout-command/',
      body: {
        // O UUID desta pesagem: se a loja gravar e cair antes de responder,
        // o desvio para a nuvem é a MESMA pesagem (`pesagem_por_uuid.py`).
        'id': LocalId.uuid(),
        'command_code': comanda,
        'weight_kg': pesoKg.toStringAsFixed(3),
        'tare_kg': '0.000',
        'extras': extras,
        // Sem impressora vinculada não há ticket a emitir: pedir impressão
        // faria o servidor recusar o lançamento inteiro.
        'print': imprimir,
      },
      accessToken: accessToken,
    );
    final job = resultado['print_job'];
    if (job is! Map) return null;
    final id = '${job['id'] ?? ''}'.trim();
    return id.isEmpty ? null : id;
  }
}
