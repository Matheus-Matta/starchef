import 'package:flutter/services.dart';

/// Junta as teclas de um leitor USB que se comporta como teclado.
///
/// A maioria dos leitores de código de barras não é um dispositivo especial:
/// eles digitam o código muito rápido e terminam com Enter ou Tab. Isso cria
/// dois problemas que este buffer resolve.
///
/// O primeiro é reconhecer o código. Caractere a caractere, ele é
/// indistinguível de alguém digitando; o que separa os dois é a CADÊNCIA — um
/// leitor manda tudo em poucos milissegundos. Por isso a janela entre teclas é
/// curta: quando a pausa passa de [interKeyTimeout], o que havia no buffer era
/// digitação e é descartado.
///
/// O segundo é o Enter final. Se ele chegar à tela como uma tecla comum,
/// confirma o que estiver em foco — um pagamento, um modal. Por isso o
/// terminador é SEMPRE consumido junto com o código.
class ScannerKeyboardCapture {
  ScannerKeyboardCapture({
    this.interKeyTimeout = const Duration(milliseconds: 90),
    this.minimumLength = 3,
    this.maximumLength = 64,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  /// Pausa máxima entre duas teclas para elas ainda serem a mesma leitura.
  ///
  /// 90 ms é generoso para um leitor (que costuma ficar abaixo de 30 ms) e
  /// curto para uma pessoa: digitar 3 caracteres nesse ritmo, seguidos de
  /// Enter, exigiria mais de 600 caracteres por minuto sem uma única pausa.
  final Duration interKeyTimeout;

  /// Códigos curtos demais não são leitura — são teclas soltas antes de um
  /// Enter que o operador apertou de propósito.
  final int minimumLength;

  /// Teto de tamanho. Um leitor mal configurado que despeje um texto inteiro
  /// não pode encher a memória nem virar uma "leitura" absurda.
  final int maximumLength;

  final DateTime Function() _clock;

  final StringBuffer _buffer = StringBuffer();
  DateTime? _lastKeyAt;
  DateTime? _startedAt;

  /// O que já foi acumulado nesta leitura, antes do terminador chegar.
  String get partial => _buffer.toString();

  void reset() {
    _buffer.clear();
    _lastKeyAt = null;
    _startedAt = null;
  }

  /// Processa uma tecla. Devolve o resultado do que fazer com ela.
  ///
  /// [acceptsInput] é `false` quando o operador está digitando em um campo:
  /// ali o teclado pertence ao campo, e um leitor disparado por engano deve
  /// simplesmente escrever no campo como qualquer outra digitação.
  ScannerKeyResult handle(KeyEvent event, {required bool acceptsInput}) {
    if (event is! KeyDownEvent) return ScannerKeyResult.ignored;
    if (!acceptsInput) {
      reset();
      return ScannerKeyResult.ignored;
    }

    final keyboard = HardwareKeyboard.instance;
    if (keyboard.isControlPressed ||
        keyboard.isAltPressed ||
        keyboard.isMetaPressed) {
      // Um atalho não é parte de um código lido.
      reset();
      return ScannerKeyResult.ignored;
    }

    final now = _clock();
    final key = event.logicalKey;
    final isTerminator =
        key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter ||
        key == LogicalKeyboardKey.tab;

    if (isTerminator) {
      final code = _buffer.toString().trim();
      final started = _startedAt;
      reset();
      if (code.length < minimumLength) {
        // Enter solto: pertence à tela, não ao leitor.
        return ScannerKeyResult.ignored;
      }
      if (started != null && now.difference(started) > _readingWindow) {
        // Demorou demais para ser uma leitura — era digitação seguida de
        // Enter, e o Enter é do operador.
        return ScannerKeyResult.ignored;
      }
      // O terminador é consumido junto: é ele que, solto, confirmaria um
      // pagamento ou fecharia um modal por conta do leitor.
      return ScannerKeyResult.code(code);
    }

    final character = event.character;
    if (character == null || character.isEmpty) return ScannerKeyResult.ignored;
    if (character.runes.any((rune) => rune < 0x20 || rune == 0x7f)) {
      return ScannerKeyResult.ignored;
    }

    final last = _lastKeyAt;
    if (last != null && now.difference(last) > interKeyTimeout) {
      // A pausa foi longa: o que estava acumulado era digitação humana.
      _buffer.clear();
      _startedAt = null;
    }
    _startedAt ??= now;
    _lastKeyAt = now;
    if (_buffer.length >= maximumLength) {
      reset();
      return ScannerKeyResult.ignored;
    }
    _buffer.write(character);
    // A tecla é consumida enquanto a leitura corre: deixá-la passar faria o
    // código aparecer digitado na tela junto com a leitura.
    return ScannerKeyResult.buffering;
  }

  /// Janela total de uma leitura, do primeiro caractere ao terminador.
  Duration get _readingWindow =>
      Duration(milliseconds: interKeyTimeout.inMilliseconds * maximumLength);
}

/// O que a tela deve fazer com a tecla que acabou de chegar.
class ScannerKeyResult {
  const ScannerKeyResult._(this.code, this.consumed);

  /// Tecla que não interessa ao leitor: siga o fluxo normal.
  static const ignored = ScannerKeyResult._(null, false);

  /// Tecla acumulada em uma leitura em andamento: consumida, sem ação ainda.
  static const buffering = ScannerKeyResult._(null, true);

  /// Leitura concluída.
  factory ScannerKeyResult.code(String value) => ScannerKeyResult._(value, true);

  /// O código lido, quando a leitura terminou.
  final String? code;

  /// A tecla foi consumida e não deve chegar à tela.
  final bool consumed;

  bool get hasCode => code != null;
}
