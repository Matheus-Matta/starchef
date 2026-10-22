import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

/// O teclado do PDV são os ATALHOS dele; o resto é mouse.
///
/// O Flutter traz o teclado de navegador: Tab e as setas passeiam o foco
/// pelos botões e campos, e Enter/Espaço "clicam" o botão focado. No caixa
/// isso atrapalhava — a seta que devia escolher a forma de pagamento pulava
/// para um botão qualquer, e o Enter acionava o botão que o Tab tinha focado.
///
/// Aqui essas teclas deixam de navegar e de acionar na raiz do app. O que
/// continua valendo:
/// - os atalhos do PDV (`pdv_shortcuts.dart`), lidos ANTES do foco pelo
///   `HardwareKeyboard`; a tecla que eles usaram é segurada pela
///   `PdvKeyBarrier` e não chega até aqui;
/// - dentro de um campo de texto, setas movem o cursor e Enter confirma: o
///   campo trata essas teclas antes da raiz;
/// - Esc fecha o diálogo, e os diálogos que têm teclas próprias (produto,
///   pesagem, DANFE) seguem com elas.
///
/// `DoNothingAndStopPropagationIntent`, e não `DoNothingIntent`: a tecla não é
/// marcada como tratada, e assim continua chegando ao campo de texto pela
/// entrada do sistema (o Enter do `onSubmitted`).
Map<ShortcutActivator, Intent> atalhosSemNavegacao() => {
  ...WidgetsApp.defaultShortcuts,
  for (final tecla in teclasDeNavegacao)
    tecla: const DoNothingAndStopPropagationIntent(),
};

/// As teclas que o navegador usa para andar e clicar sem mouse.
const teclasDeNavegacao = <SingleActivator>[
  SingleActivator(LogicalKeyboardKey.tab),
  SingleActivator(LogicalKeyboardKey.tab, shift: true),
  SingleActivator(LogicalKeyboardKey.arrowUp),
  SingleActivator(LogicalKeyboardKey.arrowDown),
  SingleActivator(LogicalKeyboardKey.arrowLeft),
  SingleActivator(LogicalKeyboardKey.arrowRight),
  SingleActivator(LogicalKeyboardKey.enter),
  SingleActivator(LogicalKeyboardKey.numpadEnter),
  SingleActivator(LogicalKeyboardKey.space),
];
