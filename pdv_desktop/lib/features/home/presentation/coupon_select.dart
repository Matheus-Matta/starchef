import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import 'coupon_options_list.dart';
import 'payment_input_style.dart';

/// O cupom da tela de pagamento: UM campo de seleção com busca.
///
/// Eram um campo, um botão "Aplicar" e uma fileira de botões com os cupons
/// soltos embaixo — três controles para uma escolha só, e a fileira empurrava
/// o resumo da conta para baixo. Agora a lista abre no próprio campo:
/// "Nenhum" sempre em primeiro, os vigentes mais usados logo abaixo, e a busca
/// no servidor enquanto o caixa digita. O X dentro do campo remove.
///
/// Só cupom vigente aparece: sugerir um vencido seria um toque para ouvir uma
/// recusa. Um código fora da lista (cupom de uso restrito) ainda vale com
/// Enter — quem decide é o servidor, sempre.
class CouponSelect extends StatefulWidget {
  const CouponSelect({
    super.key,
    required this.api,
    required this.accessToken,
    required this.aplicado,
    required this.busy,
    required this.erro,
    required this.onAplicar,
    required this.onRemover,
  });

  final ApiClient api;
  final String accessToken;

  /// O código que o pedido carrega. Vazio = nenhum cupom.
  final String aplicado;
  final bool busy;

  /// A recusa do servidor ("Este CPF já usou este cupom"), no próprio campo.
  final String erro;
  final ValueChanged<String> onAplicar;
  final VoidCallback onRemover;

  @override
  State<CouponSelect> createState() => _CouponSelectState();
}

/// "Nenhum": a opção que retira o cupom, sempre a primeira da lista.
const _nenhum = <String, dynamic>{'code': ''};

class _CouponSelectState extends State<CouponSelect> {
  /// Espera o operador parar de digitar: uma ida por tecla afogaria a loja.
  static const _pausa = Duration(milliseconds: 250);

  late final _controle = TextEditingController(text: widget.aplicado);
  final _foco = FocusNode();
  int _versao = 0;

  @override
  void didUpdateWidget(CouponSelect antigo) {
    super.didUpdateWidget(antigo);
    // O servidor aceitou, trocou ou retirou: o campo mostra o que vale.
    if (antigo.aplicado != widget.aplicado) _controle.text = widget.aplicado;
  }

  @override
  void dispose() {
    _controle.dispose();
    _foco.dispose();
    super.dispose();
  }

  Future<Iterable<Map<String, dynamic>>> _opcoes(TextEditingValue valor) async {
    final minha = ++_versao;
    await Future<void>.delayed(_pausa);
    // Uma busca mais nova começou enquanto esta esperava: esta não volta.
    if (minha != _versao) return const [];
    // O texto igual ao aplicado é o campo mostrando o cupom, não uma busca.
    final texto = valor.text.trim() == widget.aplicado ? '' : valor.text.trim();
    try {
      final resposta = await widget.api.get(
        '/promotions/coupons/',
        query: {
          'vigentes': 1,
          'ordering': '-total_resgates',
          'page_size': 8,
          if (texto.isNotEmpty) 'search': texto,
        },
        accessToken: widget.accessToken,
      );
      return [
        _nenhum,
        ...((resposta['results'] ?? const []) as List).whereType<Map>().map(
          Map<String, dynamic>.from,
        ),
      ];
    } catch (_) {
      // Sem lista o campo continua valendo: o código digitado e Enter.
      return const [_nenhum];
    }
  }

  void _escolher(Map<String, dynamic> cupom) {
    final codigo = '${cupom['code'] ?? ''}';
    _foco.unfocus();
    if (codigo.isEmpty) {
      _controle.clear();
      if (widget.aplicado.isNotEmpty) widget.onRemover();
    } else {
      widget.onAplicar(codigo);
    }
  }

  void _digitado() {
    final codigo = _controle.text.trim().toUpperCase();
    if (codigo.isEmpty) {
      if (widget.aplicado.isNotEmpty) widget.onRemover();
    } else if (codigo != widget.aplicado) {
      widget.onAplicar(codigo);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        RawAutocomplete<Map<String, dynamic>>(
          textEditingController: _controle,
          focusNode: _foco,
          displayStringForOption: (cupom) => '${cupom['code'] ?? ''}',
          optionsBuilder: _opcoes,
          onSelected: _escolher,
          fieldViewBuilder: (context, controle, foco, enviar) => TextField(
            key: const Key('payment-coupon'),
            controller: controle,
            focusNode: foco,
            enabled: !widget.busy,
            textCapitalization: TextCapitalization.characters,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _digitado(),
            decoration: campoDoPagamento(
              'Cupom',
              hintText: 'Buscar cupom',
              prefixIcon: const Icon(Icons.local_activity_outlined, size: 18),
              suffixIcon: widget.busy
                  ? const Padding(
                      padding: EdgeInsets.all(10),
                      child: SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  : widget.aplicado.isEmpty
                  ? null
                  : botaoDoCampo(
                      key: const Key('payment-coupon-remove'),
                      icon: Icons.close_rounded,
                      tooltip: 'Remover cupom',
                      onPressed: () => _escolher(_nenhum),
                    ),
            ),
          ),
          optionsViewBuilder: (context, escolher, opcoes) =>
              CouponOptionsList(opcoes: opcoes, escolher: escolher),
        ),
        if (widget.erro.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              widget.erro,
              style: TextStyle(color: cores.error, fontSize: 12),
            ),
          ),
      ],
    );
  }
}
