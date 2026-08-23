/// Localiza o restaurante do caixa ativo ao qual o usuário está vinculado.
///
/// A API serializa `operators` normalmente como uma lista de IDs, mas o
/// leitor também aceita objetos com `id` para continuar compatível caso a
/// representação seja enriquecida no futuro.
String? cashLinkedRestaurantId({
  required List<Map<String, dynamic>> cashStations,
  required String userId,
  required Set<String> availableRestaurantIds,
}) {
  final normalizedUserId = userId.trim();
  if (normalizedUserId.isEmpty) return null;

  for (final station in cashStations) {
    if (station['is_active'] == false) continue;
    final operators = station['operators'];
    if (operators is! List ||
        !operators.any(
          (operator) => _referenceId(operator) == normalizedUserId,
        )) {
      continue;
    }

    final restaurantId = _referenceId(
      station['restaurant'] ?? station['restaurant_id'],
    );
    if (restaurantId != null && availableRestaurantIds.contains(restaurantId)) {
      return restaurantId;
    }
  }
  return null;
}

String? _referenceId(Object? value) {
  final raw = value is Map ? value['id'] : value;
  final normalized = '${raw ?? ''}'.trim();
  return normalized.isEmpty ? null : normalized;
}
