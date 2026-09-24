import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/app_page.dart';
import '../../orders/data/orders_repository.dart';
import 'customer_form_sheet.dart';
import 'customer_list_view.dart';

/// A lista de clientes no aparelho do garçom.
///
/// É consulta e cadastro, não venda: vincular o cliente a um pedido continua
/// sendo gesto do fluxo do pedido, onde a escolha tem consequência.
///
/// O garçom precisa disto na mão porque quem pede o cadastro é o cliente, na
/// mesa: "põe no meu nome", "meu telefone mudou". Sem a tela, ele anotava no
/// papel e alguém digitava depois — quando digitava.
class CustomersPage extends StatefulWidget {
  const CustomersPage({super.key, required this.repository});

  final OrdersRepository repository;

  @override
  State<CustomersPage> createState() => _CustomersPageState();
}

class _CustomersPageState extends State<CustomersPage> {
  final _busca = TextEditingController();
  List<Map<String, dynamic>> _clientes = const [];
  var _carregando = true;
  String _erro = '';
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _busca.dispose();
    super.dispose();
  }

  Future<void> _carregar() async {
    setState(() {
      _carregando = true;
      _erro = '';
    });
    try {
      final clientes = await widget.repository.customers(busca: _busca.text);
      if (!mounted) return;
      setState(() {
        _clientes = clientes;
        _carregando = false;
      });
    } on ApiException catch (falha) {
      if (!mounted) return;
      setState(() {
        _erro = falha.message;
        _carregando = false;
      });
    }
  }

  /// Espera o garçom parar de digitar antes de consultar.
  ///
  /// No celular cada letra é uma requisição em rede de loja: sem a pausa,
  /// "Maria" dispara cinco, e a resposta da terceira pode chegar depois da
  /// quinta — a lista mostraria o resultado de "Mar".
  void _buscarComPausa(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), _carregar);
  }

  Future<void> _abrirFormulario({Map<String, dynamic>? cliente}) async {
    final salvo = await showCustomerForm(
      context,
      widget.repository,
      existing: cliente,
    );
    if (salvo == null || !mounted) return;
    await _carregar();
  }

  @override
  Widget build(BuildContext context) => AppPageScaffold(
    title: 'Clientes',
    actions: [
      IconButton(
        tooltip: 'Atualizar',
        onPressed: _carregando ? null : _carregar,
        icon: const Icon(Icons.refresh),
      ),
    ],
    floatingActionButton: FloatingActionButton.extended(
      onPressed: () => _abrirFormulario(),
      icon: const Icon(Icons.person_add_alt_1),
      label: const Text('Novo'),
    ),
    body: Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: TextField(
            controller: _busca,
            onChanged: _buscarComPausa,
            onSubmitted: (_) => _carregar(),
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: 'Nome, telefone, e-mail ou CPF',
              border: const OutlineInputBorder(),
              suffixIcon: _busca.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () {
                        _busca.clear();
                        _carregar();
                      },
                    ),
            ),
          ),
        ),
        Expanded(
          child: CustomerListView(
            clientes: _clientes,
            busca: _busca.text,
            carregando: _carregando,
            erro: _erro,
            onRefresh: _carregar,
            onEdit: (cliente) => _abrirFormulario(cliente: cliente),
          ),
        ),
      ],
    ),
  );
}
