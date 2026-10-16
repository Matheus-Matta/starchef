import '../../../core/storage/local_preferences.dart';

/// Uma passagem pela Balança Rápida: o que foi lançado, onde e o papel dela.
class PassagemDaBalanca {
  const PassagemDaBalanca({
    required this.comanda,
    required this.produto,
    required this.pesoKg,
    required this.total,
    required this.quando,
    this.printJobId,
  });

  final String comanda;
  final String produto;
  final double pesoKg;
  final double total;
  final DateTime quando;

  /// Trabalho de impressão da etiqueta; `null` = saiu sem impressora.
  final String? printJobId;

  bool get reimprimivel => printJobId != null;

  Map<String, dynamic> toJson() => {
    'comanda': comanda,
    'produto': produto,
    'peso_kg': pesoKg,
    'total': total,
    'quando': quando.toIso8601String(),
    'print_job': printJobId,
  };

  static PassagemDaBalanca? fromJson(Object? json) {
    if (json is! Map) return null;
    final quando = DateTime.tryParse('${json['quando']}');
    if (quando == null) return null;
    final job = json['print_job'];
    return PassagemDaBalanca(
      comanda: '${json['comanda'] ?? ''}',
      produto: '${json['produto'] ?? ''}',
      pesoKg: (json['peso_kg'] as num?)?.toDouble() ?? 0,
      total: (json['total'] as num?)?.toDouble() ?? 0,
      quando: quando,
      printJobId: job == null ? null : '$job',
    );
  }
}

/// As últimas passagens DESTE terminal, a mais nova primeiro, para reimprimir.
///
/// Fica nas preferências do terminal (sobrevive a reiniciar o PDV) e guarda
/// só o necessário para achar e reimprimir a etiqueta. A reimpressão reusa o
/// MESMO trabalho de impressão: nada é lançado de novo na comanda.
class HistoricoDePassagens {
  const HistoricoDePassagens(this.preferences);

  final LocalPreferences preferences;
  static const maximo = 20;

  List<PassagemDaBalanca> ler() => preferences.historicoDaBalanca
      .map(PassagemDaBalanca.fromJson)
      .whereType<PassagemDaBalanca>()
      .toList();

  Future<void> registrar(PassagemDaBalanca passagem) =>
      preferences.setHistoricoDaBalanca([
        passagem.toJson(),
        ...ler().take(maximo - 1).map((p) => p.toJson()),
      ]);
}
