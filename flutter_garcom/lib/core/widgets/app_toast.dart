import 'package:flutter/material.dart';

/// Recado curto no rodapé — o retorno de toda ação do garçom.
///
/// Era um `_toast` privado repetido em três telas, cada uma reescrevendo o
/// mesmo `ScaffoldMessenger.of(context).showSnackBar(SnackBar(...))`.
void showToast(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}
