import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../errors/app_error.dart';
import '../errors/app_error_host.dart';
import '../network/api_exception.dart';

/// Copia uma mensagem para a área de transferência e confirma na tela.
Future<void> copyError(BuildContext context, String message) async {
  await Clipboard.setData(ClipboardData(text: message));
  if (!context.mounted) return;
  ScaffoldMessenger.maybeOf(context)?.showSnackBar(
    const SnackBar(
      content: Text('Erro copiado para a área de transferência.'),
      duration: Duration(milliseconds: 1500),
    ),
  );
}

/// Publica uma falha no alerta global do aplicativo.
///
/// Existe um único caminho para erros visíveis: o [ErrorCenter]. Ele garante o
/// botão de fechar exigido pelo backlog, preserva a mensagem do backend, guarda
/// o detalhe técnico no log e permite copiar tudo. Este atalho mantém as
/// chamadas antigas curtas sem abrir um segundo caminho paralelo.
void showAppError(
  BuildContext context,
  Object error, {
  String? title,
  String? recommendedAction,
}) {
  final center = ErrorCenterScope.read(context);
  if (error is ApiException) {
    center.reportApi(error, title: title, recommendedAction: recommendedAction);
    return;
  }
  if (error is AppError) {
    center.report(error);
    return;
  }
  if (error is String) {
    center.report(
      AppError(
        title: title ?? 'Não foi possível concluir',
        message: error,
        recommendedAction: recommendedAction,
      ),
    );
    return;
  }
  center.reportUnexpected(error, title: title);
}

/// Confirmação rápida (sucesso ou aviso leve) no mesmo cartão do topo direito.
///
/// Substitui o `SnackBar` de rodapé espalhado pela interface: um único lugar
/// para tudo que aparece sozinho na tela, avisos de verdade e confirmações
/// juntos. Diferente de [showAppError], soma sozinho depois de
/// [autoDismissAfter] — o operador não precisa fechar um "impresso com
/// sucesso" no `X`.
void showAppToast(
  BuildContext context,
  String message, {
  String? title,
  AppErrorSeverity severity = AppErrorSeverity.info,
  Duration autoDismissAfter = const Duration(milliseconds: 2200),
}) {
  ErrorCenterScope.read(context).report(
    AppError(
      title: title ?? (severity == AppErrorSeverity.warning ? 'Atenção' : 'Concluído'),
      message: message,
      severity: severity,
      autoDismissAfter: autoDismissAfter,
    ),
  );
}
