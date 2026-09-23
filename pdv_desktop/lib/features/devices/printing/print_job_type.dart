/// O que está sendo impresso.
///
/// O nome de cada tipo é o mesmo gravado na coluna `job_type` da fila local
/// (SQLite) — por isso os apelidos: o backend usa `kitchen_ticket` onde a
/// fila daqui sempre gravou `kitchen`, e as duas grafias já convivem nas
/// linhas em disco de terminais atualizados em momentos diferentes.
enum PrintJobType {
  receipt('receipt', ['table_bill', 'cash_close']),
  kitchen('kitchen', ['kitchen_ticket', 'bar_ticket']),
  kitchenCancel('kitchen_cancel', ['kitchen_cancellation']),
  weighTicket('weigh_ticket', []),
  fiscalDanfe('fiscal_danfe', []),
  printerTest('printer_test', ['test']),

  /// Tipo que este PDV ainda não conhece — imprime como cupom comum em vez
  /// de recusar: um `job_type` novo no backend não pode deixar de sair no
  /// papel só porque o terminal está uma versão atrás.
  other('other', []);

  const PrintJobType(this.wire, this.aliases);

  /// Valor gravado na fila local.
  final String wire;

  /// Outras grafias aceitas na leitura (backend e versões anteriores).
  final List<String> aliases;

  static PrintJobType parse(Object? raw) {
    final value = '${raw ?? ''}'.trim().toLowerCase();
    if (value.isEmpty) return PrintJobType.receipt;
    for (final type in PrintJobType.values) {
      if (type.wire == value || type.aliases.contains(value)) return type;
    }
    return PrintJobType.other;
  }
}
