/// Blocos de layout do app do garçom — a mesma biblioteca que o PDV desktop
/// usa em `flutter/lib/core/widgets/shadcn_layout.dart`, com os mesmos nomes.
///
/// Antes cada tela montava à mão o seu cartão, o seu selo, o seu aviso e o seu
/// "nada aqui": eram sete `Container` com `withValues(alpha: .12)` espalhados
/// em cinco arquivos, cada um com um respiro e uma borda ligeiramente
/// diferentes. Aqui existe um de cada, e o alinhamento passa a ser
/// consequência de usar o mesmo bloco — não de lembrar do mesmo número.
///
/// Este arquivo é só a porta de entrada: quem importa `shadcn_layout.dart`
/// recebe a biblioteca inteira e não precisa saber em qual pedaço cada bloco
/// mora.
library;

export 'app_feedback.dart';
export 'app_form.dart';
export 'app_page.dart';
export 'app_surfaces.dart';
