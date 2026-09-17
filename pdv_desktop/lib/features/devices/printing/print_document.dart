import '../../../core/data/print_queue_service.dart';

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

/// O documento a imprimir: exatamente os campos que a fila local guarda.
///
/// É o modelo que atravessa todo o caminho da impressão — quem monta o cupom
/// devolve um destes, a fila grava um destes, e a impressora recebe um
/// destes. Antes cada etapa carregava as mesmas quatro informações soltas em
/// parâmetros posicionais diferentes (`content`, `barcodeValue`, `qrValue`,
/// `jobType`), e bastava uma chamada esquecer o código de barras para a
/// comanda sair sem ele.
class PrintDocument {
  const PrintDocument({
    required this.type,
    required this.content,
    this.barcode,
    this.qr,
    this.remoteJobId,
    this.rawType,
  });

  final PrintJobType type;

  /// Cupom já renderizado em texto.
  final String content;

  /// Valor Code128 (comanda), quando houver.
  final String? barcode;

  /// Valor do QR Code (DANFE NFC-e), quando houver.
  final String? qr;

  /// `PrintJob` correspondente no servidor, quando este documento veio de lá.
  final String? remoteJobId;

  /// Grafia original do tipo, preservada para não reescrever no servidor um
  /// `job_type` que ele conhece e este PDV ainda não.
  final String? rawType;

  /// Valor a gravar na fila local.
  String get wireType => rawType ?? type.wire;

  bool get isEmpty => content.trim().isEmpty;

  PrintDocument copyWith({String? content, String? barcode, String? qr}) =>
      PrintDocument(
        type: type,
        content: content ?? this.content,
        barcode: barcode ?? this.barcode,
        qr: qr ?? this.qr,
        remoteJobId: remoteJobId,
        rawType: rawType,
      );

  /// Documento montado por este terminal (offline ou por escolha do caixa).
  factory PrintDocument.local({
    required PrintJobType type,
    required String content,
    String? barcode,
    String? qr,
  }) => PrintDocument(
    type: type,
    content: content,
    barcode: barcode,
    qr: qr,
  );

  /// Documento que já estava na fila local.
  factory PrintDocument.fromQueueEntry(PrintQueueEntry entry) => PrintDocument(
    type: PrintJobType.parse(entry.jobType),
    content: entry.content,
    barcode: entry.barcode,
    qr: entry.qr,
    remoteJobId: entry.remoteJobId,
    rawType: entry.jobType,
  );

  /// Documento de um `PrintJob` renderizado pelo servidor.
  ///
  /// `text_content` é o caminho normal; o HTML só entra como último recurso
  /// (ex.: `POST /orders/{id}/print/` não devolve o payload, só o HTML).
  factory PrintDocument.fromRemoteJob(Map<String, dynamic> job) {
    final rawPayload = job['payload'];
    final payload = rawPayload is Map<String, dynamic>
        ? rawPayload
        : const <String, dynamic>{};
    final readyText = '${payload['text_content'] ?? ''}'.trim();
    final text = readyText.isNotEmpty
        ? readyText
        : htmlToText('${job['html'] ?? job['html_content'] ?? ''}');
    final rawType = '${job['job_type'] ?? ''}'.trim();
    return PrintDocument(
      type: PrintJobType.parse(rawType),
      content: text,
      barcode: code128ValueFromPayload(payload),
      qr: qrValueFromPayload(payload),
      remoteJobId: '${job['print_job_id'] ?? job['id'] ?? ''}'.trim().isEmpty
          ? null
          : '${job['print_job_id'] ?? job['id']}',
      rawType: rawType.isEmpty ? null : rawType,
    );
  }

  static String? code128ValueFromPayload(Map<String, dynamic> payload) {
    final payloadVersion = int.tryParse('${payload['payload_version'] ?? ''}');
    if (payloadVersion != 2) return null;

    final rawBarcode = payload['barcode'];
    if (rawBarcode is! Map) return null;
    final symbology = '${rawBarcode['symbology'] ?? ''}'.trim().toUpperCase();
    final value = '${rawBarcode['value'] ?? ''}'.trim();
    if (symbology != 'CODE128' || value.isEmpty) return null;
    return value;
  }

  /// Extracts the NFC-e QR Code payload (fiscal DANFE print jobs only).
  ///
  /// Mirrors [code128ValueFromPayload]'s payload_version gate — same contract,
  /// different key (`qr_data` instead of a nested `barcode` map), because a
  /// DANFE fiscal job carries a QR Code, not a Code128 barcode.
  static String? qrValueFromPayload(Map<String, dynamic> payload) {
    final payloadVersion = int.tryParse('${payload['payload_version'] ?? ''}');
    if (payloadVersion != 2) return null;
    final value = '${payload['qr_data'] ?? ''}'.trim();
    return value.isEmpty ? null : value;
  }

  /// Último recurso quando o job não trouxe `text_content` pronto.
  ///
  /// Colapsa primeiro o espaço em branco ENTRE tags: a indentação do
  /// template Django é inconsistente (algumas linhas de tabela quebradas em
  /// várias linhas de código-fonte, outras compactas numa linha só), e sem
  /// isso o resultado dependia de acidente de formatação do HTML — uma
  /// célula ganhava quebra de linha de graça, a vizinha colava direto no
  /// valor ("SubtotalR$ 237,00"). Cada `</td>` fechado sempre vira o mesmo
  /// separador, não importa como o HTML de origem foi indentado.
  static String htmlToText(String html) => html
      .replaceAll(RegExp(r'>\s+<'), '><')
      // CSS/JS nao sao conteudo imprimivel. Sem esta remocao, o fallback de
      // jobs antigos imprimia regras como "td { padding... }" junto aos itens.
      .replaceAll(
        RegExp(r'<(style|script)\b[^>]*>[\s\S]*?</\1>', caseSensitive: false),
        '',
      )
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(RegExp(r'</td>', caseSensitive: false), '  ')
      .replaceAll(
        RegExp(r'</(p|div|tr|li|h[1-6])>', caseSensitive: false),
        '\n',
      )
      .replaceAll(RegExp(r'<[^>]+>'), '')
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll(RegExp(r'[ \t]+\n'), '\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
