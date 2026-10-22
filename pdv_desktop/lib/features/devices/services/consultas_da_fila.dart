import '../printing/print_job_type.dart';

/// As consultas da fila remota: só o que ESTE terminal imprime sozinho.
///
/// A consulta pedia os 100 trabalhos pendentes do restaurante inteiro e o
/// agente descartava, um a um, os que não eram com ele — de impressora com a
/// impressão automática desligada, sem equipamento, de outra estação. Como o
/// descarte não muda o trabalho no servidor, a mesma centena voltava em toda
/// consulta: 6.000 linhas de "print_job_skipped_auto_print_off" em 50 minutos
/// (pdv.log), e as comandas novas disputando lugar na página com o lixo.
///
/// Agora o filtro é do servidor (`printer__in`):
/// - impressoras com `auto_print`: todos os tipos;
/// - impressoras sem `auto_print`: só a nota de pesagem, que a balança rápida
///   imprime mesmo assim (é a regra do laço em `_ingestRemotePrintJobs`).
///
/// Sem impressora endereçável não há consulta: nada daqui sairia no papel.
List<Map<String, dynamic>> consultasDaFila({
  required String restaurantId,
  required Iterable<Map<String, dynamic>> impressoras,
}) {
  final automaticas = <String>[];
  final manuais = <String>[];
  for (final impressora in impressoras) {
    (impressora['auto_print'] == true ? automaticas : manuais).add(
      '${impressora['id']}',
    );
  }
  Map<String, dynamic> consulta(List<String> ids) => {
    'restaurant': restaurantId,
    'printer__in': ids.join(','),
    'status__in': 'scheduled,pending,rendered',
    'page_size': 100,
    // Do MAIS NOVO para o mais velho. Uma loja com acumulado tem mais de cem
    // trabalhos parados no servidor; ordenando do mais velho, a primeira
    // página seria só lixo antigo — que o corte de idade descarta — e a
    // comanda recém-criada não caberia nela.
    'ordering': '-created_at',
  };
  return [
    if (automaticas.isNotEmpty) consulta(automaticas),
    if (manuais.isNotEmpty)
      {...consulta(manuais), 'job_type': PrintJobType.weighTicket.wire},
  ];
}
