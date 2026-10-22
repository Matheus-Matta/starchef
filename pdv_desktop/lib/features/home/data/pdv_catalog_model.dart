import 'pdv_repository.dart';

class PdvCatalog {
  const PdvCatalog({
    required this.cashStations,
    required this.products,
    required this.categories,
    required this.tables,
    required this.commands,
    required this.paymentMethods,
    this.carregandoProdutos = false,
  });

  /// Na ordem de [CatalogoDoPdv._consultasDoCatalogo].
  factory PdvCatalog.fromLists(
    List<List<JsonMap>> listas, {
    bool carregandoProdutos = false,
  }) => PdvCatalog(
    cashStations: listas[0],
    products: listas[1],
    categories: listas[2],
    tables: listas[3],
    commands: listas[4],
    paymentMethods: listas[5],
    carregandoProdutos: carregandoProdutos,
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

  /// Só a primeira página de produtos chegou; o resto vem por trás
  /// (`produtos_em_paginas.dart`). Fora do `toJson`: não é dado do catálogo.
  final bool carregandoProdutos;
}
