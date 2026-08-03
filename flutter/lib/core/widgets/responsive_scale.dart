import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Escala a interface inteira — texto, ícones, espaçamento, tudo junto —
/// conforme o tamanho da janela, em vez de só o texto crescer sozinho.
///
/// Antes só o texto era ampliado (via `textScaler`), e nunca encolhia abaixo
/// de 1,04×. Como as alturas de linha, célula de grade etc. são fixas em
/// pixels, um texto que cresce sem o contêiner ao redor é exatamente o
/// padrão do estouro de poucos pixels que se repetiu a sessão inteira — cada
/// correção pontual só empurrava a margem, sem tratar a causa. Fazendo o
/// layout inteiro numa resolução de referência e só depois encaixando o
/// resultado no espaço real, texto e contêiner sempre crescem ou encolhem na
/// mesma proporção, então a margem entre os dois nunca muda: numa janela
/// menor a interface toda encolhe (zoom out) e numa maior ela cresce um
/// pouco, sem que nada estoure.
class ResponsiveScale extends StatelessWidget {
  const ResponsiveScale({
    super.key,
    required this.child,
    this.referenceSize = const Size(1280, 800),
    this.minScale = 0.72,
    this.maxScale = 1.3,
  });

  final Widget child;

  /// Tamanho em que as telas do PDV foram desenhadas — o padrão da janela
  /// principal (ver `WindowOptions` em `main.dart`). Abaixo disso a
  /// interface encolhe; acima, cresce; sempre proporcionalmente.
  final Size referenceSize;

  final double minScale;
  final double maxScale;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // O espaço disponível de verdade aqui — não o tamanho da janela
        // inteira. `MediaQuery.size` reportaria a janela toda, mas quem
        // envolve este widget (a barra de título, por exemplo) já consumiu
        // parte dela; usar o tamanho da janela nesse caso faz a interface
        // ser desenhada maior do que o espaço restante e cortar a borda.
        // `LayoutBuilder` sempre reflete o que sobrou de verdade, não
        // importa quem já consumiu espaço acima.
        final available = constraints.biggest;
        if (!available.width.isFinite ||
            !available.height.isFinite ||
            available.isEmpty) {
          return child;
        }

        final scaleByWidth = available.width / referenceSize.width;
        final scaleByHeight = available.height / referenceSize.height;
        // O menor dos dois: numa janela larga e baixa (ou estreita e alta),
        // é a dimensão mais apertada que decide, senão a interface vaza pela
        // outra.
        final scale = math.min(
          scaleByWidth,
          scaleByHeight,
        ).clamp(minScale, maxScale);

        // O filho enxerga um espaço "virtual" maior ou menor que o real — na
        // proporção inversa da escala — e faz o layout normalmente nesse
        // espaço, como se estivesse no tamanho de referência. O `FittedBox`
        // reporta ao pai exatamente `available` como seu tamanho (nunca mais
        // que isso, então nunca corta) e só reduz/amplia visualmente o
        // conteúdo já pronto para caber ali — diferente de um
        // `Transform.scale` isolado, que manteria o tamanho de layout do
        // filho (o virtual, não o real) e deixaria o pai cortar a sobra.
        final virtualSize = Size(
          available.width / scale,
          available.height / scale,
        );

        return MediaQuery(
          data: MediaQuery.of(context).copyWith(size: virtualSize),
          child: FittedBox(
            fit: BoxFit.fill,
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: virtualSize.width,
              height: virtualSize.height,
              child: child,
            ),
          ),
        );
      },
    );
  }
}
