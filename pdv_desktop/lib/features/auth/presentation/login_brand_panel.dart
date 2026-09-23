import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_theme.dart';

class LoginBrandPanel extends StatelessWidget {
  const LoginBrandPanel({super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(48),
    decoration: const BoxDecoration(
      color: AppColors.zinc900,
      border: Border(right: BorderSide(color: AppColors.orange, width: 4)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Image.asset(
              'assets/logoicon.png',
              width: 46,
              height: 46,
              filterQuality: FilterQuality.high,
            ),
            const SizedBox(width: 12),
            const Text(
              'StarChef',
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const Spacer(),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A cozinha e o salão, no mesmo ritmo.',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 38,
                  height: 1.1,
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: 20),
              Text(
                'Pedidos, comandas, caixa e equipamentos locais em um só lugar para o seu restaurante.',
                style: TextStyle(
                  color: Color(0xFFFFDFD0),
                  fontSize: 15,
                  height: 1.6,
                  fontWeight: FontWeight.w500,
                ),
              ),
              SizedBox(height: 28),
              Wrap(
                spacing: 28,
                runSpacing: 20,
                children: [
                  _Feature(
                    icon: Icons.receipt_long_outlined,
                    label: 'Pedidos & comandas',
                  ),
                  _Feature(
                    icon: Icons.desktop_windows_outlined,
                    label: 'KDS ao vivo',
                  ),
                  _Feature(
                    icon: Icons.payments_outlined,
                    label: 'Caixa & pagamentos',
                  ),
                ],
              ),
            ],
          ),
        ),
        const Spacer(),
        const Text(
          '© 2026 StarChef · PDV desktop',
          style: TextStyle(color: Color(0xFFFFD0BB), fontSize: 12),
        ),
      ],
    ),
  );
}

class _Feature extends StatelessWidget {
  const _Feature({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 105,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .16),
            borderRadius: AppTheme.radius,
            border: Border.all(color: Colors.white24),
          ),
          child: Icon(icon, color: Colors.white, size: 21),
        ),
        const SizedBox(height: 9),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );
}
