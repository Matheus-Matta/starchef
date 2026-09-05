import '../../../core/theme/app_theme.dart';

/// Quantas linhas de pedido cabem na altura disponível.
///
/// A tabela paginada NÃO rola por dentro: ela desenha o número de linhas que
/// mandarem, e se esse número não couber no espaço a tela estoura. Então a
/// conta precisa acertar dos dois lados — reservar de menos quebra o layout,
/// reservar de mais deixa uma faixa vazia embaixo da paginação.
///
/// Fica fora da tela, e não como um número solto dentro do `LayoutBuilder`,
/// porque é a única parte disso que dá para provar com um teste.
abstract final class OrdersTableMetrics {
  /// O que a tabela gasta fora das linhas.
  ///
  /// Medido, e não deduzido: uma tabela de uma linha mede 148 px, e a linha
  /// vale 36 — o resto é o cabeçalho das colunas (uma linha), a barra de
  /// paginação e o respiro que o Material põe em volta dela. A primeira
  /// tentativa foi somar as partes documentadas e deu 16 px a menos, o
  /// suficiente para a tabela estourar numa tela de 768. O teste refaz a
  /// medida a cada execução, então este número não pode envelhecer calado.
  ///
  /// Não entra aqui o título da tabela — ele foi removido, e valia outros
  /// 64 px. Se algum dia voltar, esta conta volta com ele.
  static const chrome = AppTheme.tableRowHeight + 76;

  /// O teto existe só para não pedir mil linhas numa tela absurda; quem
  /// decide de fato é o espaço. Já foi 10, e num monitor de balcão isso
  /// deixava um vão sem nada abaixo da paginação.
  static const maxRows = 60;

  static int rowsThatFit(double available) =>
      ((available - chrome) / AppTheme.tableRowHeight).floor().clamp(
        1,
        maxRows,
      );
}
