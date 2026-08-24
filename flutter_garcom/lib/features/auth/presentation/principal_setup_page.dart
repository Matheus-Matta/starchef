import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_signature.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/labeled_field.dart';
import 'auth_scaffold.dart';
import 'diagnostics_sheet.dart';
import 'session_controller.dart';

/// Pareamento do aparelho com o Caixa Principal — depois do login.
///
/// Vem depois porque a requisição de teste vai assinada com conta, operador e
/// restaurante, que só existem depois de o backend dizer quem é o garçom. E é
/// uma configuração do APARELHO: feita uma vez pelo gerente, sobrevive à troca
/// de garçom no fim do turno.
class PrincipalSetupPage extends StatefulWidget {
  const PrincipalSetupPage({
    super.key,
    required this.controller,
    this.onDone,
  });

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
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 3,
                  child: LabeledField(
                    controller: _host,
                    label: 'IP na rede',
                    hint: '192.168.0.10',
                    icon: Icons.router_outlined,
                    keyboardType: TextInputType.url,
                    textInputAction: TextInputAction.next,
                    validator: (value) =>
                        (value == null || value.trim().isEmpty)
                        ? 'Informe o IP.'
                        : null,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  flex: 2,
                  child: LabeledField(
                    controller: _port,
                    label: 'Porta',
                    hint: '${PrincipalConfig.defaultPort}',
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.next,
                    validator: (value) {
                      final port = int.tryParse((value ?? '').trim());
                      if (port == null || port < 1024 || port > 65535) {
                        return 'Entre 1024 e 65535.';
                      }
                      return null;
                    },
                  ),
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
            ShadButton(
              onPressed: _submit,
              enabled: !controller.loading,
              height: AppTheme.controlHeight,
              leading: controller.loading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.wifi_tethering, size: 18),
              child: Text(
                controller.loading ? 'Testando...' : 'Conectar',
              ),
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
