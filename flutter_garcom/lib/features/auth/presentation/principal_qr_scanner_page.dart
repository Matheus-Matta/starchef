import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

/// Dados de pareamento lidos do QR Code mostrado pelo Caixa Principal.
class ScannedPrincipal {
  const ScannedPrincipal({required this.host, this.port, required this.secret});

  final String host;
  final int? port;
  final String secret;
}

/// Abre a câmera e devolve os dados assim que reconhece um QR Code válido.
///
/// O Caixa Principal (Configurações → Rede local) mostra um QR com
/// `{"host": "...", "port": ..., "secret": "..."}` — o mesmo formato que este
/// leitor espera. Um código com formato diferente (QR de outra coisa
/// qualquer, por exemplo) é ignorado silenciosamente: a câmera continua
/// escaneando em vez de travar numa mensagem de erro sobre um código que o
/// garçom nem tentou usar aqui.
Future<ScannedPrincipal?> showPrincipalQrScannerPage(BuildContext context) =>
    Navigator.of(context).push<ScannedPrincipal>(
      MaterialPageRoute(builder: (_) => const _PrincipalQrScannerPage()),
    );

class _PrincipalQrScannerPage extends StatefulWidget {
  const _PrincipalQrScannerPage();

  @override
  State<_PrincipalQrScannerPage> createState() =>
      _PrincipalQrScannerPageState();
}

class _PrincipalQrScannerPageState extends State<_PrincipalQrScannerPage> {
  final _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  bool _handled = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_handled) return;
    for (final barcode in capture.barcodes) {
      final parsed = _parse(barcode.rawValue);
      if (parsed != null) {
        _handled = true;
        Navigator.of(context).pop(parsed);
        return;
      }
    }
  }

  static ScannedPrincipal? _parse(String? raw) {
    final value = raw?.trim();
    if (value == null || value.isEmpty) return null;
    try {
      final decoded = jsonDecode(value);
      if (decoded is! Map) return null;
      final host = '${decoded['host'] ?? ''}'.trim();
      if (host.isEmpty) return null;
      final secret = '${decoded['secret'] ?? ''}'.trim();
      if (secret.isEmpty) return null;
      final port = int.tryParse('${decoded['port'] ?? ''}');
      return ScannedPrincipal(host: host, port: port, secret: secret);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.black,
    appBar: AppBar(
      backgroundColor: Colors.black,
      foregroundColor: Colors.white,
      title: const Text('Ler QR Code do caixa'),
      actions: [
        IconButton(
          tooltip: 'Lanterna',
          onPressed: () => _controller.toggleTorch(),
          icon: const Icon(Icons.flash_on_outlined),
        ),
      ],
    ),
    body: Stack(
      fit: StackFit.expand,
      children: [
        MobileScanner(controller: _controller, onDetect: _onDetect),
        Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            color: Colors.black54,
            child: const Text(
              'Aponte para o QR Code em Configurações → Rede local, no PDV.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ],
    ),
    floatingActionButton: ShadButton.ghost(
      onPressed: () => Navigator.of(context).maybePop(),
      child: const Text('Cancelar', style: TextStyle(color: Colors.white)),
    ),
  );
}
