import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../data/customer_repository.dart';
import 'customer_form_dialog.dart';
import 'customer_search_bar.dart';
import 'customer_tile.dart';

/// A lista de clientes do restaurante, com cadastro e edição na modal.
///
/// É consulta, não venda. O operador vem aqui para achar alguém, conferir o
/// telefone, corrigir um CPF digitado errado — e para cadastrar quem ligou
/// antes de existir pedido. Vincular o cliente a uma venda continua sendo
/// gesto do fluxo do pedido, onde a escolha tem consequência.
///
/// A BUSCA É DO SERVIDOR. Um restaurante com dez mil clientes não cabe na
/// memória do terminal, e filtrar só a página carregada diria "não existe"
/// para quem está na página seguinte.
class CustomersPage extends StatefulWidget {
  const CustomersPage({
    super.key,
    required this.repository,
    this.restaurantId,
  });

  final CustomerRepository repository;
  final String? restaurantId;

  @override
  State<CustomersPage> createState() => _CustomersPageState();
}

class _CustomersPageState extends State<CustomersPage> {
  final _busca = TextEditingController();
  List<Map<String, dynamic>> _clientes = const [];
  var _carregando = true;
  String _erro = '';
  String _recado = '';
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
      final clientes = await widget.repository.list(
        restaurantId: widget.restaurantId,
        busca: _busca.text,
      );
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

  /// Espera o operador parar de digitar antes de consultar.
  ///
  /// Sem isso, "Maria" dispara cinco buscas e a resposta da terceira pode
  /// chegar depois da quinta — a lista mostraria o resultado de "Mar".
  void _buscarComPausa(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _carregar);
  }

  Future<void> _abrirFormulario({Map<String, dynamic>? cliente}) async {
    final salvo = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => CustomerFormDialog(
        existing: cliente,
        restaurantId: widget.restaurantId,
        confirmLabel: cliente == null ? 'Cadastrar' : 'Salvar',
        onSubmit: (corpo) => cliente == null
            ? widget.repository.create(corpo)
            : widget.repository.update('${cliente['id']}', corpo),
        onError: (falha) {
          if (mounted) {
            setState(
              () => _erro = falha is ApiException ? falha.message : '$falha',
            );
          }
        },
      ),
    );
    if (salvo == null || !mounted) return;
    setState(
      () => _recado = cliente == null
          ? 'Cliente ${salvo['name']} cadastrado.'
          : 'Cliente ${salvo['name']} atualizado.',
    );
    await _carregar();
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CustomerSearchBar(
            controller: _busca,
            onChanged: _buscarComPausa,
            onSubmit: _carregar,
            onClear: () {
              _busca.clear();
              _carregar();
            },
            onNew: () => _abrirFormulario(),
            carregando: _carregando,
          ),
          if (_erro.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_erro, style: TextStyle(color: cores.error)),
            ),
          if (_recado.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_recado, style: TextStyle(color: cores.primary)),
            ),
          const SizedBox(height: 12),
          Expanded(child: _corpo(cores)),
        ],
      ),
    );
  }

  Widget _corpo(ColorScheme cores) {
    if (_carregando && _clientes.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_clientes.isEmpty) {
      // Duas frases, porque são dois estados: a base está vazia, ou a busca
      // não achou. Uma só mandaria o operador cadastrar alguém que já existe.
      return Center(
        child: Text(
          _busca.text.trim().isEmpty
              ? 'Nenhum cliente cadastrado ainda.'
              : 'Nenhum cliente encontrado para "${_busca.text.trim()}".',
          style: TextStyle(color: cores.onSurfaceVariant),
        ),
      );
    }
    return ListView.separated(
      itemCount: _clientes.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (_, indice) => CustomerTile(
        customer: _clientes[indice],
        onEdit: () => _abrirFormulario(cliente: _clientes[indice]),
      ),
    );
  }
}
