import 'package:flutter/foundation.dart';

import 'app_logger.dart';

/// Nenhum erro pode sumir em silêncio durante uma venda.
///
/// São dois caminhos, e os dois precisam de tratamento:
/// - [FlutterError.onError]: o que o framework captura (build, layout,
///   callbacks de toque);
/// - [PlatformDispatcher.onError]: o que escapa de um `Future` sem `catch`.
///   Sem este, uma falha num `unawaited(...)` da Balança Rápida não chegava ao
///   log e a tela ficava parada sem explicação.
void installGlobalErrorHandlers() {
  // Erros fora de um handler explícito ainda precisam chegar ao log; nenhum
  // deles pode desaparecer em silêncio durante uma venda.
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    // Sem o widget e a biblioteca, um estouro de layout vira uma linha de log
    // idêntica repetida por item da lista, e não dá para saber onde procurar.
    AppLogger.instance.error(
      'flutter_error',
      data: {
        'library': details.library,
        'context': details.context?.toString(),
        'widget': details.informationCollector == null
            ? null
            : DiagnosticsNode.message(
                details.informationCollector!()
                    .map((node) => node.toString())
                    .join(' | '),
              ).toString(),
      },
      cause: details.exception,
      stackTrace: details.stack,
    );
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    AppLogger.instance.error(
      'uncaught_async_error',
      cause: error,
      stackTrace: stack,
    );
    // Tratado: registrar e seguir é melhor do que derrubar o caixa.
    return true;
  };
}
