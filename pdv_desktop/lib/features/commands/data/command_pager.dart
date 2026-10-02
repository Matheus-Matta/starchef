import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_exception.dart';

/// Uma página da lista: os itens e se o servidor tem mais.
typedef PaginaDeComandas = ({
  List<Map<String, dynamic>> itens,
  bool temMais,
  int? total,
});

/// Busca a página [pagina] (começa em 1) filtrada por [busca].
typedef BuscarPaginaDeComandas =
    Future<PaginaDeComandas> Function({required int pagina, String busca});

/// Comandas que chegam conforme a rolagem, e não todas de uma vez.
///
/// Uma loja com 500 cartões abria a tela esperando as cinco páginas antes de
/// mostrar o primeiro. Aqui a primeira página aparece sozinha e as próximas
/// vêm quando a rolagem chega perto do fim ([carregarMais]).
///
/// A busca vai ao SERVIDOR ([digitar]): com a lista pela metade, filtrar em
/// memória diria "não encontrada" para a comanda 480 que ainda não desceu.
///
/// Cada busca nova abre uma GERAÇÃO. Resposta de geração velha é descartada —
/// digitar "1", "12", "120" depressa dispara três pedidos, e o do "1" (o mais
/// lento, porque casa com mais) não pode chegar por último e trocar a lista.
class CommandPager extends ChangeNotifier {
  CommandPager(
    this._buscarPagina, {
    this.espera = const Duration(milliseconds: 300),
  });

  final BuscarPaginaDeComandas _buscarPagina;

  /// Quanto [digitar] espera a pessoa parar de digitar antes de buscar.
  final Duration espera;

  List<Map<String, dynamic>> itens = const [];
  bool temMais = true;
  bool carregando = false;
  int? total;
  String erro = '';
  String busca = '';

  int _geracao = 0;
  int _proximaPagina = 1;
  bool _descartado = false;
  Timer? _digitando;

  /// A busca do campo de texto: só vai ao servidor quando a digitação para.
  void digitar(String termo) {
    _digitando?.cancel();
    if (termo.trim() == busca) return;
    _digitando = Timer(espera, () => recomecar(busca: termo));
  }

  /// Busca [termo] agora, sem esperar — o Enter do leitor de cartão.
  Future<void> buscarJa(String termo) {
    _digitando?.cancel();
    return recomecar(busca: termo);
  }

  /// Recomeça do zero com [busca] (ou com a busca atual, quando nula).
  ///
  /// Mantém os itens na tela até a primeira página nova chegar: limpar antes
  /// piscava a grade inteira a cada letra digitada.
  Future<void> recomecar({String? busca}) {
    this.busca = (busca ?? this.busca).trim();
    _geracao++;
    _proximaPagina = 1;
    temMais = true;
    carregando = false;
    return _carregar(substituir: true);
  }

  /// A próxima página. Sem efeito enquanto outra está vindo ou no fim.
  Future<void> carregarMais() {
    if (carregando || !temMais || erro.isNotEmpty) return Future.value();
    return _carregar(substituir: false);
  }

  /// Tenta de novo depois de uma falha, da página onde parou.
  Future<void> tentarDeNovo() {
    if (carregando) return Future.value();
    erro = '';
    return _carregar(substituir: _proximaPagina == 1);
  }

  Future<void> _carregar({required bool substituir}) async {
    final geracao = _geracao;
    carregando = true;
    erro = '';
    _avisar();
    try {
      final pagina = await _buscarPagina(pagina: _proximaPagina, busca: busca);
      if (geracao != _geracao || _descartado) return;
      // A mesma comanda pode reaparecer na página seguinte quando outra foi
      // criada no meio da rolagem (tudo desliza uma posição). Repetida, ela
      // viraria dois cartões iguais na grade.
      final vistos = {
        if (!substituir)
          for (final c in itens) '${c['id']}',
      };
      final novos = [
        for (final c in pagina.itens)
          if (vistos.add('${c['id']}')) c,
      ];
      itens = substituir ? novos : [...itens, ...novos];
      temMais = pagina.temMais && pagina.itens.isNotEmpty;
      total = pagina.total ?? total;
      _proximaPagina++;
    } on ApiException catch (falha) {
      if (geracao != _geracao || _descartado) return;
      erro = falha.message;
    } catch (falha) {
      if (geracao != _geracao || _descartado) return;
      erro = 'Falha ao carregar as comandas: $falha';
    } finally {
      if (geracao == _geracao && !_descartado) {
        carregando = false;
        _avisar();
      }
    }
  }

  /// Troca uma comanda já na lista pela versão nova, sem recarregar tudo.
  void atualizar(Map<String, dynamic> comanda) {
    final indice = itens.indexWhere((c) => c['id'] == comanda['id']);
    if (indice < 0) return;
    itens = [...itens]..[indice] = comanda;
    _avisar();
  }

  void _avisar() {
    if (!_descartado) notifyListeners();
  }

  @override
  void dispose() {
    _descartado = true;
    _digitando?.cancel();
    super.dispose();
  }
}
