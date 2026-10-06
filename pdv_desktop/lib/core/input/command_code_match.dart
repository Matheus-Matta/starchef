/// Quando um código lido É uma comanda — e quando não é.
///
/// A etiqueta imprime o número com zeros (`0017`), o operador digita `17`, e
/// os dois têm de achar a mesma comanda. E SÓ ela: abrir "a comanda mais
/// parecida" lança consumo na conta de outro cliente. Foi o que aconteceu com
/// a 17 lida que abriu a 107.
library;

final _soDigitos = RegExp(r'^\d+$');

/// O código sem espaços e, quando é só número, sem os zeros à esquerda.
String normalizarCodigoDeComanda(String valor) {
  final limpo = valor.trim();
  if (!_soDigitos.hasMatch(limpo)) return limpo;
  final semZeros = limpo.replaceFirst(RegExp(r'^0+'), '');
  return semZeros.isEmpty ? '0' : semZeros;
}

/// O que aparece em letras grandes enquanto a comanda abre.
String numeroLidoParaExibir(String lido) => normalizarCodigoDeComanda(lido);

/// A comanda é a do código lido — pelo código da etiqueta ou pelo número?
bool comandaCasaComLido(Map<String, dynamic> comanda, String lido) {
  final alvo = normalizarCodigoDeComanda(lido);
  if (alvo.isEmpty) return false;
  for (final campo in const ['code', 'number']) {
    final valor = '${comanda[campo] ?? ''}';
    if (valor.trim().isEmpty) continue;
    if (normalizarCodigoDeComanda(valor) == alvo) return true;
  }
  return false;
}

/// A comanda lida, procurada numa lista — por casamento exato, nunca por
/// eliminação.
Map<String, dynamic>? comandaLidaNaLista(
  Iterable<Map<String, dynamic>> comandas,
  String lido,
) {
  for (final comanda in comandas) {
    if (comandaCasaComLido(comanda, lido)) return comanda;
  }
  return null;
}
