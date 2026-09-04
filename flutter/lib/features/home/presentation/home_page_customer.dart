// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Escolha e cadastro do cliente do pedido.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _CustomerSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get selectedCustomer;
  set selectedCustomer(Map<String, dynamic>? value);

  Future<Map<String, dynamic>?> _chooseCustomer(String type) async {
    List<Map<String, dynamic>> customers;
    try {
      customers = await _list(
        '/customers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 300,
        },
      );
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
    if (!mounted) return null;
    var search = '';
    return showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, update) {
          final filtered = customers.where((customer) {
            final term = search.trim().toLowerCase();
            return term.isEmpty ||
                '${customer['name']} ${customer['phone']} ${customer['document'] ?? ''}'
                    .toLowerCase()
                    .contains(term);
          }).toList();
          return AppDialog(
            title: Text(
              type == 'delivery'
                  ? 'Cliente do delivery'
                  : 'Cliente da retirada',
            ),
            content: SizedBox(
              width: 620,
              height: 480,
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          autofocus: true,
                          onChanged: (value) => update(() => search = value),
                          decoration: const InputDecoration(
                            labelText: 'Buscar cliente',
                            hintText: 'Nome, telefone ou CPF',
                            prefixIcon: Icon(Icons.search),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(
                        onPressed: () async {
                          final created = await _createCustomerDialog();
                          if (created != null && context.mounted) {
                            customers = [created, ...customers];
                            update(() {});
                            Navigator.pop(context, created);
                          }
                        },
                        icon: const Icon(Icons.person_add_alt_1),
                        label: const Text('Novo cliente'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: filtered.isEmpty
                        ? const Center(
                            child: Text(
                              'Nenhum cliente encontrado. Cadastre um novo cliente.',
                              textAlign: TextAlign.center,
                            ),
                          )
                        : ListView.separated(
                            itemCount: filtered.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 1),
                            itemBuilder: (_, index) {
                              final customer = filtered[index];
                              return ListTile(
                                leading: const CircleAvatar(
                                  child: Icon(Icons.person_outline),
                                ),
                                title: Text('${customer['name']}'),
                                subtitle: Text('${customer['phone']}'),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => Navigator.pop(context, customer),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Voltar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<Map<String, dynamic>?> _createCustomerDialog() async {
    final formKey = GlobalKey<FormState>();
    final name = TextEditingController();
    final phone = TextEditingController();
    final email = TextEditingController();
    final document = TextEditingController();
    final notes = TextEditingController();
    var saving = false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AppDialog(
          title: const Text('Cadastrar cliente'),
          content: SizedBox(
            width: 560,
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextFormField(
                      controller: name,
                      autofocus: true,
                      decoration: const InputDecoration(
                        labelText: 'Nome completo',
                        helperText: 'Nome usado para identificar o cliente.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o nome do cliente.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Telefone',
                        helperText: 'Número para contato sobre o pedido.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o telefone.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: const InputDecoration(
                              labelText: 'E-mail',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: TextFormField(
                            controller: document,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'CPF',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: notes,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Observações internas',
                        helperText:
                            'Informações visíveis somente para a equipe.',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(context),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: saving
                  ? null
                  : () async {
                      if (!formKey.currentState!.validate()) return;
                      update(() => saving = true);
                      try {
                        final customer = await api.post(
                          '/customers/',
                          body: {
                            'restaurant': restaurantId,
                            'name': name.text.trim(),
                            'phone': phone.text.trim(),
                            'email': email.text.trim(),
                            'document': document.text.trim(),
                            'internal_notes': notes.text.trim(),
                            'is_active': true,
                          },
                          accessToken: token,
                        );
                        if (context.mounted) Navigator.pop(context, customer);
                      } catch (error) {
                        if (context.mounted) _error(error);
                        update(() => saving = false);
                      }
                    },
              icon: saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: const Text('Cadastrar e selecionar'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    phone.dispose();
    email.dispose();
    document.dispose();
    notes.dispose();
    return result;
  }
}
