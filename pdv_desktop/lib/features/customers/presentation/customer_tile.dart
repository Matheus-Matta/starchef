import 'package:flutter/material.dart';

/// Uma linha da lista de clientes.
///
/// Separada da página porque são duas perguntas: a página resolve BUSCAR
/// (consulta, pausa de digitação, estados vazios) e a linha resolve MOSTRAR.
/// Quando o cadastro ganhar um campo novo, é aqui que ele aparece — sem
/// passar pela lógica de busca.
class CustomerTile extends StatelessWidget {
  const CustomerTile({super.key, required this.customer, required this.onEdit});

  final Map<String, dynamic> customer;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final grupos = (customer['group_names'] as List?)?.cast<String>() ?? const [];
    final inativo = customer['is_active'] == false;
    return ListTile(
      leading: CircleAvatar(child: Text(_inicial('${customer['name'] ?? '?'}'))),
      title: Text(
        '${customer['name'] ?? ''}',
        style: TextStyle(
          decoration: inativo ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Text(_contato()),
      trailing: Wrap(
        spacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final grupo in grupos)
            Chip(label: Text(grupo), visualDensity: VisualDensity.compact),
          if (inativo)
            const Chip(
              label: Text('Inativo'),
              visualDensity: VisualDensity.compact,
            ),
          IconButton(
            tooltip: 'Editar',
            icon: const Icon(Icons.edit_outlined),
            onPressed: onEdit,
          ),
        ],
      ),
      onTap: onEdit,
    );
  }

  String _inicial(String nome) {
    final limpo = nome.trim();
    return limpo.isEmpty ? '?' : limpo[0].toUpperCase();
  }

  /// Telefone e e-mail na mesma linha, sem separador sobrando quando um falta.
  String _contato() {
    final partes = [
      '${customer['phone'] ?? ''}'.trim(),
      '${customer['email'] ?? ''}'.trim(),
    ].where((parte) => parte.isNotEmpty);
    return partes.isEmpty ? 'Sem contato cadastrado' : partes.join(' · ');
  }
}
