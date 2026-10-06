import 'package:flutter/material.dart';

import '../input/command_code_match.dart';

/// O número da comanda LIDA, em letras grandes, enquanto ela abre.
///
/// A leitura errada (o cartão 17 abrindo a 107) só é percebida quando alguém
/// olha o número pequeno no cabeçalho — depois de já ter lançado. Com o número
/// lido ocupando a tela no instante da leitura, o operador vê na hora.
///
/// Não segura o fluxo: o aviso fica enquanto [trabalho] corre e some com um
/// esmaecimento curto depois, sem esperar nada.
Future<T> mostrandoComandaLida<T>(
  BuildContext context,
  String lido,
  Future<T> Function() trabalho,
) async {
  final overlay = Overlay.maybeOf(context, rootOverlay: true);
  if (overlay == null) return trabalho();
  final saindo = ValueNotifier(false);
  final entrada = OverlayEntry(
    builder: (_) =>
        _AvisoDeComandaLida(numero: numeroLidoParaExibir(lido), saindo: saindo),
  );
  overlay.insert(entrada);
  try {
    return await trabalho();
  } finally {
    saindo.value = true;
    Future<void>.delayed(_AvisoDeComandaLida.esmaecer, () {
      if (entrada.mounted) entrada.remove();
      saindo.dispose();
    });
  }
}

class _AvisoDeComandaLida extends StatelessWidget {
  const _AvisoDeComandaLida({required this.numero, required this.saindo});

  static const esmaecer = Duration(milliseconds: 350);

  final String numero;
  final ValueNotifier<bool> saindo;

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return IgnorePointer(
      child: ValueListenableBuilder<bool>(
        valueListenable: saindo,
        builder: (context, sai, child) => AnimatedOpacity(
          opacity: sai ? 0 : 1,
          duration: esmaecer,
          child: child,
        ),
        child: ColoredBox(
          color: cores.scrim.withValues(alpha: 0.55),
          child: Center(
            child: Material(
              color: cores.surface,
              elevation: 12,
              borderRadius: BorderRadius.circular(28),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 72,
                  vertical: 40,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'COMANDA',
                      style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 6,
                        color: cores.onSurfaceVariant,
                      ),
                    ),
                    FittedBox(
                      child: Text(
                        numero,
                        key: const ValueKey('comanda-lida-numero'),
                        style: TextStyle(
                          fontSize: 160,
                          height: 1.1,
                          fontWeight: FontWeight.w900,
                          color: cores.primary,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const SizedBox.square(
                      dimension: 32,
                      child: CircularProgressIndicator(strokeWidth: 3),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
