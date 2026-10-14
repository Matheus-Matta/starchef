import '../../logging/app_logger.dart';

/// A sequência do que aconteceu com a porta da balança, para o suporte.
///
/// "A balança fecha sozinha" não se investiga sem saber a ORDEM: abriu, deu
/// erro, fechou, agendou reconexão, o operador parou. Cada evento vai para o
/// log do terminal (`scale_<evento>`) e os últimos ficam em memória, que é o
/// que os testes conferem.
class ScaleEventLog {
  ScaleEventLog(this.portName);

  static const _limite = 100;

  final String portName;
  final List<String> _eventos = [];

  List<String> get eventos => List.unmodifiable(_eventos);

  void registrar(String evento, [Map<String, Object?> dados = const {}]) {
    _eventos.add(evento);
    if (_eventos.length > _limite) _eventos.removeAt(0);
    AppLogger.instance.info(
      'scale_$evento',
      data: {'port': portName, ...dados},
    );
  }
}
