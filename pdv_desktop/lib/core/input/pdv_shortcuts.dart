import 'package:flutter/services.dart';

import 'pdv_screen.dart';

/// Um atalho de teclado do PDV.
///
/// O registro é a fonte única: a tecla que o roteador escuta e a linha que a
/// página de ajuda mostra saem do MESMO objeto. Enquanto as duas coisas
/// viviam separadas, trocar uma tecla exigia lembrar de editar a documentação
/// — e ninguém lembra. Aqui, mudar a tecla muda a ajuda no mesmo commit.
class PdvShortcut {
  const PdvShortcut({
    required this.id,
    required this.label,
    required this.description,
    required this.trigger,
    this.screens = const {},
    this.requiresOrder = false,
    this.guardsRepeat = false,
    this.documentedOnly = false,
    this.insideTextField = false,
    this.group = 'Geral',
  });

  /// Identificador estável usado pelo roteador para despachar a ação.
  final String id;

  /// Nome curto, como aparece na ajuda.
  final String label;

  /// O que a tecla faz, e quando não faz.
  final String description;

  final ShortcutTrigger trigger;

  /// Telas em que o atalho vale. Vazio = global.
  final Set<PdvScreen> screens;

  /// Exige um pedido aberto. Sem ele o atalho fica desativado (e a ajuda diz
  /// isso), em vez de disparar uma ação sem alvo.
  final bool requiresOrder;

  /// A ação apaga, cobra ou imprime: nunca dispara duas vezes por repetição
  /// automática de tecla.
  ///
  /// É o próprio registro que decide isso — uma segunda lista dentro do
  /// roteador se desencontraria dele no primeiro atalho novo, e o sintoma
  /// seria uma tecla presa virando duas cobranças.
  final bool guardsRepeat;

  /// A tecla é tratada FORA do roteador do PDV.
  ///
  /// F11 é assim: quem escuta é a janela do aplicativo (`starchef_app.dart`),
  /// porque tela cheia não é assunto do caixa. Ela aparece na ajuda e na
  /// faixa de atalhos — o operador precisa saber que existe —, mas `resolve`
  /// a ignora de propósito: se o roteador a consumisse, o handler da janela
  /// nunca a receberia e a tecla pararia de funcionar.
  final bool documentedOnly;

  /// Vale mesmo com o cursor num campo — quando a tecla não tem uso nele.
  ///
  /// As setas da tela de pagamento: o campo do valor é de uma linha só, e é
  /// onde o caixa está. O roteador ainda deixa a tecla com o campo que a usa
  /// (a lista do cupom; ver `PdvInputContext.textFieldOwnsArrows`).
  final bool insideTextField;

  final String group;

  bool get isGlobal => screens.isEmpty;

  bool appliesTo(PdvScreen screen) => isGlobal || screens.contains(screen);

  /// Como a tecla é escrita na ajuda ("Ctrl + Shift + V").
  String get keysLabel => trigger.description;
}

/// A combinação de teclas de um atalho.
class ShortcutTrigger {
  const ShortcutTrigger(
    this.key, {
    this.control = false,
    this.shift = false,
    this.alt = false,
    this.label = '',
  });

  final LogicalKeyboardKey key;
  final bool control;
  final bool shift;
  final bool alt;

  /// Rótulo explícito, quando o nome derivado da tecla ficaria ruim.
  final String label;

  bool matches(KeyEvent event, HardwareKeyboard keyboard) {
    if (event.logicalKey != key) return false;
    if (keyboard.isControlPressed != control) return false;
    if (keyboard.isAltPressed != alt) return false;
    // Shift é comparado só quando o atalho exige: teclados diferentes usam
    // shift para produzir o mesmo caractere (`+`, por exemplo).
    if (shift && !keyboard.isShiftPressed) return false;
    return true;
  }

  String get _keyName {
    if (label.isNotEmpty) return label;
    final debug = key.keyLabel;
    return debug.isEmpty ? key.debugName ?? '?' : debug;
  }

  String get description => [
    if (control) 'Ctrl',
    if (shift) 'Shift',
    if (alt) 'Alt',
    _keyName,
  ].join(' + ');
}

/// Ações que o PDV expõe ao teclado.
///
/// Identificadores em vez de callbacks: o registro é `const` e não depende de
/// nenhuma tela estar montada, o que é o que permite a página de ajuda listar
/// tudo (inclusive o que está desativado agora) sem duplicar a lista.
abstract final class PdvAction {
  static const help = 'help';
  static const focusSearch = 'focus-search';
  static const refresh = 'refresh';
  static const cashCenter = 'cash-center';
  static const pickCommand = 'pick-command';
  static const readClipboard = 'read-clipboard';
  static const sendToKitchen = 'send-to-kitchen';
  static const payment = 'payment';
  static const printReceipt = 'print-receipt';
  static const back = 'back';
  static const increaseQuantity = 'increase-quantity';
  static const decreaseQuantity = 'decrease-quantity';
  static const removeItem = 'remove-item';
  static const newSale = 'new-sale';
  static const moveSelectionUp = 'move-selection-up';
  static const moveSelectionDown = 'move-selection-down';
  static const confirm = 'confirm';
  static const nextPaymentMethod = 'next-payment-method';
  static const previousPaymentMethod = 'previous-payment-method';
  static const notifications = 'notifications';
  static const gridLeft = 'grid-left';
  static const gridRight = 'grid-right';
  static const gridUp = 'grid-up';
  static const gridDown = 'grid-down';
  static const addHighlighted = 'add-highlighted';
  static const categoryNext = 'category-next';
  static const categoryPrevious = 'category-previous';
  static const paymentKeyHelp = 'payment-key-help';

  /// `payment-key:7`, `payment-key:back`: a tecla do teclado da tela.
  static const paymentKeyPrefix = 'payment-key:';

  // As páginas do menu lateral, uma tecla de função cada (F1 a F8).
  static const goSale = 'go-sale';
  static const goOrders = 'go-orders';
  static const goTables = 'go-tables';
  static const goCommands = 'go-commands';
  static const goCustomers = 'go-customers';
  static const goCash = 'go-cash';
  static const goScale = 'go-scale';
  static const goSettings = 'go-settings';

  /// Tratada pela janela do aplicativo; ver [PdvShortcut.documentedOnly].
  static const toggleFullScreen = 'toggle-full-screen';
}

/// O catálogo de atalhos do PDV.
///
/// O MAPA, para quem procura uma tecla:
/// - F1 a F8 levam às páginas, na ordem do menu lateral — e cada página tem a
///   SUA tecla: com "Pedidos" escondido pela permissão, F2 não faz nada, e o
///   F3 continua sendo Mesas. Uma tecla que mudasse de página conforme o
///   usuário seria decorada errado no primeiro dia.
/// - F9 notificações, F10 central do caixa, F11 tela cheia, F12 ajuda.
/// - Na venda: Enter vai ao pagamento; Ctrl + E envia à cozinha; Ctrl + P
///   imprime. Tab leva à busca da página.
/// - Ctrl é para gesto (nova venda, buscar, atualizar, informar comanda);
///   Ctrl + Shift, para o que não pode sair por engano (ler a área de
///   transferência).
abstract final class PdvShortcuts {
  static const all = <PdvShortcut>[
    // ── Páginas ──────────────────────────────────────────────────────────
    PdvShortcut(
      id: PdvAction.goSale,
      label: 'Venda',
      description:
          'Abre a venda. Com um pedido na tela, volta para ele; sem pedido, '
          'começa no início.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f1, label: 'F1'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goOrders,
      label: 'Pedidos',
      description: 'Abre a lista de pedidos do restaurante.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f2, label: 'F2'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goTables,
      label: 'Mesas',
      description:
          'Abre as mesas. Com itens no carrinho, pede confirmação antes de '
          'sair da venda.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f3, label: 'F3'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goCommands,
      label: 'Comandas',
      description: 'Abre a página das comandas: consulta e conferência.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f4, label: 'F4'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goCustomers,
      label: 'Clientes',
      description: 'Abre a lista de clientes.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f5, label: 'F5'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goCash,
      label: 'Caixa',
      description: 'Abre o caixa e o financeiro do turno.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f6, label: 'F6'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goScale,
      label: 'Balança',
      description: 'Abre a balança rápida.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f7, label: 'F7'),
      group: 'Páginas',
    ),
    PdvShortcut(
      id: PdvAction.goSettings,
      label: 'Mais (configurações)',
      description: 'Abre as configurações e os equipamentos do terminal.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f8, label: 'F8'),
      group: 'Páginas',
    ),
    // ── Sistema ──────────────────────────────────────────────────────────
    PdvShortcut(
      id: PdvAction.notifications,
      label: 'Notificações',
      description: 'Abre e fecha a lista de notificações (o sino do topo).',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f9, label: 'F9'),
      group: 'Sistema',
    ),
    PdvShortcut(
      id: PdvAction.cashCenter,
      label: 'Central do caixa',
      description: 'Abre sangria, suprimento, abertura e fechamento do caixa.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f10, label: 'F10'),
      group: 'Sistema',
    ),
    PdvShortcut(
      id: PdvAction.toggleFullScreen,
      label: 'Tela cheia',
      description:
          'Alterna entre janela e tela cheia. Quem trata esta tecla é a '
          'janela do aplicativo, não o PDV — por isso ela funciona em '
          'qualquer tela, inclusive com um campo de texto focado.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f11, label: 'F11'),
      documentedOnly: true,
      group: 'Sistema',
    ),
    PdvShortcut(
      id: PdvAction.help,
      label: 'Ajuda e atalhos',
      description:
          'Abre esta página, com os atalhos da tela atual e do sistema.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f12, label: 'F12'),
      group: 'Sistema',
    ),
    PdvShortcut(
      id: PdvAction.back,
      label: 'Voltar / fechar',
      description:
          'Fecha o modal aberto. Sem modal, volta uma etapa do atendimento.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.escape, label: 'Esc'),
      group: 'Sistema',
    ),
    // O Tab não navega mais entre botões (`teclado_sem_navegacao.dart`):
    // ele leva à busca da página, até de dentro de outro campo.
    PdvShortcut(
      id: PdvAction.focusSearch,
      label: 'Focar a busca',
      description:
          'Leva o cursor para a busca da página; já nela, tira o cursor.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.tab, label: 'Tab'),
      insideTextField: true,
      group: 'Sistema',
    ),
    // A "/" NÃO é atalho: o leitor de comanda digita o QR como teclas, e um
    // QR com endereço ("https://.../c/12") trazia a barra no meio — o cursor
    // ia para a busca e o resto do código caía nela, travando a leitura.
    PdvShortcut(
      id: PdvAction.focusSearch,
      label: 'Focar a busca (alternativo)',
      description: 'Mesma ação do Tab.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyF,
        control: true,
        label: 'F',
      ),
      group: 'Sistema',
    ),
    PdvShortcut(
      id: PdvAction.refresh,
      label: 'Atualizar e sincronizar',
      description:
          'Recarrega os dados da tela e tenta esvaziar a fila de envio.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyR,
        control: true,
        label: 'R',
      ),
      group: 'Sistema',
    ),
    // ── Venda ────────────────────────────────────────────────────────────
    PdvShortcut(
      id: PdvAction.payment,
      label: 'Ir para pagamento',
      description:
          'Abre o fechamento do pedido. Com o cursor na busca, o Enter só '
          'conclui a busca. Quem adiciona produto é o Espaço.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.enter, label: 'Enter'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.payment,
      label: 'Ir para pagamento (numérico)',
      description: 'Mesma ação, no Enter do teclado numérico.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.numpadEnter,
        label: 'Enter (num)',
      ),
      screens: {PdvScreen.order},
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.sendToKitchen,
      label: 'Enviar à cozinha',
      description: 'Manda os itens pendentes do pedido atual para produção.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyE,
        control: true,
        label: 'E',
      ),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.printReceipt,
      label: 'Imprimir recibo',
      description: 'Imprime o recibo do pedido atual.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyP,
        control: true,
        label: 'P',
      ),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.newSale,
      label: 'Nova venda',
      description:
          'Começa um atendimento novo. Com itens não enviados, pede '
          'confirmação antes.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyN,
        control: true,
        label: 'N',
      ),
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.pickCommand,
      label: 'Informar comanda',
      description:
          'Abre a seleção de comanda para digitar o número à mão. Com o '
          'carrinho montado, anexa o cartão a ele.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyI,
        control: true,
        label: 'I',
      ),
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.readClipboard,
      label: 'Ler área de transferência',
      description:
          'Interpreta o texto copiado como se tivesse vindo do leitor. Só '
          'acontece quando você pede — nada é lido em segundo plano. Ctrl + V '
          'continua colando normalmente num campo.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyV,
        control: true,
        shift: true,
        label: 'V',
      ),
      group: 'Leitura de código',
    ),
    PdvShortcut(
      id: PdvAction.confirm,
      label: 'Confirmar a ação principal',
      description:
          'Confirma o que a tela está oferecendo: abrir a comanda filtrada, '
          'registrar o recebimento. Dentro de um campo, o Enter continua '
          'sendo dele. Nos diálogos de configuração do produto e de pesagem, '
          'o Enter é o próprio "Adicionar" — só quando a escolha obrigatória '
          'já foi feita.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.enter, label: 'Enter'),
      screens: {PdvScreen.context, PdvScreen.payment},
      // A tecla mais fácil de segurar sem perceber — e no pagamento ela
      // registra recebimento.
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.moveSelectionDown,
      label: 'Próximo item',
      description: 'Move o cursor para o item seguinte do pedido.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.arrowDown,
        shift: true,
        label: 'Seta ↓',
      ),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.moveSelectionUp,
      label: 'Item anterior',
      description: 'Move o cursor para o item anterior do pedido.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.arrowUp,
        shift: true,
        label: 'Seta ↑',
      ),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    // As setas SEM Shift andam pela grade de produtos (Shift + ↑ ↓ é o
    // carrinho, acima — e por isso vem antes: `matches` aceita o Shift a mais).
    // Valem com o cursor na busca, que é onde ele fica.
    PdvShortcut(
      id: PdvAction.gridDown,
      label: 'Produto abaixo',
      description: 'Destaca o produto da linha de baixo na grade.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowDown, label: 'Seta ↓'),
      screens: {PdvScreen.order},
      insideTextField: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.gridUp,
      label: 'Produto acima',
      description: 'Destaca o produto da linha de cima na grade.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowUp, label: 'Seta ↑'),
      screens: {PdvScreen.order},
      insideTextField: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.gridRight,
      label: 'Próximo produto',
      description: 'Destaca o produto seguinte na grade.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowRight, label: 'Seta →'),
      screens: {PdvScreen.order},
      insideTextField: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.gridLeft,
      label: 'Produto anterior',
      description: 'Destaca o produto anterior na grade.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowLeft, label: 'Seta ←'),
      screens: {PdvScreen.order},
      insideTextField: true,
      group: 'Venda',
    ),
    // Ctrl e Shift TOCADOS SOZINHOS: quem detecta é o roteador
    // (`toque_de_modificador.dart`), porque o toque só existe quando a tecla
    // SOLTA sem outra no meio — Ctrl + E e Shift + ↓ não trocam categoria.
    PdvShortcut(
      id: PdvAction.categoryNext,
      label: 'Próxima categoria',
      description: 'Ctrl apertado e solto sozinho: a categoria seguinte.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.controlLeft, label: 'Ctrl'),
      screens: {PdvScreen.order},
      documentedOnly: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.categoryPrevious,
      label: 'Categoria anterior',
      description: 'Shift apertado e solto sozinho: a categoria anterior.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.shiftLeft, label: 'Shift'),
      screens: {PdvScreen.order},
      documentedOnly: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.addHighlighted,
      label: 'Adicionar o produto destacado',
      description:
          'Adiciona ao carrinho o produto destacado pelas setas (o primeiro da '
          'lista, sem seta). Com o cursor na busca, o Espaço é do texto; o '
          'Enter conclui a busca.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.space, label: 'Espaço'),
      screens: {PdvScreen.order},
      guardsRepeat: true,
      group: 'Venda',
    ),
    PdvShortcut(
      id: PdvAction.increaseQuantity,
      label: 'Aumentar quantidade',
      description: 'Soma 1 ao item selecionado do pedido.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.add, label: '+'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.increaseQuantity,
      label: 'Aumentar quantidade (numérico)',
      description: 'Mesma ação do +, na tecla do teclado numérico.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.numpadAdd, label: '+ (num)'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.decreaseQuantity,
      label: 'Diminuir quantidade',
      description: 'Subtrai 1 do item selecionado do pedido.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.minus, label: '-'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.decreaseQuantity,
      label: 'Diminuir quantidade (numérico)',
      description:
          'Mesma ação do -. Chegando a zero, vira o cancelamento do item, '
          'que pede motivo.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.numpadSubtract,
        label: '- (num)',
      ),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.removeItem,
      label: 'Remover item',
      description:
          'Cancela o item selecionado, sempre pelo mesmo caminho do botão: '
          'com motivo, e — para item já enviado à cozinha — com permissão e '
          'cupom de cancelamento no setor.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.delete, label: 'Delete'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Itens do pedido',
    ),
    // A linha da ajuda; quem responde às teclas é [digitosDoPagamento].
    PdvShortcut(
      id: PdvAction.paymentKeyHelp,
      label: 'Digitar o valor',
      description:
          'Os números (de cima e do numérico) digitam o valor do pagamento, '
          'como o teclado da tela. Backspace apaga o último dígito e Delete '
          'zera. Com o cursor no cupom ou no CPF, o número é do campo.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.digit0, label: '0–9'),
      screens: {PdvScreen.payment},
      documentedOnly: true,
      group: 'Pagamento',
    ),
    PdvShortcut(
      id: PdvAction.nextPaymentMethod,
      label: 'Próxima forma de pagamento',
      description:
          'Seleciona a forma de pagamento seguinte da lista, mesmo com o '
          'cursor no valor. No campo do cupom a seta anda na lista de cupons.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowDown, label: 'Seta ↓'),
      screens: {PdvScreen.payment},
      insideTextField: true,
      group: 'Pagamento',
    ),
    PdvShortcut(
      id: PdvAction.previousPaymentMethod,
      label: 'Forma de pagamento anterior',
      description:
          'Seleciona a forma de pagamento anterior da lista, mesmo com o '
          'cursor no valor.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowUp, label: 'Seta ↑'),
      screens: {PdvScreen.payment},
      insideTextField: true,
      group: 'Pagamento',
    ),
  ];

  /// Os atalhos válidos na tela informada, na ordem do catálogo.
  static List<PdvShortcut> forScreen(PdvScreen screen) =>
      all.where((shortcut) => shortcut.appliesTo(screen)).toList();

  /// A tecla da ação [id] como a tela a escreve ("Enter", "Ctrl + E").
  ///
  /// As etiquetas dos botões ("Pagamento  Enter") saem daqui, e não de texto
  /// solto: foi texto solto que deixou "F4" escrito no botão depois de a
  /// tecla mudar.
  static String teclaDe(String id, {PdvScreen? screen}) {
    for (final shortcut in all) {
      if (shortcut.id != id) continue;
      if (screen != null && !shortcut.appliesTo(screen)) continue;
      return shortcut.keysLabel;
    }
    return '';
  }

  /// Grupos na ordem em que a ajuda os apresenta.
  static List<String> get groups {
    final seen = <String>[];
    for (final shortcut in all) {
      if (!seen.contains(shortcut.group)) seen.add(shortcut.group);
    }
    return seen;
  }

  /// Os números e o Backspace/Delete do pagamento: digitam o valor como o
  /// teclado da tela (`PaymentKeypad`). Fora da lista [all] porque são vinte
  /// teclas para UMA linha da ajuda.
  static final List<PdvShortcut> digitosDoPagamento = [
    for (var n = 0; n <= 9; n++) ...[
      _digito('$n', LogicalKeyboardKey(LogicalKeyboardKey.digit0.keyId + n)),
      _digito('$n', LogicalKeyboardKey(LogicalKeyboardKey.numpad0.keyId + n)),
    ],
    _digito('back', LogicalKeyboardKey.backspace),
    _digito('clear', LogicalKeyboardKey.delete),
  ];

  static PdvShortcut _digito(String tecla, LogicalKeyboardKey key) =>
      PdvShortcut(
        id: '${PdvAction.paymentKeyPrefix}$tecla',
        label: 'Digitar o valor',
        description: '',
        trigger: ShortcutTrigger(key),
        screens: const {PdvScreen.payment},
        group: 'Pagamento',
      );

  /// O atalho disparado por este evento, se houver.
  ///
  /// Percorre na ordem do catálogo e devolve o primeiro que casa — atalhos com
  /// modificador vêm antes do mesmo caractere sem modificador porque
  /// [ShortcutTrigger.matches] exige igualdade exata de Ctrl e Alt.
  static PdvShortcut? resolve(
    KeyEvent event, {
    required PdvScreen screen,
    HardwareKeyboard? keyboard,
  }) {
    final board = keyboard ?? HardwareKeyboard.instance;
    for (final shortcut in all) {
      // Documentado, mas de outra camada: deixar passar é o que mantém a
      // tecla funcionando onde ela realmente é tratada.
      if (shortcut.documentedOnly) continue;
      if (!shortcut.appliesTo(screen)) continue;
      if (shortcut.trigger.matches(event, board)) return shortcut;
    }
    if (screen == PdvScreen.payment) {
      for (final digito in digitosDoPagamento) {
        if (digito.trigger.matches(event, board)) return digito;
      }
    }
    return null;
  }
}
