import 'package:flutter/material.dart';

/// Paleta compartilhada com o PDV desktop (`flutter/lib/core/theme`), para o
/// garçom e o caixa parecerem o mesmo produto.
///
/// Mesmo arquivo, mesmo nome e mesmos valores dos dois lados: quando uma cor
/// muda, ela muda nos dois apps sem ninguém precisar lembrar do outro.
abstract final class AppColors {
  static const orange = Color(0xFFEA580C);

  /// Laranja do tema escuro: o mesmo `primary`, um passo mais claro para
  /// continuar legível sobre fundo preto.
  static const orangeLight = Color(0xFFF97316);
  static const danger = Color(0xFFDC2626);
  static const success = Color(0xFF16A34A);
  static const warning = Color(0xFFD97706);
  static const zinc50 = Color(0xFFFAFAFA);
  static const zinc100 = Color(0xFFF4F4F5);
  static const zinc200 = Color(0xFFE4E4E7);
  static const zinc300 = Color(0xFFD4D4D8);
  static const zinc400 = Color(0xFFA1A1AA);
  static const zinc500 = Color(0xFF71717A);
  static const zinc700 = Color(0xFF3F3F46);
  static const zinc800 = Color(0xFF27272A);
  static const zinc900 = Color(0xFF18181B);
  static const zinc950 = Color(0xFF09090B);
}
