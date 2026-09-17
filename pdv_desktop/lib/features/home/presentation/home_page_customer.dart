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

  Future<Map<String, dynamic>?> _createCustomerDialog() => showDialog<
    Map<String, dynamic>
  >(
    context: context,
    barrierDismissible: false,
    // O diálogo é dono dos cinco controladores e os descarta no `dispose` do
    // seu `State`, depois que a rota termina de sair. Descartá-los aqui, logo
    // após o `await`, é cedo demais — ver `_MovementApprovalForm`.
    builder: (_) => _NewCustomerForm(
      onCreate: (corpo) =>
          api.post('/customers/', body: corpo, accessToken: token),
      onError: (error) {
        if (mounted) _error(error);
      },
      restaurantId: restaurantId,
    ),
  );
}

/// Cadastro rápido de cliente, direto do pedido.
class _NewCustomerForm extends StatefulWidget {
  const _NewCustomerForm({
    required this.onCreate,
    required this.onError,
    required this.restaurantId,
  });

  final Future<Map<String, dynamic>> Function(Map<String, dynamic> corpo)
  onCreate;
  final void Function(Object error) onError;
  final String? restaurantId;

  @override
  State<_NewCustomerForm> createState() => _NewCustomerFormState();
}

class _NewCustomerFormState extends State<_NewCustomerForm> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _document = TextEditingController();
  final _notes = TextEditingController();
  var _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _email.dispose();
    _document.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final Map<String, dynamic> customer;
    try {
      customer = await widget.onCreate({
        'restaurant': widget.restaurantId,
        'name': _name.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'document': _document.text.trim(),
        'internal_notes': _notes.text.trim(),
        'is_active': true,
      });
    } catch (error) {
      if (!mounted) return;
      widget.onError(error);
      // O diálogo segue aberto com o que já foi digitado: o operador corrige
      // o campo recusado em vez de preencher tudo de novo.
      setState(() => _saving = false);
      return;
    }
    if (!mounted) return;
    Navigator.pop(context, customer);
  }

  @override
  Widget build(BuildContext context) => AppDialog(
    title: const Text('Cadastrar cliente'),
    content: SizedBox(
      width: 560,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Nome completo',
                  helperText: 'Nome usado para identificar o cliente.',
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Informe o nome do cliente.'
                    : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Telefone',
                  helperText: 'Número para contato sobre o pedido.',
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Informe o telefone.'
                    : null,
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _email,
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
                      controller: _document,
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
                controller: _notes,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Observações internas',
                  helperText: 'Informações visíveis somente para a equipe.',
                ),
              ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: _saving ? null : () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton.icon(
        onPressed: _saving ? null : _save,
        icon: _saving
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.save_outlined),
        label: const Text('Cadastrar e selecionar'),
      ),
    ],
  );
}
