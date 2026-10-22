import '../../../core/input/pdv_shortcuts.dart';

/// Enquanto o "Concluir" espera o servidor, a tela não muda de venda.
///
/// Esc ou Ctrl+N no meio da espera voltavam a tela e começavam outra
/// venda; a resposta chegava depois, limpava o rascunho e mandava a tela para
/// a "próxima venda" — apagando o carrinho do cliente seguinte, sem aviso. Só
/// a ajuda responde: ela abre por cima e não mexe em venda nenhuma.
bool atalhoValeDuranteAConclusao(String acao) => acao == PdvAction.help;
