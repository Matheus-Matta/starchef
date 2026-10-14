import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';

/// Os cupons como botões, logo abaixo do campo do pagamento.
///
/// O caixa digitava o código inteiro, e o cliente quase sempre traz o mesmo
/// cupom da campanha do mês. Agora os 5 mais usados aparecem de cara e, enquanto
/// ele digita, a lista vira a busca pelo que foi digitado. Um toque aplica.
///
/// Só cupom vigente (ligado e no prazo): sugerir um vencido seria um toque
/// para ouvir uma recusa.
class CouponSuggestions extends StatefulWidget {
  const CouponSuggestions({
    super.key,
    required this.api,
    required this.accessToken,
    required this.controller,
    required this.onPick,
  });

  final ApiClient api;
  final String accessToken;
  final TextEditingController controller;
  final ValueChanged<String> onPick;

  @override
  State<CouponSuggestions> createState() => _CouponSuggestionsState();
}

class _CouponSuggestionsState extends State<CouponSuggestions> {
  /// Espera o operador parar de digitar: uma ida por tecla afogaria a loja e
  /// devolveria as respostas fora de ordem.
  static const _pausa = Duration(milliseconds: 250);

  List<Map<String, dynamic>> _cupons = const [];
  Timer? _debounce;
  String _buscado = '';
  int _versao = 0;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_aoDigitar);
    _buscar('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    widget.controller.removeListener(_aoDigitar);
    super.dispose();
  }

  void _aoDigitar() {
    final texto = widget.controller.text.trim();
    if (texto == _buscado) return;
    _debounce?.cancel();
    _debounce = Timer(_pausa, () => _buscar(texto));
  }

  Future<void> _buscar(String texto) async {
    _buscado = texto;
    final minha = ++_versao;
    try {
      final resposta = await widget.api.get(
        '/promotions/coupons/',
        query: {
          'vigentes': 1,
          'ordering': '-total_resgates',
          'page_size': 5,
          if (texto.isNotEmpty) 'search': texto,
        },
        accessToken: widget.accessToken,
      );
      // Uma resposta antiga que chegue depois não troca a lista atual.
      if (!mounted || minha != _versao) return;
      setState(() {
        _cupons = ((resposta['results'] ?? const []) as List)
            .whereType<Map>()
            .map(Map<String, dynamic>.from)
            .toList();
      });
    } catch (_) {
      // Sem sugestões o campo continua funcionando: elas são atalho.
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cupons.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          for (final cupom in _cupons)
            ActionChip(
              key: ValueKey('cupom-sugerido-${cupom['code']}'),
              avatar: const Icon(Icons.local_activity_outlined, size: 14),
              label: Text('${cupom['code']}'),
              tooltip: '${cupom['name'] ?? ''}'.trim().isEmpty
                  ? null
                  : '${cupom['name']}',
              visualDensity: VisualDensity.compact,
              onPressed: () => widget.onPick('${cupom['code']}'),
            ),
        ],
      ),
    );
  }
}
