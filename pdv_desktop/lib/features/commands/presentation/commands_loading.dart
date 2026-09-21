import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../data/command_repository.dart';

/// De onde vêm as comandas desta tela: a carga da lista e o leitor de cartão.
///
/// Separado do desenho da página porque são dois assuntos com ritmos
/// diferentes — o que aparece na tela muda por pedido de layout, e isto aqui
/// muda quando a API muda.
mixin CommandsLoading<T extends StatefulWidget> on State<T> {
  // ── fornecido pela página ───────────────────────────────────────────────
  CommandRepository get repository;
  String? get restaurantId;
  TextEditingController get leitor;
  FocusNode get focoDoLeitor;
  Stream<String>? get codigosLidos;

  StreamSubscription<String>? _assinaturaDeCodigos;

  /// Passa a ouvir o leitor avulso — o que é lido sem nenhum campo focado.
  ///
  /// A página chama isto no `initState` e [pararDeOuvirCodigos] no `dispose`.
  void ouvirCodigosLidos() {
    _assinaturaDeCodigos = codigosLidos?.listen((codigo) {
      // O campo do leitor é preenchido antes: `abrirPorCodigo` lê dele, e
      // assim os dois caminhos — digitar ali e passar o cartão solto — são o
      // MESMO código, com as mesmas recusas.
      leitor.text = codigo;
      unawaited(abrirPorCodigo());
    });
  }

  void pararDeOuvirCodigos() => _assinaturaDeCodigos?.cancel();

  List<Map<String, dynamic>> comandas = const [];
  Map<String, dynamic>? selecionada;
  bool carregando = false;
  String erro = '';
  String recado = '';

  Future<void> carregar() async {
    setState(() {
      carregando = true;
      erro = '';
    });
    try {
      final lista = await repository.list(restaurantId: restaurantId);
      if (mounted) setState(() => comandas = lista);
    } on ApiException catch (falha) {
      if (mounted) setState(() => erro = falha.message);
    } catch (falha) {
      // Nem toda falha é `ApiException`: um corpo que não é mapa, um
      // `TypeError` de conversão ou uma exceção crua da rede escapavam daqui e
      // deixavam a tela SEM lista e SEM recado — o operador via uma página
      // parada, sem saber se ainda estava vindo ou se tinha dado errado.
      if (mounted) {
        setState(() => erro = 'Falha ao carregar as comandas: $falha');
      }
    } finally {
      if (mounted) setState(() => carregando = false);
    }
  }

  /// O leitor é um teclado: digita o código e manda Enter.
  ///
  /// Resolve pelo `by-code` em vez de filtrar a lista em memória de propósito —
  /// o cartão pode ser de uma comanda que a página ainda não carregou.
  Future<void> abrirPorCodigo() async {
    final lido = leitor.text.trim();
    if (lido.isEmpty) return;
    leitor.clear();
    setState(() {
      carregando = true;
      erro = '';
      recado = '';
    });
    try {
      final comanda = await repository.byCode(lido);
      if (!mounted) return;
      setState(() => selecionada = Map<String, dynamic>.from(comanda));
      final conhecida = comandas.any((item) => item['id'] == comanda['id']);
      if (!conhecida) await carregar();
    } on ApiException catch (falha) {
      if (mounted) setState(() => erro = falha.message);
    } catch (falha) {
      // O cartão passado e nada acontecendo é o pior retorno possível no
      // balcão: o operador passa de novo, e de novo. Toda falha vira recado.
      if (mounted) setState(() => erro = 'Falha ao ler o cartão: $falha');
    } finally {
      if (mounted) setState(() => carregando = false);
      focoDoLeitor.requestFocus();
    }
  }
}
