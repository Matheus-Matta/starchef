/// Como o operador chama este caixa.
///
/// O nome do cadastro (`cash_station_name`) é o que ele lê na tela de caixas e
/// nos relatórios; `station` é o texto livre que sessões antigas guardavam.
/// Preferir o primeiro mantém o rótulo da barra lateral igual ao do
/// comprovante impresso — duas grafias para o mesmo caixa fazem o operador
/// achar que são dois.
String cashStationLabelOf(
  Map<String, dynamic> session, {
  String fallback = 'Caixa',
}) {
  final station = '${session['cash_station_name'] ?? session['station'] ?? ''}'
      .trim();
  return station.isEmpty ? fallback : station;
}
