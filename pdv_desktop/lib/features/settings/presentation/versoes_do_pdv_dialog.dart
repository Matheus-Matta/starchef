import 'package:flutter/material.dart';

import '../../../core/update/pdv_auto_updater.dart';
import '../../../core/update/versoes_do_pdv.dart';
import '../../../core/widgets/app_dialog.dart';

/// Escolher a versão do PDV deste terminal: voltar a uma anterior (ou ir a
/// outra) e FICAR nela.
///
/// O PDV fecha e reabre na versão escolhida, pelo mesmo caminho da
/// atualização (`pdv_troca_de_versao.dart`): conferida, trocada com o PDV
/// fechado e desfeita sozinha se não abrir. Escolhida, a versão fica FIXA —
/// a abertura avisa que há outra mais nova, mas não troca — até alguém pedir
/// "Voltar a atualizar sozinho" ou "Buscar atualizações".
class VersoesDoPdvDialog extends StatefulWidget {
  const VersoesDoPdvDialog({super.key, required this.updater});

  final PdvAutoUpdater updater;

  /// Devolve a versão escolhida, `'atualizar'` para soltar a fixação, ou `null`.
  static Future<Object?> show(BuildContext context, PdvAutoUpdater updater) =>
      showDialog<Object>(
        context: context,
        builder: (_) => VersoesDoPdvDialog(updater: updater),
      );

  @override
  State<VersoesDoPdvDialog> createState() => _VersoesDoPdvDialogState();
}

class _VersoesDoPdvDialogState extends State<VersoesDoPdvDialog> {
  late final Future<List<PdvVersaoDisponivel>> _versoes = widget.updater
      .listarVersoes();
  PdvVersaoDisponivel? _escolhida;

  String get _instalada =>
      widget.updater.status?.installed?.version ?? 'desconhecida';

  @override
  Widget build(BuildContext context) {
    final fixada = widget.updater.versaoFixada;
    return AppDialog(
      maxWidth: 520,
      title: const Text('Versão do PDV'),
      content: SizedBox(
        width: 480,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Instalada neste terminal: v$_instalada'),
            if (fixada != null) ...[
              const SizedBox(height: 8),
              _AvisoDaFixada(
                versao: fixada,
                onSoltar: () => Navigator.of(context).pop('atualizar'),
              ),
            ],
            const SizedBox(height: 12),
            const Text(
              'Escolha a versão. O PDV fecha e reabre nela, e fica nela até '
              'alguém pedir para voltar a atualizar.',
            ),
            const SizedBox(height: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: _lista(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: _escolhida == null
              ? null
              : () => Navigator.of(context).pop(_escolhida),
          child: Text(
            _escolhida == null
                ? 'Instalar'
                : 'Instalar v${_escolhida!.version}',
          ),
        ),
      ],
    );
  }

  Widget _lista() => FutureBuilder<List<PdvVersaoDisponivel>>(
    future: _versoes,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) {
        return const Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()),
        );
      }
      if (snapshot.hasError) {
        return Text('Não foi possível listar as versões: ${snapshot.error}');
      }
      final versoes = snapshot.data ?? const [];
      if (versoes.isEmpty) {
        return const Text('Nenhuma outra versão publicada para este terminal.');
      }
      return ListView(
        shrinkWrap: true,
        children: [
          for (final versao in versoes)
            ListTile(
              dense: true,
              selected: _escolhida == versao,
              leading: Icon(
                _escolhida == versao
                    ? Icons.radio_button_checked
                    : Icons.radio_button_off,
              ),
              title: Text('v${versao.version}'),
              subtitle: Text(_descricao(versao)),
              onTap: () => setState(() => _escolhida = versao),
            ),
        ],
      );
    },
  );

  String _descricao(PdvVersaoDisponivel versao) {
    final data = versao.publicadaEm?.toLocal();
    final quando = data == null
        ? ''
        : 'Publicada em ${data.day.toString().padLeft(2, '0')}/'
              '${data.month.toString().padLeft(2, '0')}/${data.year}';
    return quando;
  }
}

class _AvisoDaFixada extends StatelessWidget {
  const _AvisoDaFixada({required this.versao, required this.onSoltar});

  final String versao;
  final VoidCallback onSoltar;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: scheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              'Versão v$versao fixada: este terminal não atualiza sozinho.',
            ),
          ),
          TextButton(
            onPressed: onSoltar,
            child: const Text('Voltar a atualizar sozinho'),
          ),
        ],
      ),
    );
  }
}
