import 'package:flutter/material.dart';

/// O cabeçalho da tela de clientes: buscar, cadastrar, recarregar.
///
/// Separado da página porque é o que o operador OPERA, enquanto a página
/// cuida do que ela mostra. A pausa de digitação continua na página: ela é
/// quem sabe consultar, e um widget que soubesse disso precisaria conhecer o
/// repositório.
class CustomerSearchBar extends StatelessWidget {
  const CustomerSearchBar({
    super.key,
    required this.controller,
    required this.onChanged,
    required this.onSubmit,
    required this.onClear,
    required this.onNew,
    required this.carregando,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onSubmit;
  final VoidCallback onClear;
  final VoidCallback onNew;
  final bool carregando;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: TextField(
          controller: controller,
          onChanged: onChanged,
          onSubmitted: (_) => onSubmit(),
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.search),
            hintText: 'Buscar por nome, telefone, e-mail ou CPF',
            border: const OutlineInputBorder(),
            suffixIcon: controller.text.isEmpty
                ? null
                : IconButton(
                    tooltip: 'Limpar',
                    icon: const Icon(Icons.close),
                    onPressed: onClear,
                  ),
          ),
        ),
      ),
      const SizedBox(width: 12),
      FilledButton.icon(
        onPressed: onNew,
        icon: const Icon(Icons.person_add_alt_1),
        label: const Text('Novo cliente'),
      ),
      const SizedBox(width: 8),
      IconButton(
        tooltip: 'Atualizar',
        onPressed: carregando ? null : onSubmit,
        icon: const Icon(Icons.refresh),
      ),
    ],
  );
}
