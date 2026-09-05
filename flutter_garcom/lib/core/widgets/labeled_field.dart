import 'package:flutter/material.dart';

/// Campo de formulário com rótulo acima, no formato do shadcn.
///
/// O campo em si é Material (`TextFormField`): ele traz validação, teclado e
/// autofill de graça, e é o mesmo caminho já usado no PDV. O visual — borda,
/// raio, altura de toque, cor de foco — vem inteiro do tema
/// (`AppTheme.inputDecorationTheme`); aqui não sobra nenhum número solto, que
/// era justamente o que fazia este campo divergir dos outros do app quando o
/// tema mudava.
class LabeledField extends StatelessWidget {
  const LabeledField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.icon,
    this.obscureText = false,
    this.keyboardType,
    this.textInputAction,
    this.validator,
    this.onSubmitted,
    this.suffix,
    this.autofillHints,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? icon;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final String? Function(String?)? validator;
  final ValueChanged<String>? onSubmitted;
  final Widget? suffix;
  final Iterable<String>? autofillHints;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        label,
        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
      const SizedBox(height: 6),
      TextFormField(
        controller: controller,
        obscureText: obscureText,
        keyboardType: keyboardType,
        textInputAction: textInputAction,
        validator: validator,
        autofillHints: autofillHints,
        onFieldSubmitted: onSubmitted,
        decoration: InputDecoration(
          hintText: hint,
          prefixIcon: icon == null ? null : Icon(icon, size: 20),
          suffixIcon: suffix,
        ),
      ),
    ],
  );
}
