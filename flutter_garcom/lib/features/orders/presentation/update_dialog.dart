import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/update/garcom_update_controller.dart';

/// Aviso de versão nova, na frente de tudo.
///
/// Antes isto era só a faixa no topo da lista ([UpdateBanner]), escolhida para
/// não interromper o atendimento. Na prática o garçom passava direto: a faixa
/// divide espaço com pendências de envio e dados de cache, e ninguém para de
/// atender para ler um aviso fino.
///
/// Atualizar não é opcional — o aparelho conversa com o Caixa Principal por um
/// contrato que muda entre versões, e um salão com aparelhos em versões
/// diferentes é onde nascem os erros caros. Então o aviso abre em cima, com um
/// único botão grande, toda vez que o app encontra versão nova.
///
/// O "Agora não" existe e é de propósito: sem rede, sem espaço ou com o
/// instalador recusado, um diálogo sem saída deixaria o garçom sem conseguir
/// lançar pedido nenhum no meio do serviço. Ele fecha o diálogo, mas a faixa
/// continua ali e o aviso volta na próxima abertura do app.
Future<void> showGarcomUpdateDialog(
  BuildContext context,
  GarcomUpdateController controller,
) => showDialog<void>(
  context: context,
  // Só sai pelo botão: um toque fora não pode dispensar por acidente o que o
  // garçom precisa ler.
  barrierDismissible: false,
  builder: (context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) => _UpdateDialog(controller: controller),
  ),
);

class _UpdateDialog extends StatelessWidget {
  const _UpdateDialog({required this.controller});

  final GarcomUpdateController controller;

  bool get _busy =>
      controller.phase == GarcomUpdateBannerPhase.downloading ||
      controller.phase == GarcomUpdateBannerPhase.readyToInstall;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // O instalador do Android assumiu: o diálogo já cumpriu o papel e sai da
    // frente sozinho.
    if (controller.phase == GarcomUpdateBannerPhase.hidden) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (Navigator.of(context).canPop()) Navigator.of(context).pop();
      });
    }
    return AlertDialog(
      shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
      contentPadding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: .12),
                borderRadius: AppTheme.radius,
              ),
              child: Icon(
                Icons.system_update_alt,
                size: 32,
                color: scheme.primary,
              ),
            ),
          ),
          const SizedBox(height: AppTheme.gapLoose),
          Text(
            'Nova versão disponível',
            textAlign: TextAlign.center,
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: AppTheme.gapTight),
          Text(
            _explanation,
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
          if (controller.phase == GarcomUpdateBannerPhase.downloading) ...[
            const SizedBox(height: AppTheme.gapLoose),
            LinearProgressIndicator(value: controller.progress),
          ],
          const SizedBox(height: 24),
          // O botão ocupa a largura inteira e tem o dobro da altura de um
          // controle comum: é para ser tocado com o aparelho na mão, em pé, no
          // meio do salão — e para não haver dúvida sobre o que fazer aqui.
          ShadButton(
            height: AppTheme.controlHeight * 1.25,
            enabled: !_busy,
            onPressed: controller.downloadAndInstall,
            leading: _busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.4,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.download, size: 22),
            child: Text(
              _buttonLabel,
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
      actionsPadding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
      actions: [
        Center(
          child: TextButton(
            onPressed: _busy ? null : () => Navigator.of(context).pop(),
            child: Text(
              'Agora não',
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
          ),
        ),
      ],
    );
  }

  String get _explanation => switch (controller.phase) {
    GarcomUpdateBannerPhase.failed =>
      controller.detail ?? 'Não foi possível baixar. Tente de novo.',
    GarcomUpdateBannerPhase.downloading =>
      'Baixando. Mantenha o aplicativo aberto até o instalador abrir.',
    GarcomUpdateBannerPhase.readyToInstall =>
      'Abrindo o instalador do Android. Confirme para concluir.',
    _ =>
      'Atualize antes de continuar atendendo: aparelhos em versões diferentes '
          'conversam de formas diferentes com o Caixa Principal.',
  };

  String get _buttonLabel => switch (controller.phase) {
    GarcomUpdateBannerPhase.downloading => 'Baixando...',
    GarcomUpdateBannerPhase.readyToInstall => 'Abrindo instalador...',
    GarcomUpdateBannerPhase.failed => 'Tentar de novo',
    _ => 'Baixar e instalar',
  };
}
