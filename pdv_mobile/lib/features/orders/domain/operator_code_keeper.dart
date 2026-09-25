import 'package:flutter/foundation.dart';

/// Guarda o código de quem está lançando, por atendimento.
///
/// O CASO É O TOTEM: um aparelho no salão, uma sessão só, vários garçons. O
/// código diz quem anotou cada item — sem ele, o dia inteiro fica no nome do
/// mesmo login.
///
/// O CÓDIGO VALE POR ATENDIMENTO, e é aí que está a decisão de desenho:
///
/// - **por item** seria o registro mais fiel, e inutilizável: dez pratos numa
///   mesa são dez digitações, e a décima é "1111" para acabar logo — um rastro
///   que mente é pior do que nenhum;
/// - **por sessão** não serve num aparelho compartilhado: o segundo garçom
///   lançaria no código do primeiro sem perceber.
///
/// Então: pergunta uma vez ao entrar no pedido ou na comanda, e esquece ao sair.
/// Quem assume o aparelho depois informa o seu.
class OperatorCodeKeeper extends ChangeNotifier {
  /// A chave que o backend conhece (`apps.orders.operator_code.CHAVE`).
  static const chave = 'operator_code';

  final _porAtendimento = <String, String>{};

  /// O código guardado para este pedido/comanda, ou vazio.
  String codigoDe(String assunto) => _porAtendimento[assunto] ?? '';

  bool temCodigo(String assunto) => codigoDe(assunto).isNotEmpty;

  /// Guarda o código. Só dígitos entram — é o que o servidor aceita, e barrar
  /// aqui evita uma ida à rede para ouvir a mesma recusa.
  void guardar(String assunto, String codigo) {
    final limpo = codigo.replaceAll(RegExp(r'\D'), '');
    if (limpo.isEmpty) return;
    _porAtendimento[assunto] = limpo;
    notifyListeners();
  }

  /// Esquece o código ao sair do atendimento.
  void esquecer(String assunto) {
    if (_porAtendimento.remove(assunto) != null) notifyListeners();
  }

  /// Esquece tudo — na saída do app, ou quando a sessão troca.
  void limpar() {
    if (_porAtendimento.isEmpty) return;
    _porAtendimento.clear();
    notifyListeners();
  }

  /// O corpo que acompanha a requisição, ou `null` quando não há código.
  ///
  /// `null` em vez de mapa vazio de propósito: o backend distingue "não informou"
  /// de "informou vazio", e mandar `{}` num restaurante que exige o código
  /// receberia a recusa sem o operador ter sido perguntado.
  Map<String, String>? corpoDe(String assunto) {
    final codigo = codigoDe(assunto);
    if (codigo.isEmpty) return null;
    return {chave: codigo};
  }
}
