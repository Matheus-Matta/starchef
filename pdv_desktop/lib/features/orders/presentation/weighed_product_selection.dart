class WeighedProductSelection {
  const WeighedProductSelection({
    required this.weightKg,
    required this.note,
    this.scaleReading,
  });

  final double weightKg;
  final String note;
  final Map<String, dynamic>? scaleReading;
}
