/// A forma de pagamento antes ou depois da atual — para ↑ e ↓ no pagamento.
///
/// Dá a volta nas pontas: com três formas, ↓ na última volta à primeira. Sem
/// seleção (ou com uma que saiu da lista) começa pela primeira, que é a mais
/// usada (`?ordering=-uso,name`).
String? formaVizinha(
  List<Map<String, dynamic>> formas,
  String? atual,
  int passo,
) {
  if (formas.isEmpty) return null;
  final indice = formas.indexWhere((forma) => '${forma['id']}' == atual);
  if (indice < 0) return '${formas.first['id']}';
  final proximo = (indice + passo) % formas.length;
  return '${formas[proximo < 0 ? proximo + formas.length : proximo]['id']}';
}
