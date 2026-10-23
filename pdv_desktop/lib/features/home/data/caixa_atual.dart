import '../../../core/network/api_exception.dart';

/// O caixa que a tela deve mostrar depois de `/cash-register/current/` recusar.
///
/// 404 é "nenhum caixa aberto"; 403/409, o caixa está com outra pessoa ou com
/// este operador em outra máquina. Nos três, a sessão que a tela segurava não
/// vale mais aqui, e `null` é o que mostra "Abra o caixa para iniciar". A
/// releitura do aviso de caixa engolia o 404 e deixava a sessão FECHADA na
/// tela, sem o bloqueio.
///
/// Qualquer outra falha (rede, 500) não diz nada sobre o caixa: a tela segue
/// como estava, em vez de travar o operador no meio da venda.
Map<String, dynamic>? caixaAposRecusa(
  ApiException erro,
  Map<String, dynamic>? atual,
) => const {403, 404, 409}.contains(erro.statusCode) ? null : atual;
