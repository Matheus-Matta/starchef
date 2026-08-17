import 'package:flutter/material.dart';

import '../../../core/storage/local_preferences.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../home/data/pdv_repository.dart';
import 'scale_workstation_page.dart';

class ScaleWindowPage extends StatefulWidget {
  const ScaleWindowPage({
    super.key,
    required this.controller,
    required this.preferences,
    required this.isFullScreen,
    required this.onToggleFullScreen,
    this.preferredRestaurantId,
  });

  final AuthController controller;
  final LocalPreferences preferences;
  final bool isFullScreen;
  final VoidCallback onToggleFullScreen;
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
      final preferred =
          restaurantId ??
          widget.preferredRestaurantId ??
          widget.controller.session!.user.restaurantId;
      final selected = preferred != null && available.contains(preferred)
          ? preferred
          : '${loadedRestaurants.first['id']}';
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

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (errorMessage != null || restaurantId == null) {
      return Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.scale_outlined,
                    size: 54,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    errorMessage ?? 'Estação indisponível.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Tentar novamente'),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }
    return Scaffold(
      body: ScaleWorkstationPage(
        api: widget.controller.repository.apiClient,
        accessToken: widget.controller.session!.accessToken,
        restaurants: restaurants,
        restaurantId: restaurantId,
        products: products,
        onRestaurantChanged: _changeRestaurant,
        preferences: widget.preferences,
        isFullScreen: widget.isFullScreen,
        onToggleFullScreen: widget.onToggleFullScreen,
      ),
    );
  }
}
