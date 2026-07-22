import 'package:flutter/material.dart';

import '../../auth/presentation/auth_controller.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.controller});

  final AuthController controller;

  @override
  Widget build(BuildContext context) {
    final user = controller.session!.user;
    final displayName = user.name.isEmpty ? user.username : user.name;
    return Scaffold(
      appBar: AppBar(
        title: const Text('StarChef PDV'),
        actions: [
          IconButton(
            tooltip: 'Sair',
            onPressed: controller.logout,
            icon: const Icon(Icons.logout),
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.check_circle,
              size: 64,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 18),
            Text(
              'Acesso realizado, $displayName',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(user.branchName ?? user.restaurantName ?? 'StarChef'),
            const SizedBox(height: 8),
            const Text('A tela de pedidos será conectada nesta área.'),
          ],
        ),
      ),
    );
  }
}
