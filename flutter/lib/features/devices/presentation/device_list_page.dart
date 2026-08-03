import 'dart:io';

import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/copyable_error.dart';
import '../domain/printer_endpoint.dart';
import '../services/local_device_agent.dart';

enum DeviceKind { printer, scale }

Map<String, dynamic> _deviceSettings(Map<String, dynamic>? item) =>
    item?['settings'] as Map<String, dynamic>? ?? const {};

String _savedConnectionType(Map<String, dynamic>? item) =>
    '${_deviceSettings(item)['connection_type'] ?? item?['connection_type'] ?? 'windows'}';

class DeviceListPage extends StatefulWidget {
  const DeviceListPage({
    super.key,
    required this.kind,
    required this.api,
    required this.token,
    required this.restaurantId,
  });

  final DeviceKind kind;
  final ApiClient api;
  final String token;
  final String restaurantId;

  @override
  State<DeviceListPage> createState() => _DeviceListPageState();
}

class _DeviceListPageState extends State<DeviceListPage> {
  bool loading = true;
  String? loadError;
  String search = '';
  List<Map<String, dynamic>> rows = [];

  String get title =>
      widget.kind == DeviceKind.printer ? 'Impressoras' : 'Balanças';
  String get path =>
      widget.kind == DeviceKind.printer ? '/printers/' : '/scales/';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      loadError = null;
    });
    try {
      final data = await widget.api.get(
        path,
        query: {'restaurant': widget.restaurantId, 'page_size': 300},
        accessToken: widget.token,
      );
      rows = ((data['results'] ?? const []) as List)
          .cast<Map<String, dynamic>>()
          .where((item) => '${item['restaurant']}' == widget.restaurantId)
          .toList();
    } on ApiException catch (error) {
      loadError = error.message;
      if (mounted) {
        showAppError(context, error);
      }
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _edit([Map<String, dynamic>? item]) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => DeviceEditPage(
          kind: widget.kind,
          api: widget.api,
          token: widget.token,
          restaurantId: widget.restaurantId,
          item: item,
        ),
      ),
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final filtered = rows.where((item) {
      final term = search.toLowerCase();
      return term.isEmpty ||
          '${item['name']} ${item['endpoint'] ?? ''} ${item['host'] ?? ''} ${item['port'] ?? ''} ${item['sector_name'] ?? ''}'
              .toLowerCase()
              .contains(term);
    }).toList();
    return Scaffold(
      appBar: AppBar(
        leading: const BackButton(),
        title: Text(title),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          const SizedBox(width: 12),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Configuração de $title',
                        style: Theme.of(context).textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Cadastre e mantenha os equipamentos deste restaurante.',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(
                  width: 280,
                  child: TextField(
                    onChanged: (value) => setState(() => search = value),
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      hintText: 'Filtrar...',
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: () => _edit(),
                  icon: const Icon(Icons.add),
                  label: Text(
                    widget.kind == DeviceKind.printer
                        ? 'Nova impressora'
                        : 'Nova balança',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            Expanded(
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: loading
                    ? const Center(child: CircularProgressIndicator())
                    : loadError != null
                    ? _LoadFailure(message: loadError!, onRetry: _load)
                    : filtered.isEmpty
                    ? _EmptyDevices(kind: widget.kind, onCreate: () => _edit())
                    : LayoutBuilder(
                        builder: (context, constraints) {
                          final calculatedRows =
                              ((constraints.maxHeight - 180) / 48).floor();
                          final rowsPerPage = calculatedRows.clamp(1, 10);
                          final tableWidth = constraints.maxWidth < 900
                              ? 900.0
                              : constraints.maxWidth;
                          final pageOptions = <int>{
                            rowsPerPage,
                            5,
                            10,
                            20,
                            50,
                          }.toList()..sort();
                          return SingleChildScrollView(
                            scrollDirection: Axis.horizontal,
                            child: SizedBox(
                              width: tableWidth,
                              child: PaginatedDataTable(
                                header: Text('$title cadastradas'),
                                showCheckboxColumn: false,
                                rowsPerPage: rowsPerPage,
                                availableRowsPerPage: pageOptions,
                                showFirstLastButtons: true,
                                columnSpacing: 42,
                                horizontalMargin: 24,
                                dataRowMinHeight: 44,
                                dataRowMaxHeight: 48,
                                columns: [
                                  const DataColumn(label: Text('Nome')),
                                  DataColumn(
                                    label: Text(
                                      widget.kind == DeviceKind.printer
                                          ? 'Driver'
                                          : 'Protocolo',
                                    ),
                                  ),
                                  DataColumn(
                                    label: Text(
                                      widget.kind == DeviceKind.printer
                                          ? 'Conexão'
                                          : 'Porta',
                                    ),
                                  ),
                                  const DataColumn(label: Text('Setor')),
                                  const DataColumn(label: Text('Status')),
                                  const DataColumn(label: Text('Ações')),
                                ],
                                source: _DeviceSource(
                                  filtered,
                                  widget.kind,
                                  _edit,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadFailure extends StatelessWidget {
  const _LoadFailure({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.error_outline,
            size: 48,
            color: Theme.of(context).colorScheme.error,
          ),
          const SizedBox(height: 14),
          Text(
            message,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            alignment: WrapAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: () => copyError(context, message),
                icon: const Icon(Icons.copy_outlined),
                label: const Text('Copiar erro'),
              ),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _EmptyDevices extends StatelessWidget {
  const _EmptyDevices({required this.kind, required this.onCreate});

  final DeviceKind kind;
  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    final printer = kind == DeviceKind.printer;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              printer ? Icons.print_outlined : Icons.scale_outlined,
              size: 52,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 14),
            Text(
              printer
                  ? 'Nenhuma impressora neste restaurante'
                  : 'Nenhuma balança neste restaurante',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            const Text(
              'Cadastre o primeiro equipamento para ele aparecer nesta lista.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onCreate,
              icon: const Icon(Icons.add),
              label: Text(
                printer ? 'Cadastrar impressora' : 'Cadastrar balança',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DeviceSource extends DataTableSource {
  _DeviceSource(this.rows, this.kind, this.onEdit);
  final List<Map<String, dynamic>> rows;
  final DeviceKind kind;
  final ValueChanged<Map<String, dynamic>> onEdit;

  @override
  DataRow? getRow(int index) {
    if (index >= rows.length) return null;
    final item = rows[index];
    return DataRow.byIndex(
      index: index,
      cells: [
        DataCell(Text('${item['name']}')),
        DataCell(
          Text(
            '${item[kind == DeviceKind.printer ? 'driver_type' : 'protocol']}',
          ),
        ),
        DataCell(
          Text(
            kind == DeviceKind.printer
                ? _printerConnection(item)
                : '${item['port'] ?? '—'}',
          ),
        ),
        DataCell(Text('${item['sector_name'] ?? 'Sem setor'}')),
        DataCell(
          Chip(label: Text(item['is_active'] == true ? 'Ativo' : 'Inativo')),
        ),
        DataCell(
          IconButton(
            tooltip: 'Ver e editar',
            onPressed: () => onEdit(item),
            icon: const Icon(Icons.edit_outlined),
          ),
        ),
      ],
    );
  }

  @override
  int get rowCount => rows.length;
  @override
  bool get isRowCountApproximate => false;
  @override
  int get selectedRowCount => 0;

  static String _printerConnection(Map<String, dynamic> item) =>
      PrinterEndpoint.fromJson(item).describe;
}

class DeviceEditPage extends StatefulWidget {
  const DeviceEditPage({
    super.key,
    required this.kind,
    required this.api,
    required this.token,
    required this.restaurantId,
    this.item,
  });
  final DeviceKind kind;
  final ApiClient api;
  final String token;
  final String restaurantId;
  final Map<String, dynamic>? item;

  @override
  State<DeviceEditPage> createState() => _DeviceEditPageState();
}

class _DeviceEditPageState extends State<DeviceEditPage> {
  final formKey = GlobalKey<FormState>();
  late final name = TextEditingController(
    text: '${widget.item?['name'] ?? ''}',
  );
  late final connection = TextEditingController(
    text:
        '${widget.item?[widget.kind == DeviceKind.printer ? 'endpoint' : 'port'] ?? ''}',
  );
  late final maxAge = TextEditingController(
    text: '${widget.item?['reading_max_age_seconds'] ?? 120}',
  );
  late final delay = TextEditingController(
    text: '${widget.item?['auto_print_delay_seconds'] ?? 3}',
  );
  late final baudRate = TextEditingController(
    text:
        '${(widget.item?['settings'] as Map<String, dynamic>?)?['baudrate'] ?? 9600}',
  );
  late final host = TextEditingController(
    text:
        '${widget.item?['host'] ?? _deviceSettings(widget.item)['host'] ?? ''}',
  );
  late final networkPort = TextEditingController(
    text:
        '${widget.item?['port'] ?? _deviceSettings(widget.item)['port'] ?? 9100}',
  );
  late final timeout = TextEditingController(
    text:
        '${widget.item?['timeout_seconds'] ?? _deviceSettings(widget.item)['timeout_seconds'] ?? 10}',
  );
  late String connectionType = _savedConnectionType(widget.item);
  late String type =
      '${widget.item?[widget.kind == DeviceKind.printer ? 'driver_type' : 'protocol'] ?? (widget.kind == DeviceKind.printer ? 'browser' : 'generic')}';
  late bool active = widget.item?['is_active'] as bool? ?? true;
  late bool autoPrint = widget.item?['auto_print'] as bool? ?? false;
  bool saving = false;
  bool testing = false;
  bool loadingChoices = true;
  List<Map<String, dynamic>> sectors = [];
  List<Map<String, dynamic>> printers = [];
  List<Map<String, dynamic>> products = [];
  List<String> localPrinters = [];
  List<String> localSerialPorts = [];
  late String? sectorId = widget.item?['sector']?.toString();
  late String? printerId = widget.item?['printer']?.toString();
  late String? productId = widget.item?['product']?.toString();

  @override
  void initState() {
    super.initState();
    _loadChoices();
  }

  Future<List<Map<String, dynamic>>> _list(String path) async {
    final data = await widget.api.get(
      path,
      query: {'restaurant': widget.restaurantId, 'page_size': 300},
      accessToken: widget.token,
    );
    return ((data['results'] ?? const []) as List).cast<Map<String, dynamic>>();
  }

  Future<void> _loadChoices() async {
    try {
      final result = await Future.wait([
        _list('/tables/sectors/'),
        if (widget.kind == DeviceKind.scale) _list('/printers/'),
        if (widget.kind == DeviceKind.scale) _list('/menu/products/'),
      ]);
      sectors = result[0];
      if (widget.kind == DeviceKind.scale) {
        printers = result[1];
        products = result[2];
      } else {
        localPrinters = await _loadWindowsPrinters();
      }
      localSerialPorts = await _loadWindowsSerialPorts();
    } on ApiException catch (error) {
      if (mounted) {
        showAppError(context, error);
      }
    } finally {
      if (mounted) setState(() => loadingChoices = false);
    }
  }

  Future<List<String>> _loadWindowsPrinters() async {
    if (!Platform.isWindows) return const [];
    try {
      final result = await Process.run('powershell.exe', const [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        'Get-Printer | Select-Object -ExpandProperty Name',
      ]).timeout(const Duration(seconds: 5));
      if (result.exitCode != 0) return const [];
      final names =
          '${result.stdout}'
              .split(RegExp(r'\r?\n'))
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toSet()
              .toList()
            ..sort();
      return names;
    } catch (_) {
      return const [];
    }
  }

  Future<List<String>> _loadWindowsSerialPorts() async {
    if (!Platform.isWindows) return const [];
    try {
      final result = await Process.run('powershell.exe', const [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        '[System.IO.Ports.SerialPort]::GetPortNames()',
      ]).timeout(const Duration(seconds: 5));
      if (result.exitCode != 0) return const [];
      final ports =
          '${result.stdout}'
              .split(RegExp(r'\r?\n'))
              .map((item) => item.trim().toUpperCase())
              .where((item) => RegExp(r'^COM\d+$').hasMatch(item))
              .toSet()
              .toList()
            ..sort((a, b) {
              final left = int.tryParse(a.substring(3)) ?? 0;
              final right = int.tryParse(b.substring(3)) ?? 0;
              return left.compareTo(right);
            });
      return ports;
    } catch (_) {
      return const [];
    }
  }

  List<Map<String, dynamic>> _uniqueById(List<Map<String, dynamic>> items) {
    final seen = <String>{};
    return items.where((item) => seen.add('${item['id']}')).toList();
  }

  @override
  void dispose() {
    name.dispose();
    connection.dispose();
    maxAge.dispose();
    delay.dispose();
    baudRate.dispose();
    host.dispose();
    networkPort.dispose();
    timeout.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!formKey.currentState!.validate()) return;
    setState(() => saving = true);
    try {
      final body = <String, dynamic>{
        'restaurant': widget.restaurantId,
        'name': name.text.trim(),
        'sector': sectorId,
        'is_active': active,
        'auto_print': autoPrint,
        'settings': {
          ...(widget.item?['settings'] as Map<String, dynamic>? ?? const {}),
          'executor': 'flutter_desktop',
          if (widget.kind == DeviceKind.printer) ...{
            'connection_type': connectionType,
            'host': host.text.trim().isEmpty ? null : host.text.trim(),
            'port': int.tryParse(networkPort.text) ?? 9100,
            'timeout_seconds': int.tryParse(timeout.text) ?? 10,
          },
          if (widget.kind == DeviceKind.scale ||
              (widget.kind == DeviceKind.printer && connectionType == 'serial'))
            'baudrate': int.tryParse(baudRate.text) ?? 9600,
        },
        if (widget.kind == DeviceKind.printer) ...{
          'driver_type': type,
          'connection_type': connectionType,
          'endpoint': connection.text.trim(),
          'host': host.text.trim().isEmpty ? null : host.text.trim(),
          'port': int.tryParse(networkPort.text) ?? 9100,
          'timeout_seconds': int.tryParse(timeout.text) ?? 10,
        } else ...{
          'protocol': type,
          'port': connection.text.trim(),
          'product': productId,
          'printer': printerId,
          'reading_max_age_seconds': int.tryParse(maxAge.text) ?? 120,
          'auto_print_delay_seconds': int.tryParse(delay.text) ?? 3,
        },
      };
      final saved = widget.item == null
          ? await widget.api.post(
              widget.kind == DeviceKind.printer ? '/printers/' : '/scales/',
              body: body,
              accessToken: widget.token,
            )
          : await widget.api.patch(
              '${widget.kind == DeviceKind.printer ? '/printers' : '/scales'}/${widget.item!['id']}/',
              body: body,
              accessToken: widget.token,
            );
      if (widget.kind == DeviceKind.printer &&
          _savedConnectionType(saved) != connectionType) {
        throw const ApiException(
          'O servidor não confirmou o tipo de conexão. Reinicie e atualize o backend antes de tentar novamente.',
        );
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (mounted) {
        showAppError(context, error);
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _testPrinter() async {
    final item = widget.item;
    if (item == null || testing) return;
    setState(() => testing = true);
    Map<String, dynamic>? job;
    try {
      job = await widget.api.post(
        '/printers/${item['id']}/test-connection/',
        body: const {},
        accessToken: widget.token,
      );
      final apiPrinter =
          job['printer'] as Map<String, dynamic>? ?? const <String, dynamic>{};
      final printer = <String, dynamic>{
        ...apiPrinter,
        'connection_type': connectionType,
        'endpoint': connection.text.trim().toUpperCase(),
        'host': host.text.trim().isEmpty ? null : host.text.trim(),
        'port': int.tryParse(networkPort.text) ?? 9100,
        'timeout_seconds': int.tryParse(timeout.text) ?? 10,
        'driver_type': type,
        'settings': {
          ...(apiPrinter['settings'] as Map<String, dynamic>? ?? const {}),
          'connection_type': connectionType,
          'host': host.text.trim().isEmpty ? null : host.text.trim(),
          'port': int.tryParse(networkPort.text) ?? 9100,
          'timeout_seconds': int.tryParse(timeout.text) ?? 10,
          'baudrate': int.tryParse(baudRate.text) ?? 9600,
        },
      };
      final payload = job['payload'] as Map<String, dynamic>? ?? const {};
      final text = '${payload['text_content'] ?? ''}'.trim();
      await LocalDeviceAgent(api: widget.api).printForPrinter(printer, text);
      await widget.api.post(
        '/print-jobs/${job['print_job_id']}/mark-printed/',
        body: const {},
        accessToken: widget.token,
      );
      if (mounted) {
        showAppToast(context, 'Conexão confirmada. A nota de teste foi impressa.');
      }
    } catch (error) {
      final jobId = job?['print_job_id'];
      if (jobId != null) {
        try {
          await widget.api.post(
            '/print-jobs/$jobId/mark-failed/',
            body: {'error': 'Falha no teste local: $error'},
            accessToken: widget.token,
          );
        } catch (_) {}
      }
      if (mounted) {
        showAppError(
          context,
          error,
          title: 'Não foi possível imprimir a nota de teste',
          recommendedAction:
              'Confira o endereço da impressora e se ela está ligada.',
        );
      }
    } finally {
      if (mounted) setState(() => testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final printer = widget.kind == DeviceKind.printer;
    final options = printer
        ? const [('browser', 'Navegador'), ('escpos', 'ESC/POS')]
        : const [
            ('generic', 'Genérico'),
            ('toledo_prt2', 'Toledo PRT2'),
            ('filizola', 'Filizola'),
            ('urano', 'Urano'),
          ];
    return Scaffold(
      appBar: AppBar(
        leading: const BackButton(),
        title: Text(
          '${widget.item == null ? 'Cadastrar' : 'Editar'} ${printer ? 'impressora' : 'balança'}',
        ),
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(28),
                child: Form(
                  key: formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Dados do equipamento',
                        style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'A configuração fica salva no backend e o PDV Desktop executa o equipamento localmente.',
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 24),
                      TextFormField(
                        controller: name,
                        decoration: const InputDecoration(
                          labelText: 'Nome',
                          helperText:
                              'Nome usado para identificar o equipamento.',
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? 'Informe o nome.'
                            : null,
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String?>(
                        key: ValueKey(
                          'sector-$sectorId-${_uniqueById(sectors).map((item) => item['id']).join('|')}',
                        ),
                        initialValue:
                            _uniqueById(
                              sectors,
                            ).any((item) => '${item['id']}' == sectorId)
                            ? sectorId
                            : null,
                        decoration: const InputDecoration(
                          labelText: 'Setor',
                          helperText: 'Setor atendido por este equipamento.',
                        ),
                        items: [
                          const DropdownMenuItem(
                            value: null,
                            child: Text('Todos os setores'),
                          ),
                          ..._uniqueById(sectors).map(
                            (item) => DropdownMenuItem(
                              value: '${item['id']}',
                              child: Text('${item['name']}'),
                            ),
                          ),
                        ],
                        onChanged: loadingChoices
                            ? null
                            : (value) => setState(() => sectorId = value),
                      ),
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: type,
                        decoration: InputDecoration(
                          labelText: printer ? 'Driver' : 'Protocolo',
                        ),
                        items: options
                            .map(
                              (option) => DropdownMenuItem(
                                value: option.$1,
                                child: Text(option.$2),
                              ),
                            )
                            .toList(),
                        onChanged: (value) => setState(() => type = value!),
                      ),
                      const SizedBox(height: 16),
                      if (printer) ...[
                        DropdownButtonFormField<String>(
                          initialValue: connectionType,
                          decoration: const InputDecoration(
                            labelText: 'Tipo de conexão',
                            helperText:
                                'Escolha como este computador acessa a impressora.',
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: 'windows',
                              child: Text('Windows / USB'),
                            ),
                            DropdownMenuItem(
                              value: 'network',
                              child: Text('Rede TCP/IP'),
                            ),
                            DropdownMenuItem(
                              value: 'serial',
                              child: Text('Porta serial'),
                            ),
                          ],
                          onChanged: (value) =>
                              setState(() => connectionType = value!),
                        ),
                        const SizedBox(height: 16),
                        if (connectionType == 'windows' &&
                            localPrinters.isNotEmpty)
                          DropdownButtonFormField<String>(
                            key: ValueKey(localPrinters.join('|')),
                            initialValue: connection.text.isEmpty
                                ? null
                                : connection.text,
                            decoration: const InputDecoration(
                              labelText: 'Impressora instalada no Windows',
                              helperText:
                                  'Inclui impressoras USB instaladas no Windows.',
                            ),
                            items:
                                {
                                      if (connection.text.isNotEmpty)
                                        connection.text,
                                      ...localPrinters,
                                    }
                                    .map(
                                      (item) => DropdownMenuItem(
                                        value: item,
                                        child: Text(item),
                                      ),
                                    )
                                    .toList(),
                            onChanged: loadingChoices
                                ? null
                                : (value) => connection.text = value ?? '',
                            validator: (value) =>
                                connectionType == 'windows' &&
                                    (value == null || value.trim().isEmpty)
                                ? 'Selecione a impressora do Windows.'
                                : null,
                          )
                        else if (connectionType == 'windows')
                          TextFormField(
                            controller: connection,
                            decoration: const InputDecoration(
                              labelText: 'Impressora do Windows',
                              helperText:
                                  'Informe o nome exato da impressora instalada.',
                            ),
                            validator: (value) =>
                                value == null || value.trim().isEmpty
                                ? 'Informe a impressora do Windows.'
                                : null,
                          )
                        else if (connectionType == 'network')
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                flex: 2,
                                child: TextFormField(
                                  controller: host,
                                  decoration: const InputDecoration(
                                    labelText: 'Endereço IP',
                                    helperText: 'Ex.: 192.168.1.50',
                                  ),
                                  validator: (value) =>
                                      value == null || value.trim().isEmpty
                                      ? 'Informe o endereço IP.'
                                      : null,
                                ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: TextFormField(
                                  controller: networkPort,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(
                                    labelText: 'Porta',
                                    helperText: 'Normalmente 9100',
                                  ),
                                  validator: (value) {
                                    final port = int.tryParse(value ?? '');
                                    return port == null ||
                                            port < 1 ||
                                            port > 65535
                                        ? 'Porta inválida.'
                                        : null;
                                  },
                                ),
                              ),
                            ],
                          )
                        else
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: localSerialPorts.isNotEmpty
                                    ? DropdownButtonFormField<String>(
                                        key: ValueKey(
                                          localSerialPorts.join('|'),
                                        ),
                                        initialValue: connection.text.isEmpty
                                            ? null
                                            : connection.text.toUpperCase(),
                                        decoration: const InputDecoration(
                                          labelText: 'Porta serial',
                                          helperText:
                                              'Portas COM detectadas neste computador.',
                                        ),
                                        items:
                                            {
                                                  if (connection
                                                      .text
                                                      .isNotEmpty)
                                                    connection.text
                                                        .toUpperCase(),
                                                  ...localSerialPorts,
                                                }
                                                .map(
                                                  (port) => DropdownMenuItem(
                                                    value: port,
                                                    child: Text(port),
                                                  ),
                                                )
                                                .toList(),
                                        onChanged: (value) =>
                                            connection.text = value ?? '',
                                        validator: (value) =>
                                            value == null || value.isEmpty
                                            ? 'Selecione a porta serial.'
                                            : null,
                                      )
                                    : TextFormField(
                                        controller: connection,
                                        textCapitalization:
                                            TextCapitalization.characters,
                                        decoration: const InputDecoration(
                                          labelText: 'Porta serial',
                                          helperText: 'Ex.: COM1 ou COM2',
                                        ),
                                        validator: (value) =>
                                            value == null ||
                                                !RegExp(
                                                  r'^COM\d+$',
                                                  caseSensitive: false,
                                                ).hasMatch(value.trim())
                                            ? 'Informe uma porta como COM1 ou COM2.'
                                            : null,
                                      ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: TextFormField(
                                  controller: baudRate,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(
                                    labelText: 'Velocidade',
                                    suffixText: 'baud',
                                  ),
                                ),
                              ),
                            ],
                          ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: timeout,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Timeout da conexão',
                            suffixText: 'segundos',
                            helperText:
                                'Tempo máximo para conectar ou enviar a impressão.',
                          ),
                          validator: (value) {
                            final seconds = int.tryParse(value ?? '');
                            return seconds == null ||
                                    seconds < 1 ||
                                    seconds > 120
                                ? 'Use um valor entre 1 e 120.'
                                : null;
                          },
                        ),
                      ] else if (localSerialPorts.isNotEmpty)
                        DropdownButtonFormField<String>(
                          key: ValueKey('scale-${localSerialPorts.join('|')}'),
                          initialValue: connection.text.isEmpty
                              ? null
                              : connection.text.toUpperCase(),
                          decoration: const InputDecoration(
                            labelText: 'Porta da balança',
                            helperText:
                                'Selecione COM1, COM2 ou outra porta detectada.',
                          ),
                          items:
                              {
                                    if (connection.text.isNotEmpty)
                                      connection.text.toUpperCase(),
                                    ...localSerialPorts,
                                  }
                                  .map(
                                    (port) => DropdownMenuItem(
                                      value: port,
                                      child: Text(port),
                                    ),
                                  )
                                  .toList(),
                          onChanged: (value) => connection.text = value ?? '',
                        )
                      else
                        TextFormField(
                          controller: connection,
                          textCapitalization: TextCapitalization.characters,
                          decoration: const InputDecoration(
                            labelText: 'Porta',
                            helperText: 'Ex.: COM1, COM2 ou /dev/ttyUSB0.',
                          ),
                        ),
                      if (!printer) ...[
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: baudRate,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Velocidade da porta',
                            helperText:
                                'Baud rate configurado na balança. Normalmente 9600.',
                            suffixText: 'baud',
                          ),
                        ),
                        const SizedBox(height: 16),
                        DropdownButtonFormField<String?>(
                          key: ValueKey(
                            'product-$productId-${_uniqueById(products).map((item) => item['id']).join('|')}',
                          ),
                          initialValue:
                              _uniqueById(
                                products,
                              ).any((item) => '${item['id']}' == productId)
                              ? productId
                              : null,
                          decoration: const InputDecoration(
                            labelText: 'Produto por quilo',
                            helperText:
                                'Produto usado para calcular o valor da pesagem.',
                          ),
                          items: [
                            const DropdownMenuItem(
                              value: null,
                              child: Text('Nenhum produto'),
                            ),
                            ..._uniqueById(products).map(
                              (item) => DropdownMenuItem(
                                value: '${item['id']}',
                                child: Text('${item['name']}'),
                              ),
                            ),
                          ],
                          onChanged: loadingChoices
                              ? null
                              : (value) => setState(() => productId = value),
                        ),
                        const SizedBox(height: 16),
                        DropdownButtonFormField<String?>(
                          key: ValueKey(
                            'printer-$printerId-${_uniqueById(printers).map((item) => item['id']).join('|')}',
                          ),
                          initialValue:
                              _uniqueById(
                                printers,
                              ).any((item) => '${item['id']}' == printerId)
                              ? printerId
                              : null,
                          decoration: const InputDecoration(
                            labelText: 'Impressora da pesagem',
                            helperText:
                                'Impressora que receberá a nota gerada pela balança.',
                          ),
                          items: [
                            const DropdownMenuItem(
                              value: null,
                              child: Text('Nenhuma impressora'),
                            ),
                            ..._uniqueById(printers).map(
                              (item) => DropdownMenuItem(
                                value: '${item['id']}',
                                child: Text('${item['name']}'),
                              ),
                            ),
                          ],
                          onChanged: loadingChoices
                              ? null
                              : (value) => setState(() => printerId = value),
                        ),
                        const SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: maxAge,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                  labelText: 'Validade da leitura',
                                  suffixText: 'segundos',
                                ),
                              ),
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: TextFormField(
                                controller: delay,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                  labelText: 'Espera para impressão',
                                  suffixText: 'segundos',
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 12),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Impressão automática'),
                        subtitle: Text(
                          printer
                              ? 'O PDV Desktop imprime automaticamente os trabalhos recebidos.'
                              : 'O PDV Desktop envia a leitura quando o peso estabilizar.',
                        ),
                        value: autoPrint,
                        onChanged: (value) => setState(() => autoPrint = value),
                      ),
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Equipamento ativo'),
                        value: active,
                        onChanged: (value) => setState(() => active = value),
                      ),
                      const SizedBox(height: 22),
                      if (printer && widget.item != null) ...[
                        SizedBox(
                          width: double.infinity,
                          height: 50,
                          child: OutlinedButton.icon(
                            onPressed: saving || testing ? null : _testPrinter,
                            icon: testing
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.print_outlined),
                            label: const Text('Testar conexão e imprimir nota'),
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      SizedBox(
                        width: double.infinity,
                        height: 50,
                        child: FilledButton.icon(
                          onPressed: saving ? null : _save,
                          icon: saving
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.save_outlined),
                          label: const Text('Salvar equipamento'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
