import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/copyable_error.dart';
import '../printing/printer.dart';
import '../printing/printer_device.dart';
import '../printing/printer_transport.dart';

/// Os dois botões que provam o equipamento antes de a venda depender dele.
///
/// Saíram da tela de cadastro por assunto: aquela monta e salva o formulário,
/// estes falam com o hardware. O cadastro chega por [buildPrinter] como está
/// NA TELA, ainda não salvo — quem clicou acabou de trocar o IP e quer saber
/// se a troca funciona.
class PrinterTestActions extends StatefulWidget {
  const PrinterTestActions({
    super.key,
    required this.api,
    required this.token,
    required this.buildPrinter,
    this.printerId,
    this.enabled = true,
  });

  final ApiClient api;
  final String token;

  /// Recebe o cadastro que veio junto do trabalho, e a tela ganha dele.
  final Map<String, dynamic> Function([Map<String, dynamic> apiPrinter])
  buildPrinter;

  /// `null` sem cadastro: sem id não há nota para o servidor renderizar, mas
  /// a gaveta continua testável.
  final String? printerId;

  final bool enabled;

  @override
  State<PrinterTestActions> createState() => _PrinterTestActionsState();
}

class _PrinterTestActionsState extends State<PrinterTestActions> {
  bool testing = false;
  bool testingDrawer = false;

  bool get _busy => testing || testingDrawer || !widget.enabled;

  /// Manda o pulso da gaveta e nada mais.
  ///
  /// Não passa pelo servidor: não há cupom para renderizar, e o que se quer
  /// provar é o trecho final do caminho — da ligação cadastrada na tela até o
  /// conector RJ12. Também não gasta papel. Sai mesmo sem gaveta nenhuma
  /// cadastrada; ver `PrinterEndpoint.canOpenCashDrawer`.
  Future<void> _testCashDrawer() async {
    if (_busy) return;
    setState(() => testingDrawer = true);
    try {
      await TestPrinter(
        PrinterDevice.fromJson(widget.buildPrinter()),
      ).openCashDrawer();
      if (mounted) {
        showAppToast(
          context,
          'Pulso enviado à impressora. Se a gaveta não abriu, confira o cabo '
          'RJ12 e o pino do conector.',
          title: 'Gaveta acionada',
        );
      }
    } catch (error) {
      if (mounted) _falhou(error, 'Não foi possível enviar o pulso da gaveta');
    } finally {
      if (mounted) setState(() => testingDrawer = false);
    }
  }

  Future<void> _testPrinter() async {
    final printerId = widget.printerId;
    if (printerId == null || _busy) return;
    setState(() => testing = true);
    Map<String, dynamic>? job;
    try {
      // Sem a nota do servidor não há o que escrever na porta. Este terminal
      // não monta documento nenhum — um teste que imprimisse um texto
      // inventado aqui não provaria o que o operador quer provar: que o
      // caminho inteiro, do servidor ao papel, está de pé.
      job = await widget.api.post(
        '/printers/$printerId/test-connection/',
        body: const {},
        accessToken: widget.token,
      );
      final payload = job['payload'] as Map<String, dynamic>? ?? const {};
      final text = '${payload['text_content'] ?? ''}'.trim();
      if (text.isEmpty) {
        throw const ApiException(
          'O servidor não devolveu o conteúdo da nota de teste.',
        );
      }
      // Mesma classe de impressora do resto do PDV: se sai aqui, sai igual na
      // venda. E leva o pulso junto, no mesmo trabalho — o caminho completo,
      // do servidor ao papel e à gaveta.
      final tester = TestPrinter(
        PrinterDevice.fromJson(
          widget.buildPrinter(
            job['printer'] as Map<String, dynamic>? ?? const {},
          ),
        ),
      );
      await tester.send(tester.compose(content: text, openCashDrawer: true));
      final jobId = job['print_job_id'];
      if (jobId != null) {
        await widget.api.post(
          '/print-jobs/$jobId/mark-printed/',
          body: const {},
          accessToken: widget.token,
        );
      }
    } catch (error) {
      await _avisarQueFalhou(job?['print_job_id'], error);
      if (mounted) _falhou(error, 'Não foi possível imprimir a nota de teste');
    } finally {
      if (mounted) setState(() => testing = false);
    }
  }

  /// Deixar o trabalho pendente o faria voltar pela fila muito depois de quem
  /// clicou ter ido embora.
  Future<void> _avisarQueFalhou(Object? jobId, Object error) async {
    if (jobId == null) return;
    try {
      await widget.api.post(
        '/print-jobs/$jobId/mark-failed/',
        body: {'error': 'Falha no teste local: $error'},
        accessToken: widget.token,
      );
    } catch (_) {}
  }

  void _falhou(Object error, String title) => showAppError(
    context,
    error is PrinterCommunicationException ? error.message : error,
    title: title,
    recommendedAction: error is PrinterCommunicationException
        ? error.recommendedAction
        : 'Confira o endereço da impressora e se ela está ligada.',
  );

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (widget.printerId != null) ...[
        _botao(
          onPressed: _testPrinter,
          carregando: testing,
          icone: Icons.print_outlined,
          rotulo: 'Testar conexão e imprimir nota',
        ),
        const SizedBox(height: 12),
      ],
      _botao(
        onPressed: _testCashDrawer,
        carregando: testingDrawer,
        icone: Icons.point_of_sale_outlined,
        rotulo: 'Testar gaveta de dinheiro',
      ),
      const SizedBox(height: 6),
      Text(
        'Envia só o pulso de abertura pela ligação configurada acima, sem '
        'imprimir nada. É o mesmo comando que sai junto do recibo de uma '
        'venda em dinheiro.',
        style: TextStyle(
          fontSize: 12,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    ],
  );

  Widget _botao({
    required VoidCallback onPressed,
    required bool carregando,
    required IconData icone,
    required String rotulo,
  }) => SizedBox(
    width: double.infinity,
    height: 50,
    child: OutlinedButton.icon(
      onPressed: _busy ? null : onPressed,
      icon: carregando
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Icon(icone),
      label: Text(rotulo),
    ),
  );
}
