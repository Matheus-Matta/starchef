import 'package:flutter/material.dart';

import '../widgets/app_sheet.dart';
import 'mobile_release.dart';
import 'mobile_update_service.dart';

/// A folha que baixa o APK e o entrega ao instalador do Android.
///
/// Devolve `true` quando o instalador foi aberto, `null` quando o garçom saiu.
/// NÃO devolve "instalou": quem decide isso é a pessoa, na tela do sistema, e o
/// app pode ser encerrado pelo Android durante a instalação.
Future<bool?> showUpdateDownloadSheet(
  BuildContext context,
  MobileUpdateService service,
  MobileApk apk,
) => showAppSheet<bool>(
  context,
  builder: (_) => _UpdateDownload(service: service, apk: apk),
);

class _UpdateDownload extends StatefulWidget {
  const _UpdateDownload({required this.service, required this.apk});

  final MobileUpdateService service;
  final MobileApk apk;

  @override
  State<_UpdateDownload> createState() => _UpdateDownloadState();
}

class _UpdateDownloadState extends State<_UpdateDownload> {
  double _progresso = 0;
  var _baixando = false;
  String _erro = '';

  /// `false` quando o aparelho não autoriza este app a instalar pacotes.
  bool? _podeInstalar;

  @override
  void initState() {
    super.initState();
    _comecar();
  }

  Future<void> _comecar() async {
    // A PERMISSÃO É CONFERIDA ANTES DO DOWNLOAD. Baixar 25 MB para depois
    // descobrir que o aparelho não instala de fora da Play Store é gastar a rede
    // da loja e o tempo do garçom para chegar a um beco.
    final autorizado = await widget.service.installer.canInstall();
    if (!mounted) return;
    setState(() => _podeInstalar = autorizado);
    if (!autorizado) return;
    await _baixar();
  }

  Future<void> _baixar() async {
    setState(() {
      _baixando = true;
      _erro = '';
      _progresso = 0;
    });
    try {
      final arquivo = await widget.service.download(
        widget.apk,
        onProgress: (valor) {
          if (mounted) setState(() => _progresso = valor.clamp(0, 1));
        },
      );
      final entregou = await widget.service.installer.install(arquivo.path);
      if (!mounted) return;
      if (!entregou) {
        setState(() {
          _baixando = false;
          _erro =
              'O download terminou, mas o Android não abriu o instalador. '
              'Abra o arquivo ${widget.apk.name} na pasta de downloads do aparelho.';
        });
        return;
      }
      Navigator.pop(context, true);
    } catch (falha) {
      if (!mounted) return;
      setState(() {
        _baixando = false;
        // A mensagem do serviço já explica o caso (download incompleto, arquivo
        // que não confere). Trocá-la por "erro ao baixar" perderia o motivo.
        _erro = falha is Exception
            ? '$falha'.replaceFirst(RegExp(r'^\w+Exception:?\s*'), '')
            : '$falha';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSheetHeader(
          title: 'Atualizar o aplicativo',
          subtitle: '${widget.apk.name} · ${widget.apk.sizeLabel}',
        ),
        const SizedBox(height: 12),
        if (_podeInstalar == false)
          _semPermissao(cores)
        else if (_erro.isNotEmpty)
          _comErro(cores)
        else
          _emAndamento(cores),
        const SizedBox(height: 8),
      ],
    );
  }

  Widget _emAndamento(ColorScheme cores) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      LinearProgressIndicator(value: _baixando ? _progresso : null),
      const SizedBox(height: 10),
      Text(
        _baixando
            ? 'Baixando ${(_progresso * 100).toStringAsFixed(0)}%. '
                  'Mantenha o aplicativo aberto.'
            : 'Preparando o download...',
        style: TextStyle(fontSize: 12, color: cores.onSurfaceVariant),
      ),
      const SizedBox(height: 12),
      Text(
        'Ao terminar, o Android vai pedir a confirmação para instalar. '
        'Seus pedidos e a sessão continuam no servidor.',
        style: TextStyle(fontSize: 12, color: cores.onSurfaceVariant),
      ),
    ],
  );

  Widget _comErro(ColorScheme cores) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(_erro, style: TextStyle(color: cores.error)),
      const SizedBox(height: 14),
      FilledButton.icon(
        key: const Key('update-retry'),
        onPressed: _baixar,
        icon: const Icon(Icons.refresh),
        label: const Text('Tentar de novo'),
      ),
    ],
  );

  /// O beco mais comum, e o único que o app não resolve sozinho.
  ///
  /// Instalar de fora da Play Store exige que o aparelho autorize ESTE app. Sem
  /// dizer isso, o garçom vê o instalador abrir e fechar e conclui que o
  /// download falhou — e tenta de novo, no 4G, quantas vezes for preciso.
  Widget _semPermissao(ColorScheme cores) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text(
        'Este aparelho ainda não autoriza o StarChef a instalar atualizações.',
        style: TextStyle(fontWeight: FontWeight.w700, color: cores.error),
      ),
      const SizedBox(height: 6),
      Text(
        'Toque em Autorizar, ligue a permissão para o StarChef e volte aqui.',
        style: TextStyle(fontSize: 12, color: cores.onSurfaceVariant),
      ),
      const SizedBox(height: 14),
      FilledButton.icon(
        key: const Key('update-grant'),
        onPressed: () async {
          await widget.service.installer.openInstallPermission();
          // Reconfere ao voltar: a folha continua aberta, e o garçom acabou de
          // ligar a permissão na tela do sistema.
          if (mounted) await _comecar();
        },
        icon: const Icon(Icons.shield_outlined),
        label: const Text('Autorizar instalação'),
      ),
    ],
  );
}
