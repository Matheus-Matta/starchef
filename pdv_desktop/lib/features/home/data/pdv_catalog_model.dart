import 'pdv_repository.dart';

class PdvCatalog {
  const PdvCatalog({
    required this.cashStations,
    required this.products,
    required this.categories,
    required this.tables,
    required this.commands,
    required this.paymentMethods,
  });

  /// Na ordem de [CatalogoDoPdv._consultasDoCatalogo].
  factory PdvCatalog.fromLists(List<List<JsonMap>> listas) => PdvCatalog(
    cashStations: listas[0],
    products: listas[1],
    categories: listas[2],
    tables: listas[3],
    commands: listas[4],
    paymentMethods: listas[5],
  );

  Map<String, dynamic> toJson() => {
    'cash_stations': cashStations,
    'products': products,
    'categories': categories,
    'tables': tables,
    'commands': commands,
    'payment_methods': paymentMethods,
  };

  final List<JsonMap> cashStations;
  final List<JsonMap> products;
  final List<JsonMap> categories;
  final List<JsonMap> tables;
  final List<JsonMap> commands;
  final List<JsonMap> paymentMethods;
}
