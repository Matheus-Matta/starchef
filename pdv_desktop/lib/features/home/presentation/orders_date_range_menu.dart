import 'package:flutter/material.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';

/// Atalhos e calendário compacto no mesmo menu ancorado ao filtro de Pedidos.
class OrdersDateRangeMenu extends StatefulWidget {
  const OrdersDateRangeMenu({
    super.key,
    required this.label,
    required this.range,
    required this.onChanged,
  });

  final String label;
  final DateTimeRange? range;
  final ValueChanged<DateTimeRange?> onChanged;

  @override
  State<OrdersDateRangeMenu> createState() => _OrdersDateRangeMenuState();
}

class _OrdersDateRangeMenuState extends State<OrdersDateRangeMenu> {
  final MenuController _menu = MenuController();
  bool _custom = false;
  DateTime? _start;
  DateTime? _end;

  void _apply(DateTimeRange? value) {
    _menu.close();
    widget.onChanged(value);
  }

  void _selectDate(DateTime value) {
    setState(() {
      if (_start == null || _end != null) {
        _start = value;
        _end = null;
      } else if (value.isBefore(_start!)) {
        _start = value;
      } else {
        _end = value;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTimeRange lastDays(int count) => DateTimeRange(
      start: today.subtract(Duration(days: count - 1)),
      end: today,
    );

    return MenuAnchor(
      controller: _menu,
      builder: (context, controller, _) => OutlinedButton.icon(
        onPressed: () {
          if (controller.isOpen) {
            controller.close();
          } else {
            setState(() {
              _custom = false;
              _start = widget.range?.start;
              _end = widget.range?.end;
            });
            controller.open();
          }
        },
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, AppTheme.controlHeight),
          padding: const EdgeInsets.symmetric(horizontal: 10),
          textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        icon: const Icon(Icons.date_range_outlined, size: 16),
        label: Text(widget.label, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
      menuChildren: _custom
          ? [_calendar(today)]
          : [
              MenuItemButton(
                onPressed: () =>
                    _apply(DateTimeRange(start: today, end: today)),
                child: const Text('Hoje'),
              ),
              MenuItemButton(
                onPressed: () => _apply(
                  DateTimeRange(
                    start: today.subtract(const Duration(days: 1)),
                    end: today.subtract(const Duration(days: 1)),
                  ),
                ),
                child: const Text('Ontem'),
              ),
              MenuItemButton(
                onPressed: () => _apply(lastDays(7)),
                child: const Text('Últimos 7 dias'),
              ),
              MenuItemButton(
                onPressed: () => _apply(lastDays(30)),
                child: const Text('Últimos 30 dias'),
              ),
              MenuItemButton(
                onPressed: () => _apply(
                  DateTimeRange(
                    start: DateTime(today.year, today.month, 1),
                    end: today,
                  ),
                ),
                child: const Text('Este mês'),
              ),
              const Divider(height: 1),
              TextButton(
                onPressed: () => setState(() => _custom = true),
                child: const Align(
                  alignment: Alignment.centerLeft,
                  child: Text('Personalizado…'),
                ),
              ),
              if (widget.range != null)
                MenuItemButton(
                  onPressed: () => _apply(null),
                  child: const Text('Limpar período'),
                ),
            ],
    );
  }

  Widget _calendar(DateTime today) => SizedBox(
    width: 320,
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Voltar aos períodos rápidos',
                onPressed: () => setState(() => _custom = false),
                icon: const Icon(Icons.arrow_back, size: 18),
              ),
              const Expanded(child: Text('Início e fim · ou apenas um dia')),
            ],
          ),
        ),
        SizedBox(
          height: 330,
          child: CalendarDatePicker(
            initialDate: _start ?? today,
            firstDate: DateTime(today.year - 2),
            lastDate: DateTime(today.year + 1),
            onDateChanged: _selectDate,
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _start == null
                      ? 'Escolha a data inicial'
                      : '${_short(_start!)}${_end == null ? '' : ' – ${_short(_end!)}'}',
                ),
              ),
              FilledButton(
                onPressed: _start == null
                    ? null
                    : () => _apply(
                        DateTimeRange(start: _start!, end: _end ?? _start!),
                      ),
                child: const Text('Aplicar'),
              ),
            ],
          ),
        ),
      ],
    ),
  );

  static String _short(DateTime date) =>
      '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}';
}
