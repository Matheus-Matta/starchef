import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Controlador usado depois de descartado, no fechamento de um diálogo.
///
/// O formato do defeito é sempre o mesmo, e o analisador não o enxerga:
///
/// ```dart
/// final senha = TextEditingController();
/// try {
///   await showDialog(... onPressed: () async {
///     await autorizar();
///     Navigator.pop(ctx);   // showDialog retorna -> o finally descarta
///     await recarregar();   // ainda rodando...
///     senha.clear();        // ...e mexe no controlador já descartado
///   });
/// } finally {
///   senha.dispose();
/// }
/// ```
///
/// O `Navigator.pop` faz o `showDialog` completar e o `finally` descartar os
/// controladores NA MESMA volta do laço de eventos, enquanto o callback do
/// botão continua rodando. O sintoma é uma tela vermelha dizendo "A
/// TextEditingController was used after being disposed" — que esconde o erro
/// de verdade, porque ela aparece justamente quando o trabalho depois do
/// `pop` falha.
///
/// Aconteceu duas vezes neste código (autorização de sangria/suprimento e
/// aprovação de divergência de caixa), e o defeito foi herdado do PDV antigo.
/// A regra: **depois do `Navigator.pop`, não toque mais nos controladores.**
/// Trabalho demorado (recarregar a tela, imprimir) vai para depois do
/// `showDialog`, no método que o chamou.
void main() {
  test('nenhum diálogo mexe num controlador depois de fechar', () {
    final suspeitos = <String>[];

    for (final arquivo in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final linhas = arquivo.readAsLinesSync();
      for (var i = 0; i < linhas.length; i += 1) {
        final descarte = RegExp(
          r'^\s*([A-Za-z_][A-Za-z0-9_]*)\.dispose\(\);',
        ).firstMatch(linhas[i]);
        if (descarte == null) continue;
        final controlador = descarte.group(1)!;

        // Janela do método: do `pop` mais recente até este descarte.
        final inicio = i - 90 < 0 ? 0 : i - 90;
        final janela = linhas.sublist(inicio, i).join('\n');
        final pop = janela.lastIndexOf('Navigator.pop');
        if (pop == -1) continue;

        final depoisDoPop = janela.substring(pop);
        // Só é defeito quando, depois do `pop`, há espera E o controlador é
        // tocado de novo. Um `await` que não mexe nele é legítimo.
        final esperaDepois = RegExp(r'\bawait\b').hasMatch(depoisDoPop);
        final tocaDepois = RegExp(
          '\\b$controlador\\.(text|clear|value|selection)\\b',
        ).hasMatch(depoisDoPop);
        if (esperaDepois && tocaDepois) {
          suspeitos.add('${arquivo.path}:${i + 1} -> $controlador');
        }
      }
    }

    expect(
      suspeitos,
      isEmpty,
      reason:
          'Controlador tocado depois do Navigator.pop, com o descarte já '
          'agendado. Mova o trabalho demorado para depois do showDialog e '
          'leia o texto ANTES de fechar:\n${suspeitos.join('\n')}',
    );
  });

  test('nenhum método descarta controlador logo após await showDialog', () {
    // `await showDialog` volta quando a rota é DESEMPILHADA, com a animação de
    // saída ainda rodando: o campo continua na tela por alguns quadros. Quem
    // descarta ali deixa ele apontando para um objeto morto.
    //
    // O dono dos controladores tem que ser o próprio diálogo — um widget com
    // estado que os descarta no `dispose`, que só roda depois que a rota some.
    // Ver `dialogo_dono_do_controlador_test.dart`.
    final suspeitos = <String>[];

    for (final arquivo in Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))) {
      final linhas = arquivo.readAsLinesSync();
      for (var i = 0; i < linhas.length; i += 1) {
        if (!linhas[i].contains('await showDialog')) continue;
        // Varre só até o fim do MÉTODO que chamou `showDialog` — uma linha
        // com apenas `}` na indentação de membro. Sem esse limite, o
        // `dispose()` correto de um `State` declarado adiante no mesmo arquivo
        // entrava como suspeito.
        for (var j = i + 1; j < linhas.length; j += 1) {
          // Fim do método que chamou `showDialog`: um `}` na margem (função
          // de topo) ou com dois espaços (membro de classe). Sem isto, o
          // `dispose()` CORRETO de um `State` declarado adiante no mesmo
          // arquivo entrava como suspeito.
          if (RegExp(r'^ {0,2}\}').hasMatch(linhas[j])) break;
          final descarte = RegExp(
            r'^\s*([A-Za-z_][A-Za-z0-9_]*)\.dispose\(\);',
          ).firstMatch(linhas[j]);
          if (descarte == null) continue;
          suspeitos.add('${arquivo.path}:${j + 1} -> ${descarte.group(1)}');
          break;
        }
      }
    }

    expect(
      suspeitos,
      isEmpty,
      reason:
          'Controlador descartado logo depois de `await showDialog`, com a '
          'animação de saída ainda rodando. Mova a posse para dentro do '
          'diálogo:\n${suspeitos.join('\n')}',
    );
  });
}
