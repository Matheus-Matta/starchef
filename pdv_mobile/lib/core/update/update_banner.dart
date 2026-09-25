import 'package:flutter/material.dart';

import 'mobile_release.dart';
import 'mobile_update_service.dart';
import 'update_download_sheet.dart';

/// O aviso de versão nova, com o botão de baixar.
///
/// AVISA, NÃO BLOQUEIA. No celular do garçom, no meio do almoço, travar o
/// atendimento para baixar 25 MB é pior do que continuar na versão anterior: ele
/// está em pé na frente do cliente. Quem escolhe o momento é ele.
///
/// Só aparece quando há versão nova. Um banner permanente dizendo "você está
/// atualizado" vira ruído que ninguém lê — e no dia em que virar aviso de
/// verdade, ninguém vai ler também.
class UpdateBanner extends StatefulWidget {
  const UpdateBanner({super.key, this.service, this.padding});

  /// Injetável para teste. Em produção nasce aqui e é descartado no `dispose`.
  final MobileUpdateService? service;
  final EdgeInsets? padding;

  @override
  State<UpdateBanner> createState() => _UpdateBannerState();
}

class _UpdateBannerState extends State<UpdateBanner> {
  late final MobileUpdateService _service =
      widget.service ?? MobileUpdateService();
  MobileUpdateStatus? _status;
  var _dispensado = false;

  @override
  void initState() {
    super.initState();
    _checar();
  }

  @override
  void dispose() {
    // Só descarta o que criou: um serviço injetado pertence a quem o passou.
    if (widget.service == null) _service.dispose();
    super.dispose();
  }

  Future<void> _checar() async {
    final resultado = await _service.check();
    if (!mounted) return;
    setState(() => _status = resultado);
  }

  Future<void> _baixar(MobileApk apk) async {
    final instalou = await showUpdateDownloadSheet(context, _service, apk);
    // Entregue ao instalador: o app pode ser encerrado a qualquer momento pelo
    // sistema durante a instalação, então não há estado "depois" para guardar.
    if (instalou == true && mounted) setState(() => _dispensado = true);
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    if (_dispensado || status == null || !status.hasUpdate) {
      return const SizedBox.shrink();
    }
    final cores = Theme.of(context).colorScheme;
    final apk = status.apk!;
    return Padding(
      padding: widget.padding ?? const EdgeInsets.only(bottom: 14),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: cores.primary.withValues(alpha: .10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: cores.primary.withValues(alpha: .45)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.system_update, size: 18, color: cores.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Versão ${status.release!.version} disponível',
                    style: TextStyle(
                      fontWeight: FontWeight.w800,
                      color: cores.primary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 2),
            // O TAMANHO APARECE porque é o que decide "agora ou depois". Sem
            // ele, o garçom toca em baixar no 4G sem saber que são 69 MB.
            Text(
              'Você está na ${status.installed.isEmpty ? '—' : status.installed}. '
              'O download tem ${apk.sizeLabel}.',
              style: TextStyle(fontSize: 12, color: cores.onSurfaceVariant),
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    key: const Key('update-download'),
                    onPressed: () => _baixar(apk),
                    icon: const Icon(Icons.download, size: 18),
                    label: const Text('Baixar e instalar'),
                  ),
                ),
                const SizedBox(width: 8),
                // "Depois" existe para o aviso não virar obstáculo. Ele volta no
                // próximo início do app: dispensar não é recusar a atualização.
                TextButton(
                  key: const Key('update-later'),
                  onPressed: () => setState(() => _dispensado = true),
                  child: const Text('Depois'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
