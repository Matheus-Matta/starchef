import '../domain/printer_endpoint.dart';

/// A impressora como ela está cadastrada, resolvida uma única vez.
///
/// O cadastro chega como `Map<String, dynamic>` do backend, do cache local ou
/// da fila em disco, e cada tela lia esses campos com regras ligeiramente
/// diferentes. Aqui a leitura é uma só: [PrinterEndpoint] resolve o
/// transporte e esta classe resolve identidade, setor e rótulo.
///
/// Toda impressão usa o que está no cadastro — sem override por terminal. O
/// override existia para o caso de o mesmo equipamento receber caminhos
/// diferentes em cada máquina, mas criava a divergência pior: uma porta salva
/// localmente ficava desatualizada em relação ao cadastro, e a impressão real
/// abria um dispositivo diferente do que o teste de conexão abria — teste
/// passando e cupom não saindo.
class PrinterDevice {
  PrinterDevice._({
    required this.raw,
    required this.id,
    required this.name,
    required this.sector,
    required this.autoPrint,
    required this.endpoint,
  });

  factory PrinterDevice.fromJson(Map<String, dynamic> printer) =>
      PrinterDevice._(
        raw: printer,
        id: '${printer['id'] ?? ''}'.trim(),
        name: '${printer['name'] ?? ''}'.trim(),
        sector: '${printer['sector'] ?? ''}'.trim(),
        autoPrint: printer['auto_print'] == true,
        endpoint: PrinterEndpoint.fromJson(printer),
      );

  /// Cadastro original, para quem ainda fala em `Map` (fila local e API).
  final Map<String, dynamic> raw;

  final String id;
  final String name;
  final String sector;
  final bool autoPrint;
  final PrinterEndpoint endpoint;

  bool get isAddressable => endpoint.isAddressable;

  String? get missingConfiguration => endpoint.missingConfiguration;

  /// Como esta impressora aparece num aviso de erro.
  ///
  /// O aviso na tela é um só para todas as impressoras do terminal, então
  /// precisa dizer QUAL falhou: "Impressora desconectada" sozinho não
  /// distingue o cupom do caixa da comanda da cozinha.
  String get label =>
      name.isEmpty ? endpoint.label : '$name (${endpoint.label})';

  /// Recurso disputado por todos os processos que imprimem neste equipamento.
  ///
  /// É o endereço físico, não o `id` do cadastro: duas impressoras
  /// cadastradas separadamente podem apontar para o mesmo IP ou para a mesma
  /// porta, e nesse caso continuam sendo um equipamento só — que não aceita
  /// dois trabalhos ao mesmo tempo.
  String get lockResource => switch (endpoint.connection) {
    PrinterConnection.network => 'printer:${endpoint.host}:${endpoint.port}',
    PrinterConnection.serial ||
    PrinterConnection.spool => 'printer:${endpoint.endpoint}',
  };
}
