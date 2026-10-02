import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/formatters/decimal_money.dart';
import '../../../core/widgets/app_dialog.dart';
import 'weighed_product_math.dart';
import 'weighed_product_form.dart';
import 'weighed_product_selection.dart';

export 'weighed_product_selection.dart';

Future<WeighedProductSelection?> showWeighedProductDialog(
  BuildContext context, {
  required Map<String, dynamic> product,
  required List<Map<String, dynamic>> scales,
  required String? initialScaleId,
  required Future<Map<String, dynamic>> Function(String scaleId) readScale,
}) => showDialog<WeighedProductSelection>(
  context: context,
  builder: (_) => _WeighedProductDialog(
    product: product,
    scales: scales,
    initialScaleId: initialScaleId,
    readScale: readScale,
  ),
);

class _WeighedProductDialog extends StatefulWidget {
  const _WeighedProductDialog({
    required this.product,
    required this.scales,
    required this.initialScaleId,
    required this.readScale,
  });

  final Map<String, dynamic> product;
  final List<Map<String, dynamic>> scales;
  final String? initialScaleId;
  final Future<Map<String, dynamic>> Function(String scaleId) readScale;

  @override
  State<_WeighedProductDialog> createState() => _WeighedProductDialogState();
}

class _WeighedProductDialogState extends State<_WeighedProductDialog> {
  final _entry = TextEditingController();
  final _note = TextEditingController();
  late String? _scaleId = widget.initialScaleId;
  WeighedProductEntryMode _mode = WeighedProductEntryMode.weight;
  Map<String, dynamic>? _reading;
  String? _message;
  bool _readingScale = false;
  bool _settingEntry = false;

  int get _priceCents =>
      DecimalMoney.minorUnits(widget.product['current_price']);

  int get _weightGrams => _mode == WeighedProductEntryMode.weight
      ? WeighedProductMath.weightGramsFromInput(_entry.text)
      : WeighedProductMath.weightGramsForAmount(
          amount: _entry.text,
          pricePerKg: widget.product['current_price'],
        );

  int get _totalCents => WeighedProductMath.totalInCents(
    _weightGrams,
    widget.product['current_price'],
  );

  bool get _canAdd => _weightGrams > 0 && _priceCents > 0 && !_readingScale;

  @override
  void initState() {
    super.initState();
    _entry.addListener(_entryChanged);
  }

  @override
  void dispose() {
    _entry.removeListener(_entryChanged);
    _entry.dispose();
    _note.dispose();
    super.dispose();
  }

  void _entryChanged() {
    if (_settingEntry || !mounted) return;
    setState(() {
      _reading = null;
      _message = null;
    });
  }

  void _setEntry(String value) {
    _settingEntry = true;
    _entry.text = value;
    _settingEntry = false;
  }

  void _changeMode(WeighedProductEntryMode mode) {
    final grams = _weightGrams;
    setState(() {
      _mode = mode;
      _reading = null;
      _message = null;
      _setEntry(
        mode == WeighedProductEntryMode.weight
            ? WeighedProductMath.weightText(grams)
            : DecimalMoney.format(_totalCents),
      );
    });
  }

  Future<void> _readScale() async {
    final scaleId = _scaleId;
    if (scaleId == null || _readingScale) return;
    setState(() {
      _readingScale = true;
      _message = null;
    });
    try {
      final reading = await widget.readScale(scaleId);
      final value = reading['net_weight_kg'] ?? reading['weight_kg'];
      final grams = WeighedProductMath.weightGramsFromInput('$value');
      if (!mounted) return;
      setState(() {
        _reading = reading;
        _mode = WeighedProductEntryMode.weight;
        _setEntry(WeighedProductMath.weightText(grams));
        _message = reading['is_stable'] == false
            ? 'Leitura recebida; confirme a estabilidade na balança.'
            : null;
      });
    } catch (error) {
      if (mounted) setState(() => _message = '$error');
    } finally {
      if (mounted) setState(() => _readingScale = false);
    }
  }

  void _confirm() {
    if (!_canAdd) return;
    Navigator.pop(
      context,
      WeighedProductSelection(
        weightKg: _weightGrams / 1000,
        note: _note.text.trim(),
        scaleReading: _reading,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.enter): _confirm,
        const SingleActivator(LogicalKeyboardKey.numpadEnter): _confirm,
      },
      child: Focus(
        autofocus: true,
        child: AppDialog(
          maxWidth: 540,
          title: WeighedProductTitle(product: widget.product),
          content: SizedBox(
            width: 480,
            child: WeighedProductForm(
              mode: _mode,
              entryController: _entry,
              noteController: _note,
              scales: widget.scales,
              scaleId: _scaleId,
              onModeChanged: _changeMode,
              onScaleChanged: (value) => setState(() {
                _scaleId = value;
                _reading = null;
              }),
              onReadScale: _readScale,
              readingScale: _readingScale,
              weightGrams: _weightGrams,
              totalCents: _totalCents,
              message: _message,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: _canAdd ? _confirm : null,
              icon: const Icon(Icons.add),
              label: const Text('Adicionar'),
            ),
          ],
        ),
      ),
    );
  }
}
