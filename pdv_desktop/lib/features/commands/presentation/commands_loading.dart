import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/input/command_code_match.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/scanned_command_overlay.dart';
import '../data/command_pager.dart';
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

  /// As comandas chegam por página, conforme o salão rola (ver [CommandPager]).
  late final CommandPager paginador = CommandPager(
    ({required int pagina, String busca = ''}) => repository.page(
      pagina: pagina,
      busca: busca,
      restaurantId: restaurantId,
    ),
  );

  /// As que já desceram — não necessariamente todas as da loja.
  List<Map<String, dynamic>> get comandas => paginador.itens;
  Map<String, dynamic>? selecionada;
  bool carregando = false;
  String erro = '';
  String recado = '';

  @override
  void dispose() {
    paginador.dispose();
    super.dispose();
  }

  /// Relê do começo, mantendo o que está no campo de busca.
  ///
  /// A falha fica no rodapé da grade, com "Tentar de novo" — e não no recado
  /// do topo, que é das ações (lançar, cancelar) e seria apagado pela próxima.
  Future<void> carregar() async {
    setState(() => carregando = true);
    try {
      await paginador.recomecar();
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
      final comanda = await mostrandoComandaLida(
        context,
        lido,
        () => repository.byCode(lido),
      );
      if (!mounted) return;
      final confere = comandaCasaComLido(comanda, lido);
      AppLogger.instance.info(
        'comanda_lida',
        data: {
          'lido': lido,
          'numero': '${comanda['number'] ?? ''}',
          'confere': confere,
        },
      );
      if (!confere) {
        // A última trava: abrir a comanda errada é lançar na conta de outro.
        setState(
          () => erro =
              'O leitor leu ${numeroLidoParaExibir(lido)}, mas a comanda '
              'encontrada é a ${comanda['number'] ?? '?'}. Passe o cartão de novo.',
        );
        return;
      }
      setState(() => selecionada = Map<String, dynamic>.from(comanda));
      // O cartão pode ser de uma comanda que ainda não desceu na rolagem: ela
      // abre do mesmo jeito. A que já está na grade ganha o estado novo.
      paginador.atualizar(Map<String, dynamic>.from(comanda));
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
