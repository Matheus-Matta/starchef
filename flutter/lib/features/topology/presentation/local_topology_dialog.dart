import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../data/local_topology_store.dart';
import '../domain/local_topology_config.dart';
import '../services/local_topology_service.dart';

Future<LocalTopologyConfig?> showLocalTopologyDialog({
  required BuildContext context,
  required LocalTopologyConfig config,
  required LocalTopologyStatus status,
  required bool canEdit,
}) => showDialog<LocalTopologyConfig>(
  context: context,
  builder: (_) =>
      _LocalTopologyDialog(initial: config, status: status, canEdit: canEdit),
);

class _LocalTopologyDialog extends StatefulWidget {
  const _LocalTopologyDialog({
    required this.initial,
    required this.status,
    required this.canEdit,
  });

  final LocalTopologyConfig initial;
  final LocalTopologyStatus status;
  final bool canEdit;

  @override
  State<_LocalTopologyDialog> createState() => _LocalTopologyDialogState();
}

class _LocalTopologyDialogState extends State<_LocalTopologyDialog> {
  late LocalTopologyMode mode = widget.initial.mode;
  late final hostController = TextEditingController(
    text: widget.initial.principalHost,
  );
  late final portController = TextEditingController(
    text: '${widget.initial.port}',
  );
  late final secretController = TextEditingController(
    text: widget.initial.pairingSecret,
  );
  late bool trustedNetwork = widget.initial.trustedNetworkAcknowledged;
  bool obscureSecret = true;
  List<String> errors = const [];

  @override
  void dispose() {
    hostController.dispose();
    portController.dispose();
    secretController.dispose();
    super.dispose();
  }

  void _save() {
    final parsedPort = int.tryParse(portController.text.trim());
    if (parsedPort == null) {
      setState(() => errors = const ['Informe uma porta válida.']);
      return;
    }
    final candidate = LocalTopologyConfig(
      mode: mode,
      nodeId: widget.initial.nodeId,
      principalHost: hostController.text.trim(),
      port: parsedPort,
      pairingSecret: secretController.text.trim(),
      trustedNetworkAcknowledged: trustedNetwork,
    );
    final validation = candidate.validate();
    if (validation.isNotEmpty) {
      setState(() => errors = validation);
      return;
    }
    Navigator.pop(context, candidate);
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final scheme = Theme.of(context).colorScheme;
    return Material(
      type: MaterialType.transparency,
      child: ShadDialog(
        padding: EdgeInsets.zero,
        radius: AppTheme.radius,
        shadows: const [],
        constraints: BoxConstraints(
          maxWidth: 680,
          maxHeight: media.size.height - 40,
        ),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        child: Material(
          type: MaterialType.transparency,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: 680,
              maxHeight: media.size.height - 40,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 22, 16, 16),
                  child: Row(
                    children: [
                      Container(
                        width: 46,
                        height: 46,
                        decoration: BoxDecoration(
                          color: scheme.primaryContainer,
                          borderRadius: AppTheme.radius,
                        ),
                        child: Icon(Icons.hub_outlined, color: scheme.primary),
                      ),
                      const SizedBox(width: 13),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Rede local de caixas',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                            Text(
                              'Relay offline controlado · versão inicial',
                              style: TextStyle(fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        tooltip: 'Fechar',
                        onPressed: () => Navigator.pop(context),
                        icon: const Icon(Icons.close),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                Flexible(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _StatusCard(status: widget.status),
                        const SizedBox(height: 20),
                        const Text(
                          'Função desta estação',
                          style: TextStyle(fontWeight: FontWeight.w900),
                        ),
                        const SizedBox(height: 9),
                        for (final value in LocalTopologyMode.values) ...[
                          _ModeCard(
                            mode: value,
                            selected: mode == value,
                            enabled: widget.canEdit,
                            onTap: () => setState(() {
                              mode = value;
                              errors = const [];
                            }),
                          ),
                          const SizedBox(height: 8),
                        ],
                        ...[
                          const SizedBox(height: 12),
                          if (mode == LocalTopologyMode.client) ...[
                            TextField(
                              controller: hostController,
                              enabled: widget.canEdit,
                              onChanged: (_) =>
                                  setState(() => errors = const []),
                              decoration: const InputDecoration(
                                labelText: 'IP ou nome do Caixa Principal',
                                prefixIcon: Icon(Icons.dns_outlined),
                                hintText: '192.168.1.10',
                              ),
                            ),
                            const SizedBox(height: 12),
                          ],
                          TextField(
                            controller: portController,
                            enabled: widget.canEdit,
                            onChanged: (_) => setState(() => errors = const []),
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            decoration: const InputDecoration(
                              labelText: 'Porta do relay',
                              prefixIcon: Icon(Icons.settings_ethernet),
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: secretController,
                            enabled: widget.canEdit,
                            obscureText: obscureSecret,
                            autocorrect: false,
                            enableSuggestions: false,
                            onChanged: (_) => setState(() => errors = const []),
                            decoration: InputDecoration(
                              labelText: 'Chave de pareamento',
                              prefixIcon: const Icon(Icons.key_outlined),
                              suffixIcon: IconButton(
                                tooltip: obscureSecret ? 'Mostrar' : 'Ocultar',
                                onPressed: widget.canEdit
                                    ? () => setState(
                                        () => obscureSecret = !obscureSecret,
                                      )
                                    : null,
                                icon: Icon(
                                  obscureSecret
                                      ? Icons.visibility_outlined
                                      : Icons.visibility_off_outlined,
                                ),
                              ),
                            ),
                          ),
                          if (widget.canEdit) ...[
                            const SizedBox(height: 8),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: [
                                if (mode == LocalTopologyMode.principal)
                                  OutlinedButton.icon(
                                    onPressed: () => setState(() {
                                      secretController.text =
                                          LocalTopologyStore.generatePairingSecret();
                                      errors = const [];
                                    }),
                                    style: OutlinedButton.styleFrom(
                                      minimumSize: const Size(0, 52),
                                    ),
                                    icon: const Icon(Icons.autorenew),
                                    label: const Text('Gerar chave'),
                                  ),
                                OutlinedButton.icon(
                                  onPressed:
                                      secretController.text.trim().isEmpty
                                      ? null
                                      : () async {
                                          await Clipboard.setData(
                                            ClipboardData(
                                              text: secretController.text
                                                  .trim(),
                                            ),
                                          );
                                          if (context.mounted) {
                                            ScaffoldMessenger.of(
                                              context,
                                            ).showSnackBar(
                                              const SnackBar(
                                                content: Text(
                                                  'Chave copiada com segurança.',
                                                ),
                                              ),
                                            );
                                          }
                                        },
                                  style: OutlinedButton.styleFrom(
                                    minimumSize: const Size(0, 52),
                                  ),
                                  icon: const Icon(Icons.copy_outlined),
                                  label: const Text('Copiar'),
                                ),
                                if (mode == LocalTopologyMode.client)
                                  OutlinedButton.icon(
                                    onPressed: () async {
                                      final data = await Clipboard.getData(
                                        Clipboard.kTextPlain,
                                      );
                                      final value = data?.text?.trim() ?? '';
                                      if (value.isNotEmpty && mounted) {
                                        setState(() {
                                          secretController.text = value;
                                          errors = const [];
                                        });
                                      }
                                    },
                                    style: OutlinedButton.styleFrom(
                                      minimumSize: const Size(0, 52),
                                    ),
                                    icon: const Icon(Icons.content_paste),
                                    label: const Text('Colar'),
                                  ),
                              ],
                            ),
                          ],
                          const SizedBox(height: 12),
                          CheckboxListTile(
                            value: trustedNetwork,
                            enabled: widget.canEdit,
                            contentPadding: EdgeInsets.zero,
                            controlAffinity: ListTileControlAffinity.leading,
                            title: const Text(
                              'Confirmo que os caixas estão em uma rede privada e confiável',
                              style: TextStyle(fontWeight: FontWeight.w800),
                            ),
                            subtitle: const Text(
                              'As mensagens têm assinatura HMAC e proteção contra '
                              'replay, mas esta versão ainda não inclui TLS.',
                            ),
                            onChanged: (value) =>
                                setState(() => trustedNetwork = value ?? false),
                          ),
                          Container(
                            margin: const EdgeInsets.only(top: 8),
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: scheme.tertiaryContainer,
                              borderRadius: AppTheme.radius,
                            ),
                            child: const Text(
                              'Por segurança de auditoria, Cliente e Principal '
                              'precisam estar autenticados com o mesmo operador e '
                              'no mesmo restaurante. Clientes e pagamentos não são '
                              'encaminhados por esta versão.',
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                          ),
                        ],
                        if (errors.isNotEmpty)
                          Container(
                            margin: const EdgeInsets.only(top: 16),
                            padding: const EdgeInsets.all(13),
                            decoration: BoxDecoration(
                              color: scheme.errorContainer,
                              borderRadius: AppTheme.radius,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                for (final error in errors)
                                  Text(
                                    '• $error',
                                    style: TextStyle(
                                      color: scheme.onErrorContainer,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        if (!widget.canEdit)
                          Padding(
                            padding: const EdgeInsets.only(top: 16),
                            child: Text(
                              'Seu perfil pode consultar, mas não alterar a rede local.',
                              style: TextStyle(color: scheme.onSurfaceVariant),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
                  child: Wrap(
                    alignment: WrapAlignment.end,
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        style: TextButton.styleFrom(
                          minimumSize: const Size(0, 52),
                        ),
                        child: const Text('Cancelar'),
                      ),
                      if (widget.canEdit)
                        FilledButton.icon(
                          onPressed: _save,
                          style: FilledButton.styleFrom(
                            minimumSize: const Size(0, 52),
                          ),
                          icon: const Icon(Icons.save_outlined),
                          label: const Text('Salvar e aplicar'),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.status});

  final LocalTopologyStatus status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ready = status.ready;
    final background = ready
        ? scheme.tertiaryContainer
        : scheme.surfaceContainer;
    final foreground = ready
        ? scheme.onTertiaryContainer
        : scheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: AppTheme.radius,
      ),
      child: Row(
        children: [
          Icon(
            ready ? Icons.lan_outlined : Icons.link_off_outlined,
            color: foreground,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  status.message,
                  style: TextStyle(
                    color: foreground,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (status.addresses.isNotEmpty)
                  Text(
                    status.addresses.join(' · '),
                    style: TextStyle(color: foreground, fontSize: 11),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  const _ModeCard({
    required this.mode,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final LocalTopologyMode mode;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (icon, description) = switch (mode) {
      LocalTopologyMode.principal => (
        Icons.dns_outlined,
        'Guarda os dados da loja e é quem sincroniza com a nuvem.',
      ),
      LocalTopologyMode.client => (
        Icons.point_of_sale_outlined,
        'Lê e grava no Caixa Principal, que cuida da nuvem.',
      ),
    };
    return Material(
      color: selected ? scheme.primaryContainer : scheme.surface,
      borderRadius: AppTheme.radius,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: AppTheme.radius,
        child: Container(
          constraints: const BoxConstraints(minHeight: 68),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            borderRadius: AppTheme.radius,
            border: Border.all(
              color: selected ? scheme.primary : scheme.outlineVariant,
              width: selected ? 1.5 : 1,
            ),
          ),
          child: Row(
            children: [
              Icon(icon, color: selected ? scheme.primary : null),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      mode.label,
                      style: const TextStyle(fontWeight: FontWeight.w900),
                    ),
                    Text(description, style: const TextStyle(fontSize: 12)),
                  ],
                ),
              ),
              Icon(
                selected ? Icons.radio_button_checked : Icons.radio_button_off,
                color: selected ? scheme.primary : scheme.outline,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
