import '../network/api_exception.dart';
import '../relay/principal_client.dart';
import '../relay/relay_gateway.dart';

/// Traduz uma falha para a linguagem do salão.
///
/// Vive no núcleo, e não na tela de pedidos onde nasceu: a tela de detalhe
/// importava `orders_page.dart` só por causa desta função, e uma página passava
/// a depender da outra por um motivo que não era de nenhuma das duas.
///
/// [MutationQueued] não é erro: é a operação salva com sucesso no aparelho,
/// esperando o Caixa Principal responder. O texto diz isso, para o garçom não
/// repetir um lançamento que já está a caminho.
String describeFailure(Object error) {
  if (error is MutationQueued) {
    return 'Sem conexão: "${error.mutation.summary}" foi salvo e será '
        'enviado quando o Caixa Principal responder.';
  }
  if (error is PrincipalUnavailable) return error.message;
  if (error is ApiException) return error.message;
  return 'Falha inesperada: $error';
}
