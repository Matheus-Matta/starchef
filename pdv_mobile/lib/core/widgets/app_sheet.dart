import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Folha de baixo — o "diálogo" do app do garçom.
///
/// Seis telas abriam `showModalBottomSheet` com a própria combinação de
/// `isScrollControlled`, `SafeArea`, folga de teclado e um `Padding` com o
/// título dentro: cada uma esquecia um pedaço diferente (a de pagamento subia
/// junto com o teclado, a de comanda não; uma tinha 20 de margem, outra 16).
/// Aqui a moldura é uma só e as folhas trazem só o próprio conteúdo.
///
/// [heightFactor] fixa a altura em uma fração da tela — use nas folhas que
/// rolam uma lista longa (catálogo, comandas), onde uma altura que muda a cada
/// página carregada faz a folha "pular" debaixo do dedo. Sem ele, a folha
/// cresce com o conteúdo até [maxHeightFactor].
Future<T?> showAppSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  double? heightFactor,
  double maxHeightFactor = .85,
}) => showModalBottomSheet<T>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  builder: (context) {
    final screen = MediaQuery.of(context).size.height;
    return Padding(
      // Sobe junto com o teclado: sem isto o campo em foco fica atrás dele e o
      // operador digita às cegas.
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SafeArea(
        child: ConstrainedBox(
          constraints: heightFactor != null
              ? BoxConstraints.tightFor(height: screen * heightFactor)
              : BoxConstraints(maxHeight: screen * maxHeightFactor),
          child: builder(context),
        ),
      ),
    );
  },
);

/// Cabeçalho de uma folha: o que ela pergunta, e uma ação opcional.
class AppSheetHeader extends StatelessWidget {
  const AppSheetHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    subtitle!,
                    style: TextStyle(
                      fontSize: 13,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Conteúdo de folha que é uma lista de escolhas — cada opção com ícone,
/// título e explicação, no alvo de toque de [AppTheme.controlHeight].
class AppSheetOption extends StatelessWidget {
  const AppSheetOption({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.description,
  });

  final IconData icon;
  final String label;
  final String? description;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
      leading: Container(
        height: 40,
        width: 40,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: scheme.primary.withValues(alpha: .12),
          borderRadius: AppTheme.radius,
        ),
        child: Icon(icon, color: scheme.primary),
      ),
      title: Text(label),
      subtitle: description == null ? null : Text(description!),
    );
  }
}
