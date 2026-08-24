import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../cash/domain/cash_restaurant_selector.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../home/data/pdv_repository.dart';
import 'scale_workstation_page.dart';

class ScaleWindowPage extends StatefulWidget {
  const ScaleWindowPage({
    super.key,
    required this.controller,
    required this.preferences,
    required this.onClose,
    this.preferredRestaurantId,
  });

  final AuthController controller;
  final LocalPreferences preferences;
  final VoidCallback onClose;
  final String? preferredRestaurantId;

  @override
  State<ScaleWindowPage> createState() => _ScaleWindowPageState();
}

class _ScaleWindowPageState extends State<ScaleWindowPage> {
  List<Map<String, dynamic>> restaurants = const [];
  List<Map<String, dynamic>> products = const [];
  String? restaurantId;
  String? errorMessage;
  bool loading = true;
  bool stationRunning = false;

  PdvRepository get repository => PdvRepository(
    api: widget.controller.repository.apiClient,
    accessToken: widget.controller.session!.accessToken,
  );

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      errorMessage = null;
    });
    try {
      final loadedRestaurants = await repository.list(
        '/restaurants/',
        query: {'page_size': 300},
      );
      if (loadedRestaurants.isEmpty) {
        throw StateError('Nenhum restaurante está disponível para esta conta.');
      }
      final available = loadedRestaurants
          .map((item) => '${item['id']}')
          .toSet();
      String? linkedRestaurantId;
      if (restaurantId == null) {
        try {
          final cashStations = await repository.list(
            '/cash-stations/',
            query: {'page_size': 300, 'is_active': true},
          );
          linkedRestaurantId = cashLinkedRestaurantId(
            cashStations: cashStations,
            userId: widget.controller.session!.user.id,
            availableRestaurantIds: available,
          );
        } on ApiException {
          // A balança continua usando a seleção anterior quando o vínculo do
          // caixa não pode ser consultado, inclusive no modo offline.
        }
      }
      final preferred =
          restaurantId ??
          linkedRestaurantId ??
          widget.preferredRestaurantId ??
          widget.controller.session!.user.restaurantId;
      final selected = preferred != null && available.contains(preferred)
          ? preferred
          : '${loadedRestaurants.first['id']}';
      widget.controller.setActiveRestaurant(selected);
      await widget.controller.refreshSupervisorPassword(restaurantId: selected);
      final loadedProducts = await repository.list(
        '/menu/products/',
        query: {'page_size': 300, 'restaurant': selected, 'is_active': true},
      );
      if (!mounted) return;
      setState(() {
        restaurants = loadedRestaurants;
        products = loadedProducts;
        restaurantId = selected;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        errorMessage = error is StateError
            ? error.message
            : 'Não foi possível preparar a estação de balança.';
      });
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> _changeRestaurant(String value) async {
    if (value == restaurantId) return;
    setState(() => restaurantId = value);
    await _load();
  }

  List<Widget> _windowActions(BuildContext context) => [
    IconButton.outlined(
      tooltip: loading ? 'Recarregando dados...' : 'Recarregar dados',
      onPressed: loading ? null : _load,
      icon: loading
          ? const SizedBox.square(
              dimension: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.refresh),
    ),
    IconButton.outlined(
      tooltip: 'Encerrar sessão',
      onPressed: widget.controller.logout,
      icon: const Icon(Icons.logout),
    ),
    IconButton.outlined(
      tooltip: 'Fechar Balança Rápida',
      onPressed: widget.onClose,
      style: IconButton.styleFrom(
        foregroundColor: Theme.of(context).colorScheme.error,
      ),
      icon: const Icon(Icons.power_settings_new),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return AppPageScaffold(
        title: 'Estação de balança',
        description: 'Preparando equipamentos e cardápio da unidade.',
        actions: _windowActions(context),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (errorMessage != null || restaurantId == null) {
      return AppPageScaffold(
        title: 'Estação de balança',
        description: 'Operação dedicada para pesagem e comandas.',
        actions: _windowActions(context),
        body: AppEmptyState(
          icon: Icons.scale_outlined,
          title: 'Estação indisponível',
          description: errorMessage ?? 'Não foi possível preparar a balança.',
          action: FilledButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Tentar novamente'),
          ),
        ),
      );
    }
    return AppPageScaffold(
      title: 'Estação de balança',
      description: 'Pesagem, adicionais e leitura de comandas em uma só tela.',
      actions: _windowActions(context),
      showHeader: !stationRunning,
      padding: stationRunning ? EdgeInsets.zero : const EdgeInsets.all(16),
      body: ScaleWorkstationPage(
        api: widget.controller.repository.apiClient,
        accessToken: widget.controller.session!.accessToken,
        restaurants: restaurants,
        restaurantId: restaurantId,
        products: products,
        onRestaurantChanged: _changeRestaurant,
        preferences: widget.preferences,
        onRunningChanged: (running) {
          if (mounted && stationRunning != running) {
            setState(() => stationRunning = running);
          }
        },
      ),
    );
  }
}
