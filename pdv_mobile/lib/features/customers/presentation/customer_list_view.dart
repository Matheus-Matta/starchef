import 'package:flutter/material.dart';

/// O corpo da lista de clientes: os estados vazios e as linhas.
///
/// Separado da página porque são duas perguntas. A página resolve BUSCAR
/// (consulta, pausa de digitação, erro de rede); isto resolve MOSTRAR — e é
/// aqui que um campo novo do cadastro aparece, sem passar pela busca.
class CustomerListView extends StatelessWidget {
  const CustomerListView({
    super.key,
    required this.clientes,
    required this.busca,
    required this.carregando,
    required this.erro,
    required this.onRefresh,
    required this.onEdit,
  });

  final List<Map<String, dynamic>> clientes;
  final String busca;
  final bool carregando;
  final String erro;
  final Future<void> Function() onRefresh;
  final void Function(Map<String, dynamic> cliente) onEdit;

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    if (erro.isNotEmpty) return _aviso(erro, cores.error);
    if (carregando && clientes.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (clientes.isEmpty) {
      // Duas frases, porque são dois estados: a base está vazia, ou a busca
      // não achou. Uma só mandaria o garçom cadastrar alguém que já existe.
      return _aviso(
        busca.trim().isEmpty
            ? 'Nenhum cliente cadastrado ainda.'
            : 'Nada encontrado para "${busca.trim()}".',
        cores.onSurfaceVariant,
      );
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView.separated(
        padding: const EdgeInsets.only(bottom: 88),
        itemCount: clientes.length,
        separatorBuilder: (_, _) => const Divider(height: 1),
        itemBuilder: (_, indice) {
          final cliente = clientes[indice];
          final grupos =
              (cliente['group_names'] as List?)?.cast<String>() ?? const [];
          return ListTile(
            leading: CircleAvatar(
              child: Text(_inicial('${cliente['name'] ?? '?'}')),
            ),
            title: Text('${cliente['name'] ?? ''}'),
            subtitle: Text(
              [
                _contato(cliente),
                if (grupos.isNotEmpty) grupos.join(', '),
              ].join(' · '),
            ),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => onEdit(cliente),
          );
        },
      ),
    );
  }

  Widget _aviso(String texto, Color cor) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Text(texto, textAlign: TextAlign.center, style: TextStyle(color: cor)),
    ),
  );

  String _inicial(String nome) {
    final limpo = nome.trim();
    return limpo.isEmpty ? '?' : limpo[0].toUpperCase();
  }

  /// Telefone e e-mail juntos, sem separador sobrando quando um falta.
  String _contato(Map<String, dynamic> cliente) {
    final partes = [
      '${cliente['phone'] ?? ''}'.trim(),
      '${cliente['email'] ?? ''}'.trim(),
    ].where((parte) => parte.isNotEmpty);
    return partes.isEmpty ? 'Sem contato' : partes.join(' · ');
  }
}
