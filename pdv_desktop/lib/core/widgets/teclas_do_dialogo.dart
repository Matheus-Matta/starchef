import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Em todo diálogo: Enter confirma, Esc cancela.
///
/// Desde que Enter e Espaço pararam de "clicar" o botão focado
/// (`teclado_sem_navegacao.dart`), um diálogo só se fechava com o mouse. Aqui
/// as teclas valem para o diálogo inteiro, sem cada um precisar ligá-las:
///
/// - **Enter** aciona o botão PRINCIPAL: o último botão cheio
///   (`FilledButton`/`ElevatedButton`) habilitado. Desligado (falta dado),
///   Enter não faz nada — como o clique.
/// - **Esc** aciona o primeiro botão de texto ou contornado (o "Cancelar",
///   "Voltar"); sem ele, só fecha o diálogo.
///
/// Num campo de texto de uma linha, o Enter é do campo (`onSubmitted`): ele
/// chega lá primeiro e não sobe até aqui.
class TeclasDoDialogo extends StatelessWidget {
  const TeclasDoDialogo({super.key, required this.acoes, required this.child});

  final List<Widget> acoes;
  final Widget child;

  /// O `onPressed` do botão principal, ou `null` se não houver (ou desligado).
  static VoidCallback? confirmarDe(List<Widget> acoes) {
    for (final acao in acoes.reversed) {
      final botao = _botao(acao);
      if (botao is FilledButton || botao is ElevatedButton) {
        return botao!.onPressed;
      }
    }
    return null;
  }

  /// O `onPressed` do botão de cancelar, ou `null` se não houver.
  static VoidCallback? cancelarDe(List<Widget> acoes) {
    for (final acao in acoes) {
      final botao = _botao(acao);
      if ((botao is TextButton || botao is OutlinedButton) &&
          botao!.onPressed != null) {
        return botao.onPressed;
      }
    }
    return null;
  }

  /// O botão dentro de um embrulho simples (espaçamento, dica, largura).
  static ButtonStyleButton? _botao(Widget acao) {
    var atual = acao;
    for (var nivel = 0; nivel < 4; nivel++) {
      if (atual is ButtonStyleButton) return atual;
      final dentro = switch (atual) {
        SizedBox(:final child) => child,
        Padding(:final child) => child,
        Tooltip(:final child) => child,
        Expanded(:final child) => child,
        Flexible(:final child) => child,
        _ => null,
      };
      if (dentro == null) return null;
      atual = dentro;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final confirmar = confirmarDe(acoes);
    final cancelar = cancelarDe(acoes);
    void confirmarSeHouver() => confirmar?.call();
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.enter): confirmarSeHouver,
        const SingleActivator(LogicalKeyboardKey.numpadEnter):
            confirmarSeHouver,
        const SingleActivator(LogicalKeyboardKey.escape): () =>
            cancelar != null ? cancelar() : Navigator.maybePop(context),
      },
      // O foco dentro do diálogo é o que faz a tecla chegar até aqui.
      child: Focus(autofocus: true, child: child),
    );
  }
}

/// O `AlertDialog` do Material com as teclas do diálogo: para os poucos que
/// não usam o `AppDialog` e querem manter a aparência deles.
class AlertaComTeclas extends StatelessWidget {
  const AlertaComTeclas({
    super.key,
    this.title,
    this.content,
    this.actions = const [],
  });

  final Widget? title;
  final Widget? content;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => TeclasDoDialogo(
    acoes: actions,
    child: AlertDialog(title: title, content: content, actions: actions),
  );
}
