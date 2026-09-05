import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_signature.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/labeled_field.dart';
import '../../../core/widgets/shadcn_layout.dart';
import 'auth_scaffold.dart';
import 'diagnostics_sheet.dart';
import 'principal_qr_scanner_page.dart';
import 'session_controller.dart';

/// Pareamento do aparelho com o Caixa Principal — depois do login.
///
/// Vem depois porque a requisição de teste vai assinada com conta, operador e
/// restaurante, que só existem depois de o backend dizer quem é o garçom. E é
/// uma configuração do APARELHO: feita uma vez pelo gerente, sobrevive à troca
/// de garçom no fim do turno.
class PrincipalSetupPage extends StatefulWidget {
  const PrincipalSetupPage({super.key, required this.controller, this.onDone});

  final SessionController controller;

  /// Quando vem de dentro do app ("Trocar caixa"), fecha a tela no sucesso.
  /// No primeiro pareamento é nulo: quem troca de tela é o roteamento.
  final VoidCallback? onDone;

  @override
  State<PrincipalSetupPage> createState() => _PrincipalSetupPageState();
}

class _PrincipalSetupPageState extends State<PrincipalSetupPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _host;
  late final TextEditingController _port;
  late final TextEditingController _secret;
  bool _hideSecret = true;

  @override
  void initState() {
    super.initState();
    // Trocar o caixa quase sempre é ajustar o IP, não redigitar tudo.
    final current = widget.controller.principal;
    _host = TextEditingController(text: current?.host ?? '');
    _port = TextEditingController(
      text: '${current?.port ?? PrincipalConfig.defaultPort}',
    );
    _secret = TextEditingController(text: current?.secret ?? '');
  }

  @override
  void dispose() {
    _host.dispose();
    _port.dispose();
    _secret.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (widget.controller.loading) return;
    if (!(_formKey.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    final paired = await widget.controller.pair(
      host: _host.text,
      port: _port.text,
      secret: _secret.text,
    );
    if (paired && mounted) widget.onDone?.call();
  }

  /// Lê o QR Code mostrado no PDV (Configurações → Rede local) e preenche
  /// IP, porta e chave sozinho — em vez de o gerente ditar cada campo.
  Future<void> _scanQrCode() async {
    if (widget.controller.loading) return;
    FocusScope.of(context).unfocus();
    final scanned = await showPrincipalQrScannerPage(context);
    if (scanned == null || !mounted) return;
    setState(() {
      _host.text = scanned.host;
      if (scanned.port != null) _port.text = '${scanned.port}';
      _secret.text = scanned.secret;
    });
  }

  /// Testa a ligação com o que está digitado AGORA, sem gravar nada.
  ///
  /// É o caminho para descobrir por que "não conecta": o resultado separa rede
  /// bloqueada de porta fechada e de recusa do caixa — três problemas com
  /// culpados diferentes que hoje apareciam como a mesma frase.
  Future<void> _diagnose() async {
    final session = widget.controller.session;
    if (session == null) return;
    FocusScope.of(context).unfocus();
    await showPrincipalDiagnostics(
      context,
      client: widget.controller.principalClient,
      config: PrincipalConfig(
        host: _host.text.trim(),
        port: int.tryParse(_port.text.trim()) ?? PrincipalConfig.defaultPort,
        secret: _secret.text.trim(),
        // O aparelho pode ainda não ter identidade no relay (primeiro
        // pareamento): uma provisória serve, o teste não grava nada.
        nodeId:
            widget.controller.principal?.nodeId ?? RelaySignature.randomId(),
      ),
      identity: session.identity,
    );
  }

  /// A porta do relay é sempre alta: abaixo de 1024 o sistema operacional
  /// reserva para serviços do próprio computador.
  static String? _validatePort(String? value) {
    final port = int.tryParse((value ?? '').trim());
    if (port == null || port < 1024 || port > 65535) {
      return 'Entre 1024 e 65535.';
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final name = controller.session?.user.displayName ?? '';
    final restaurant = controller.session?.user.restaurantName ?? '';
    return AuthScaffold(
      title: 'Conectar ao caixa',
      subtitle: restaurant.isEmpty
          ? 'Olá, $name. Falta dizer para onde vão os pedidos.'
          : 'Olá, $name. Aponte este aparelho para o caixa do $restaurant.',
      error: controller.error,
      footnote:
          'O pedido tirado aqui é gravado e impresso pelo Caixa Principal. '
          'Peça o IP e a senha ao gerente — em Configurações → Rede local, '
          'no PDV.',
      action: widget.onDone == null
          ? ShadButton.ghost(
              onPressed: controller.loading ? null : controller.logout,
              child: const Text('Entrar com outro usuário'),
            )
          : ShadButton.ghost(
              onPressed: controller.loading
                  ? null
                  : () => Navigator.of(context).maybePop(),
              child: const Text('Cancelar'),
            ),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AppResponsiveFields(
              flex: const [3, 2],
              children: [
                LabeledField(
                  controller: _host,
                  label: 'IP na rede',
                  hint: '192.168.0.10',
                  icon: Icons.router_outlined,
                  keyboardType: TextInputType.url,
                  textInputAction: TextInputAction.next,
                  validator: (value) => (value == null || value.trim().isEmpty)
                      ? 'Informe o IP.'
                      : null,
                ),
                LabeledField(
                  controller: _port,
                  label: 'Porta',
                  hint: '${PrincipalConfig.defaultPort}',
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.next,
                  validator: _validatePort,
                ),
              ],
            ),
            const SizedBox(height: 14),
            LabeledField(
              controller: _secret,
              label: 'Senha do Caixa Principal',
              hint: 'chave de pareamento',
              icon: Icons.key_outlined,
              obscureText: _hideSecret,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _submit(),
              validator: (value) => (value == null || value.trim().isEmpty)
                  ? 'Informe a senha do caixa.'
                  : null,
              suffix: IconButton(
                tooltip: _hideSecret ? 'Mostrar' : 'Ocultar',
                icon: Icon(
                  _hideSecret
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                  size: 20,
                ),
                onPressed: () => setState(() => _hideSecret = !_hideSecret),
              ),
            ),
            const SizedBox(height: 20),
            AppSubmitButton(
              label: 'Conectar',
              busyLabel: 'Testando...',
              icon: Icons.wifi_tethering,
              busy: controller.loading,
              onPressed: _submit,
            ),
            const SizedBox(height: 8),
            ShadButton.outline(
              onPressed: controller.loading ? null : _scanQrCode,
              height: AppTheme.controlHeight,
              leading: const Icon(Icons.qr_code_scanner_outlined, size: 18),
              child: const Text('Ler QR Code'),
            ),
            const SizedBox(height: 8),
            ShadButton.ghost(
              onPressed: controller.loading ? null : _diagnose,
              leading: const Icon(Icons.troubleshoot, size: 18),
              child: const Text('Testar conexão'),
            ),
          ],
        ),
      ),
    );
  }
}
