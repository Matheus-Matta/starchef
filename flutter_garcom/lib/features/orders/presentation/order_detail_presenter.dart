import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/relay/pending_mutation.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/order_drafts.dart';
import '../data/orders_repository.dart';
import 'order_formatters.dart';

/// O estado de UM pedido aberto: o que já foi lançado, o que falta enviar, o
/// que o caixa recusou e o que já foi recebido.
///
/// Estava tudo dentro do `State` da tela — 400 linhas onde o listener da fila
/// offline, a soma dos recebimentos e a montagem do `ListView` dividiam o
/// mesmo arquivo. Aqui ficam as regras; a tela lê e desenha.
///
/// **Sem conexão com o Caixa Principal**, lançar item, cancelar item, enviar
/// para a cozinha e vincular mesa ficam salvos no aparelho (ver
/// [RelayGateway]) e aparecem com um selo "aguardando conexão" até o caixa
/// confirmar — nada aqui trava esperando rede.
class OrderDetailPresenter extends ChangeNotifier {
  OrderDetailPresenter({
    required this.repository,
    required String orderId,
    Map<String, dynamic>? initialOrder,
  }) : _orderId = orderId,
       _order = initialOrder;

  final OrdersRepository repository;

  RelayGateway get gateway => repository.gateway;
  OrderDrafts get drafts => repository.drafts;

  /// Id efetivamente usado para buscar/gravar este pedido. Começa igual ao
  /// recebido e é trocado, sozinho, pelo id real assim que uma criação offline
  /// (id `offline-...`) sincroniza — ver [_onGatewayChange].
  String _orderId;
  String get orderId => _orderId;

  Map<String, dynamic>? _order;
  Map<String, dynamic>? get order => _order;

  bool _loading = true;
  bool get loading => _loading;

  bool _working = false;
  bool get working => _working;

  String? _error;
  String? get error => _error;

  int _lastPendingCount = 0;

  /// De onde veio o pedido na tela: do Caixa Principal ou da cópia local.
  ReadOrigin _origin = const ReadOrigin.live();
  ReadOrigin get origin => _origin;

  /// Recebimentos já registrados neste pedido, vistos pelo Caixa Principal.
  List<Map<String, dynamic>> _payments = const [];

  List<Map<String, dynamic>> _paymentMethods = const [];
  List<Map<String, dynamic>> get paymentMethods => _paymentMethods;

  bool _cashRegisterOpen = false;
  bool get cashRegisterOpen => _cashRegisterOpen;

  String? _cashRegisterId;
  bool _disposed = false;

  void start() {
    gateway.addListener(_onGatewayChange);
    unawaited(load());
  }

  @override
  void dispose() {
    gateway.removeListener(_onGatewayChange);
    _disposed = true;
    super.dispose();
  }

  // ---------------------------------------------------------------- leitura

  Future<void> load() async {
    // Um pedido criado offline não existe no servidor até a criação
    // sincronizar — não há nada para buscar ainda, então mostra o que já está
    // em memória (o otimista, mais qualquer item lançado offline depois) em
    // vez de tentar um GET que só devolveria 404.
    if (_isOffline) {
      _loading = false;
      _lastPendingCount = gateway.pendingFor(_orderId).length;
      _notify();
      return;
    }
    _loading = true;
    _error = null;
    _notify();
    try {
      _order = await repository.order(_orderId);
      _origin = repository.lastReadOrigin;
      _lastPendingCount = gateway.pendingFor(_orderId).length;
      // Fora do caminho crítico: o pedido já está na tela e o garçom pode
      // lançar itens enquanto o contexto de recebimento carrega.
      unawaited(_loadPayments());
    } catch (error) {
      _error = describeFailure(error);
    } finally {
      _loading = false;
      _notify();
    }
  }

  bool get _isOffline => _orderId.startsWith('offline-');

  /// Reage à fila offline: uma pendência a menos deste pedido é o sinal de que
  /// o Caixa Principal aceitou alguma coisa — busca a versão real para
  /// substituir a linha otimista pela definitiva. Qualquer outra mudança (uma
  /// pendência a mais, ou de outro pedido) só redesenha o selo.
  void _onGatewayChange() {
    if (_disposed) return;
    if (_isOffline) {
      final resolved = gateway.resolvedOrderId(_orderId);
      if (resolved != null) {
        // Os itens ainda não enviados acompanham o pedido: sem isto eles
        // ficariam apontando para um id que deixou de existir.
        unawaited(drafts.reassign(_orderId, resolved));
        _orderId = resolved;
        _notify();
        unawaited(load());
        return;
      }
    }
    final current = gateway.pendingFor(_orderId).length;
    final flushed = current < _lastPendingCount;
    _lastPendingCount = current;
    if (flushed) {
      unawaited(load());
    } else {
      _notify();
    }
  }

  // ------------------------------------------------------------- derivados

  List<PendingMutation> get _queued => gateway.pendingFor(_orderId);

  /// Itens lançados sem conexão: ainda não existem no pedido de verdade.
  List<PendingMutation> get pendingAdds =>
      _queued.where((m) => m.kind == 'add_item').toList();

  /// Itens cujo cancelamento o caixa ainda não confirmou.
  Set<String> get voidingItemIds => _queued
      .where((m) => m.kind == 'void_item')
      .map((m) => m.itemId)
      .whereType<String>()
      .toSet();

  /// O envio à cozinha já está na fila, esperando o caixa responder.
  bool get sendQueued => _queued.any((m) => m.kind == 'send_to_kitchen');

  List<DraftItem> get draftItems => drafts.forOrder(_orderId);

  List<FailedMutation> get failures => gateway.failedFor(_orderId);

  /// Itens já lançados que foram para a produção, nesta ou em outra rodada.
  List<Map<String, dynamic>> get sentItems =>
      _items.where(_alreadySent).toList();

  /// Itens já lançados que ainda esperam o envio à cozinha.
  List<Map<String, dynamic>> get unsentItems =>
      _items.where((item) => !_alreadySent(item)).toList();

  List<Map<String, dynamic>> get _items =>
      _order == null ? const [] : orderItems(_order!);

  /// Tudo que ainda vai para a cozinha: o que o servidor já tem como pendente,
  /// o que está na fila e o que o garçom acabou de escolher.
  int get pendingToSend =>
      (_order == null ? 0 : pendingItems(_order!)) +
      pendingAdds.length +
      draftItems.length;

  bool get isEmpty =>
      _items.isEmpty &&
      pendingAdds.isEmpty &&
      draftItems.isEmpty &&
      failures.isEmpty;

  static bool _alreadySent(Map<String, dynamic> item) =>
      '${item['status'] ?? ''}' != 'pending';

  /// Total já recebido, somando o que o principal confirmou.
  double get paid => _payments.fold<double>(
    0,
    (total, item) => total + amount(item['amount']),
  );

  double get remaining {
    final missing = amount(_order?['total']) - paid;
    return missing < 0 ? 0 : missing;
  }

  bool get awaitingPayment => '${_order?['status']}' == 'awaiting_payment';

  // -------------------------------------------------------------- escritas

  /// Executa uma gravação e recarrega o pedido — a versão do Caixa Principal é
  /// sempre quem manda, mesmo depois de um envio bem-sucedido.
  ///
  /// Devolve o recado a mostrar ao garçom, ou `null` quando outra operação já
  /// estava em andamento. Uma falha de CONEXÃO não é erro: [MutationQueued] é
  /// a operação salva com sucesso no aparelho, e o selo de pendência aparece
  /// sozinho.
  Future<String?> run(Future<void> Function() action, String success) async {
    if (_working) return null;
    _working = true;
    _notify();
    try {
      await action();
      await load();
      return success;
    } on MutationQueued catch (queued) {
      return describeFailure(queued);
    } catch (error) {
      return describeFailure(error);
    } finally {
      _working = false;
      _notify();
    }
  }

  /// Acrescenta o item à lista de "a enviar" — sem tocar na rede.
  ///
  /// Antes cada toque virava uma ida ao Caixa Principal que podia falhar
  /// sozinha, e o garçom só descobria muito depois, numa pendência que já não
  /// dizia de que item se tratava. Agora os itens se acumulam e vão juntos,
  /// num envio só, quando ele confirma.
  Future<void> addDraft(ProductChoice choice) async {
    await drafts.add(
      DraftItem(
        id: OrderDrafts.newId(),
        orderId: _orderId,
        productId: choice.productId,
        productName: choice.productName,
        quantity: choice.quantity,
        variationId: choice.variationId,
        variationName: choice.variationName,
        addonIds: choice.addonIds,
        note: choice.note,
      ),
    );
    _notify();
  }

  Future<void> removeDraft(DraftItem item) async {
    await drafts.remove(item.id);
    _notify();
  }

  /// Manda tudo o que está esperando e pede a impressão da comanda.
  ///
  /// Os itens sobem um a um (é assim que o Caixa Principal e o backend os
  /// aceitam) e só então vem o envio à produção, que é o que imprime. Um item
  /// recusado não impede os outros: ele fica na lista de erros, com o motivo,
  /// para o garçom reenviar ou remover.
  Future<String?> sendToKitchen() async {
    if (_working) return null;
    final pending = draftItems;
    _working = true;
    _notify();
    var sent = 0;
    var queued = 0;
    try {
      for (final draft in pending) {
        try {
          await repository.addItem(
            orderId: _orderId,
            productId: draft.productId,
            productName: draft.productName,
            quantity: draft.quantity,
            variationId: draft.variationId,
            addonIds: draft.addonIds,
            customerNote: draft.note,
          );
          sent++;
        } on MutationQueued {
          // Salvo no aparelho: sai quando o Caixa Principal responder.
          queued++;
        }
        await drafts.remove(draft.id);
      }
      // A comanda só é impressa uma vez, no fim: uma impressão por item
      // encheria a cozinha de papel para a mesma rodada.
      try {
        await repository.sendToKitchen(_orderId);
      } on MutationQueued {
        queued++;
      }
      await load();
      return queued == 0
          ? 'Pedido enviado para produção e impressão.'
          : 'Sem conexão: $sent de ${pending.length} itens foram entregues. '
                'O resto sai quando o Caixa Principal responder.';
    } catch (error) {
      return describeFailure(error);
    } finally {
      _working = false;
      _notify();
    }
  }

  Future<void> retryFailed(FailedMutation failure) async {
    await gateway.retryFailed(failure.mutation.operationId);
    _notify();
  }

  Future<void> discardFailed(FailedMutation failure) async {
    await gateway.discardFailed(failure.mutation.operationId);
    _notify();
  }

  Future<String?> voidItem(Map<String, dynamic> item, String reason) => run(
    () => repository.voidItem(
      orderId: _orderId,
      itemId: '${item['id']}',
      itemLabel: '${item['product_name'] ?? 'item'}',
      reason: reason,
    ),
    'Item cancelado.',
  );

  /// [success] vem de fora porque só quem perguntou sabe se a comanda estava
  /// sendo vinculada pela primeira vez ou transferida de mesa.
  Future<String?> linkTable(
    String commandId,
    Map<String, dynamic> table, {
    required String success,
  }) => run(
    () => repository.linkTable(
      commandId: commandId,
      tableId: '${table['id']}',
      tableLabel: '${table['number']}',
    ),
    success,
  );

  Future<String?> unlinkTable(String commandId) => run(
    () => repository.unlinkTable(commandId: commandId),
    'Comanda desvinculada da mesa.',
  );

  Future<String?> pay({
    required String methodId,
    required String methodName,
    required String value,
    required String reference,
  }) => run(
    () => repository.pay(
      orderId: _orderId,
      paymentMethodId: methodId,
      amount: value,
      cashRegisterId: _cashRegisterId,
      reference: reference,
    ),
    'Recebimento registrado em $methodName.',
  );

  // ------------------------------------------------------------ recebimento

  /// Lê o que o recebimento precisa saber, sem prender a tela.
  ///
  /// Só depois de a conta fechar: enquanto o pedido está aberto o garçom está
  /// lançando item, e o que já foi recebido não muda nada na tela. Uma falha
  /// aqui não impede o lançamento — só esconde o botão de receber.
  Future<void> _loadPayments() async {
    if (!awaitingPayment) return;
    try {
      _payments = await repository.payments(_orderId);
      _notify();
    } catch (_) {
      // O caixa não respondeu: o pedido continua utilizável para lançamento.
    }
  }

  /// Consulta o que só o Caixa Principal sabe: quais formas de pagamento
  /// existem e qual sessão de caixa está aberta.
  ///
  /// Chamada no momento em que o operador vai receber, não a cada abertura de
  /// tela: eram três consultas ao caixa por pedido — caro no Wi-Fi do salão, e
  /// inútil enquanto o garçom está só lançando itens.
  Future<bool> loadPaymentOptions() async {
    if (_paymentMethods.isNotEmpty) return true;
    try {
      final methods = await repository.paymentMethods();
      final session = await repository.currentCashRegister();
      _paymentMethods = methods;
      _cashRegisterId = session == null ? null : '${session['id']}';
      _cashRegisterOpen = _cashRegisterId != null;
    } catch (_) {
      _paymentMethods = const [];
      _cashRegisterOpen = false;
    }
    _notify();
    return _paymentMethods.isNotEmpty;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }
}
