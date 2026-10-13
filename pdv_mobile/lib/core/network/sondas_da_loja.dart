/// A loja respondeu a ALGUMA de [vezes] sondas seguidas?
///
/// Com uma sonda só, o serviço da loja reiniciando ou a rede do salão piscando
/// trocava o aparelho para a nuvem em segundos — e trocar de servidor no meio
/// do atendimento é pior que esperar alguns segundos (`cloud_fallback.dart`).
Future<bool> lojaRespondeuAlguma(
  Future<bool> Function() sonda, {
  required int vezes,
  required Duration intervalo,
}) async {
  for (var tentativa = 1; tentativa <= vezes; tentativa++) {
    if (await sonda()) return true;
    if (tentativa < vezes) await Future<void>.delayed(intervalo);
  }
  return false;
}
