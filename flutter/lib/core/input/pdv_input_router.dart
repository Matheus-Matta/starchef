import 'dart:async';

import 'package:flutter/services.dart';

import 'pdv_screen.dart';
import 'pdv_shortcuts.dart';
import 'scanner_keyboard_capture.dart';

/// De onde veio o código.
enum CodeSource {
  /// Leitor USB que se comporta como teclado.
  keyboardWedge,

  /// Leitor ligado à porta serial (o mesmo da balança).
  serial,

  /// Texto colado pelo operador, com F8 ou Ctrl + Shift + V.
  clipboard,
}

/// Um código já normalizado, pronto para a tela interpretar.
class ScannedCode {
  const ScannedCode({required this.value, required this.source});

  final String value;
  final CodeSource source;

  String get sourceLabel => switch (source) {
    CodeSource.keyboardWedge => 'Leitor (teclado)',
    CodeSource.serial => 'Leitor serial',
    CodeSource.clipboard => 'Área de transferência',
  };

  @override
  String toString() => '$value ($sourceLabel)';
}

/// O que a tela informa ao roteador sobre o momento atual.
///
/// O roteador não conhece nenhuma tela; ele pergunta. Sem isso, a ordem de
/// prioridade viraria uma corrente de `if` espalhada por cada página — e é
/// exatamente aí que o Enter do leitor acaba confirmando um pagamento.
class PdvInputContext {
  const PdvInputContext({
    required this.screen,
    this.hasTextFocus = false,
    this.hasModal = false,
    this.modalAcceptsScanner = false,
    this.hasOrder = false,
  });

  final PdvScreen screen;

  /// O foco está em um campo de texto.
  final bool hasTextFocus;

  /// Há um diálogo aberto por cima.
  final bool hasModal;

  /// O diálogo aberto declarou que entende códigos lidos.
  final bool modalAcceptsScanner;

  /// Existe um pedido em edição (habilita F9, F10, F12, +, -, Delete).
  final bool hasOrder;

  /// A captura do leitor pode acontecer agora?
  ///
  /// A prioridade pedida é: campo/modal primeiro, leitor depois. Um modal que
  /// declara entender código é a exceção — a balança rápida é assim.
  bool get scannerEnabled {
    // A balança rápida tem captura própria (comanda + produto + peso). Se o
    // roteador consumisse as teclas lá, ela pararia de receber a leitura que
    // já sabe interpretar.
    if (screen.hasOwnScannerFlow) return false;
    if (hasTextFocus) return false;
    if (hasModal) return modalAcceptsScanner;
    return screen.readsCodes;
  }

  /// Atalhos de página e globais podem disparar agora?
  ///
  /// Com um campo focado, quase tudo pertence ao campo. As teclas de função
  /// continuam valendo porque não produzem texto — sem elas, o operador
  /// perderia F1 e F8 justamente enquanto digita.
  bool shortcutEnabled(PdvShortcut shortcut) {
    // Com um diálogo aberto, o teclado é dele. Esc precisa fechar o modal
    // superior e parar aí: se o roteador também respondesse, uma tecla
    // fecharia o modal E voltaria de página, e o operador perderia a tela sem
    // ter pedido. O mesmo vale para F10 disparando um pagamento por trás de
    // uma confirmação que ainda está na frente do operador.
    if (hasModal) return false;
    if (shortcut.requiresOrder && !hasOrder) return false;
    if (!hasTextFocus) return true;
    return _isFunctionKey(shortcut.trigger.key) ||
        shortcut.trigger.control ||
        shortcut.trigger.alt;
  }

  // `LogicalKeyboardKey` sobrescreve `==`, então o conjunto não pode ser
  // `const`. `static final` monta uma vez e evita reconstruí-lo a cada tecla.
  static final Set<LogicalKeyboardKey> _functionKeys = {
    LogicalKeyboardKey.f1,
    LogicalKeyboardKey.f2,
    LogicalKeyboardKey.f3,
    LogicalKeyboardKey.f4,
    LogicalKeyboardKey.f5,
    LogicalKeyboardKey.f6,
    LogicalKeyboardKey.f7,
    LogicalKeyboardKey.f8,
    LogicalKeyboardKey.f9,
    LogicalKeyboardKey.f10,
    LogicalKeyboardKey.f11,
    LogicalKeyboardKey.f12,
    LogicalKeyboardKey.escape,
  };

  static bool _isFunctionKey(LogicalKeyboardKey key) =>
      _functionKeys.contains(key);
}

/// O controlador central de entrada do PDV.
///
/// Teclado, leitor serial, leitor que simula teclado e área de transferência
/// produzem o MESMO evento interno; daqui para baixo nenhuma tela precisa
/// saber de onde o código veio. A tela informa o contexto, o roteador resolve
/// a prioridade e entrega o código já normalizado para quem sabe interpretá-lo.
///
/// A ordem é sempre esta, e ela existe para uma razão concreta:
///
/// 1. campo de texto ou modal aberto — o teclado pertence a quem tem o foco;
/// 2. captura do leitor — inclusive o Enter que ele envia no fim, que é
///    consumido para não confirmar um pagamento nem fechar um modal;
/// 3. atalhos da página;
/// 4. atalhos globais.
class PdvInputRouter {
  PdvInputRouter({
    required PdvInputContext Function() readContext,
    ScannerKeyboardCapture? capture,
    Future<String?> Function()? readClipboard,
  }) : _readContext = readContext,
       _capture = capture ?? ScannerKeyboardCapture(),
       _readClipboard = readClipboard ?? _defaultClipboardReader;

  static Future<String?> _defaultClipboardReader() async =>
      (await Clipboard.getData(Clipboard.kTextPlain))?.text;

  final PdvInputContext Function() _readContext;
  final ScannerKeyboardCapture _capture;
  final Future<String?> Function() _readClipboard;

  final StreamController<ScannedCode> _codes = StreamController.broadcast();
  final StreamController<PdvShortcut> _shortcuts = StreamController.broadcast();

  /// Códigos normalizados, venham de onde vierem.
  Stream<ScannedCode> get codes => _codes.stream;

  /// Atalhos disparados, já filtrados por tela e por estado.
  Stream<PdvShortcut> get shortcuts => _shortcuts.stream;

  /// Última leitura entregue — a página de ajuda mostra para diagnóstico.
  ScannedCode? lastCode;

  /// Quando cada ação protegida disparou pela última vez.
  ///
  /// Quais são as protegidas é decisão do REGISTRO (`guardsRepeat`), não desta
  /// classe: uma segunda lista aqui se desencontraria dele no primeiro atalho
  /// novo, e o sintoma seria uma tecla presa virando duas cobranças.
  final Map<String, DateTime> _lastFired = {};
  static const _repeatGuard = Duration(milliseconds: 400);

  /// Ponto único de entrada do teclado. Devolve `true` quando consome a tecla.
  bool handleKeyEvent(KeyEvent event) {
    final context = _readContext();

    // 2. Captura do leitor. Vem antes dos atalhos porque um código pode conter
    //    dígitos e letras que também são atalhos — e porque o terminador
    //    precisa ser consumido pela leitura, não pela tela.
    if (context.scannerEnabled) {
      final result = _capture.handle(event, acceptsInput: true);
      if (result.hasCode) {
        submit(result.code!, source: CodeSource.keyboardWedge);
        return true;
      }
      if (result.consumed) return true;
    } else {
      // 1. Campo ou modal com o foco: o teclado é deles. O buffer é zerado
      //    para uma leitura pela metade não vazar para a próxima tela.
      _capture.handle(event, acceptsInput: false);
    }

    if (event is! KeyDownEvent) return false;

    // 3 e 4. Atalhos da página e depois os globais — `resolve` já respeita a
    // ordem do catálogo e o recorte por tela.
    final shortcut = PdvShortcuts.resolve(event, screen: context.screen);
    if (shortcut == null) return false;
    if (!context.shortcutEnabled(shortcut)) return false;
    if (!_allowRepeat(shortcut)) return true;
    _shortcuts.add(shortcut);
    return true;
  }

  bool _allowRepeat(PdvShortcut shortcut) {
    if (!shortcut.guardsRepeat) return true;
    final now = DateTime.now();
    final last = _lastFired[shortcut.id];
    if (last != null && now.difference(last) < _repeatGuard) return false;
    _lastFired[shortcut.id] = now;
    return true;
  }

  /// Entrega um código de qualquer origem, já normalizado.
  ///
  /// Devolve `false` quando o código não sobra nada depois da normalização, ou
  /// quando a tela atual não lê códigos.
  bool submit(String raw, {required CodeSource source}) {
    final value = normalize(raw);
    if (value.isEmpty) return false;
    final context = _readContext();
    // A balança tem interpretação própria; o roteador não interfere lá.
    if (!context.screen.readsCodes || context.screen.hasOwnScannerFlow) {
      return false;
    }
    final scanned = ScannedCode(value: value, source: source);
    lastCode = scanned;
    _codes.add(scanned);
    return true;
  }

  /// Lê a área de transferência e trata o texto como uma leitura.
  ///
  /// Só por ação do operador (F8 / Ctrl + Shift + V). Vigiar a área de
  /// transferência em segundo plano interpretaria senha copiada, texto de
  /// conversa e código antigo — coisas que ninguém pediu para o PDV ler.
  Future<bool> readFromClipboard() async {
    final text = await _readClipboard();
    if (text == null) return false;
    return submit(text, source: CodeSource.clipboard);
  }

  void dispose() {
    unawaited(_codes.close());
    unawaited(_shortcuts.close());
  }

  /// Normalização comum a todas as origens.
  ///
  /// Remove o sufixo de quebra de linha que o leitor envia, corta espaços das
  /// pontas e recusa texto com mais de uma linha — um parágrafo colado por
  /// engano não é um código.
  static String normalize(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return '';
    final lines = trimmed
        .split(RegExp(r'[\r\n]+'))
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();
    if (lines.length != 1) return '';
    final value = lines.first;
    // Um código não tem espaço no meio; um texto qualquer tem.
    if (value.contains(' ')) return '';
    return value.length > 64 ? '' : value;
  }
}
