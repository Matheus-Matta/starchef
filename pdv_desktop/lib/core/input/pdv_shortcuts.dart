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
  static const home = 'home';
  static const orders = 'orders';
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

  /// Tratada pela janela do aplicativo; ver [PdvShortcut.documentedOnly].
  static const toggleFullScreen = 'toggle-full-screen';
}

/// O catálogo de atalhos do PDV.
abstract final class PdvShortcuts {
  static const all = <PdvShortcut>[
    PdvShortcut(
      id: PdvAction.toggleFullScreen,
      label: 'Tela cheia',
      description:
          'Alterna entre janela e tela cheia. Quem trata esta tecla é a '
          'janela do aplicativo, não o PDV — por isso ela funciona em '
          'qualquer tela, inclusive com um campo de texto focado.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f11, label: 'F11'),
      documentedOnly: true,
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.help,
      label: 'Ajuda e atalhos',
      description: 'Abre esta página, com os atalhos da tela atual e do sistema.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f1, label: 'F1'),
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.focusSearch,
      label: 'Focar a busca',
      description: 'Leva o cursor para o campo de busca da tela atual.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f2, label: 'F2'),
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.home,
      label: 'Início / nova venda',
      description:
          'Volta ao início. Com itens ainda não enviados à cozinha, pede '
          'confirmação antes de sair.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f3, label: 'F3'),
      guardsRepeat: true,
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.orders,
      label: 'Lista de pedidos',
      description: 'Abre a lista de pedidos do restaurante.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f4, label: 'F4'),
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.refresh,
      label: 'Atualizar e sincronizar',
      description: 'Recarrega os dados da tela e tenta esvaziar a fila de envio.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f5, label: 'F5'),
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.cashCenter,
      label: 'Central do caixa',
      description: 'Abre sangria, suprimento, abertura e fechamento do caixa.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f6, label: 'F6'),
      group: 'Caixa',
    ),
    PdvShortcut(
      id: PdvAction.pickCommand,
      label: 'Informar comanda',
      description: 'Abre a seleção de comanda para digitar o número à mão.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f7, label: 'F7'),
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.readClipboard,
      label: 'Ler área de transferência',
      description:
          'Interpreta o texto copiado como se tivesse vindo do leitor. Só '
          'acontece quando você pede — nada é lido em segundo plano.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f8, label: 'F8'),
      group: 'Leitura de código',
    ),
    PdvShortcut(
      id: PdvAction.readClipboard,
      label: 'Ler área de transferência (alternativo)',
      description:
          'Mesma ação do F8. Ctrl + V continua colando normalmente quando há '
          'um campo focado.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyV,
        control: true,
        shift: true,
        label: 'V',
      ),
      group: 'Leitura de código',
    ),
    PdvShortcut(
      id: PdvAction.sendToKitchen,
      label: 'Enviar à cozinha',
      description: 'Manda os itens pendentes do pedido atual para produção.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f9, label: 'F9'),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.payment,
      label: 'Ir para pagamento',
      description: 'Abre o fechamento do pedido atual.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f10, label: 'F10'),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.printReceipt,
      label: 'Imprimir recibo',
      description: 'Imprime o recibo do pedido atual.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.f12, label: 'F12'),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.back,
      label: 'Voltar / fechar',
      description:
          'Fecha o modal aberto. Sem modal, volta uma etapa do atendimento.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.escape, label: 'Esc'),
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.focusSearch,
      label: 'Focar a busca (alternativo)',
      description: 'Mesma ação do F2.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyF,
        control: true,
        label: 'F',
      ),
      group: 'Navegação',
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
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.printReceipt,
      label: 'Imprimir (alternativo)',
      description: 'Mesma ação do F12.',
      trigger: ShortcutTrigger(
        LogicalKeyboardKey.keyP,
        control: true,
        label: 'P',
      ),
      requiresOrder: true,
      guardsRepeat: true,
      group: 'Atendimento',
    ),
    PdvShortcut(
      id: PdvAction.confirm,
      label: 'Confirmar a ação principal',
      description:
          'Confirma o que a tela está oferecendo: fechar o pedido, abrir a '
          'comanda filtrada, registrar o recebimento. Dentro de um campo, o '
          'Enter continua sendo dele. Nos diálogos de configuração do produto '
          'e de pesagem, o Enter é o próprio "Adicionar" — só quando a escolha '
          'obrigatória já foi feita.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.enter, label: 'Enter'),
      screens: {PdvScreen.order, PdvScreen.context, PdvScreen.payment},
      // A tecla mais fácil de segurar sem perceber — e aqui ela fecha pedido
      // e registra recebimento.
      guardsRepeat: true,
      group: 'Navegação',
    ),
    PdvShortcut(
      id: PdvAction.moveSelectionDown,
      label: 'Próximo item',
      description: 'Move o cursor para o item seguinte do pedido.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowDown, label: 'Seta ↓'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
    ),
    PdvShortcut(
      id: PdvAction.moveSelectionUp,
      label: 'Item anterior',
      description: 'Move o cursor para o item anterior do pedido.',
      trigger: ShortcutTrigger(LogicalKeyboardKey.arrowUp, label: 'Seta ↑'),
      screens: {PdvScreen.order},
      requiresOrder: true,
      group: 'Itens do pedido',
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
  ];

  /// Os atalhos válidos na tela informada, na ordem do catálogo.
  static List<PdvShortcut> forScreen(PdvScreen screen) =>
      all.where((shortcut) => shortcut.appliesTo(screen)).toList();

  /// Grupos na ordem em que a ajuda os apresenta.
  static List<String> get groups {
    final seen = <String>[];
    for (final shortcut in all) {
      if (!seen.contains(shortcut.group)) seen.add(shortcut.group);
    }
    return seen;
  }

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
    return null;
  }
}
