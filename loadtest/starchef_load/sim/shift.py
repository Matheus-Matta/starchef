"""O turno: a rotina que um operador repete o dia inteiro.

E o mesmo roteiro do balcao — abre a comanda, lanca, manda pra cozinha, fecha,
recebe — com a diferenca de que aqui ele acontece as centenas, com o terminal
caindo no meio e voltando depois.

Uma regra atravessa tudo: **venda que comecou na fila continua na fila**. O ID
do pedido so existe no terminal ate a criacao subir; mandar o item por HTTP
citando esse ID temporario seria inventar um pedido que o servidor nao tem.
"""
from decimal import Decimal

from . import cash, sale
from .outbox import FAILED


def _referencia(operacao, corpo):
    if isinstance(corpo, dict) and corpo.get("id"):
        return str(corpo["id"]), True
    return operacao.local_id, False


def executar_venda(terminal, refs, rng, chaos_ratio):
    """Uma venda inteira. Devolve o registro dela (ou None se nem abriu)."""
    abrir = sale.abrir_pedido(terminal, refs, rng)
    corpo = terminal.execute(abrir)
    if corpo is None and abrir.status == FAILED:
        return None
    order_ref, confirmado = _referencia(abrir, corpo)
    # Criacao enfileirada (offline, principal fora ou falha temporaria): o resto
    # da venda vai para a mesma fila, na ordem, atras dela.
    na_fila = not confirmado

    operacoes_itens, total = sale.itens(terminal, refs, rng, order_ref, chaos_ratio)
    itens_aceitos = 0
    for operacao in operacoes_itens:
        resposta = terminal.execute(operacao, force_queue=na_fila)
        if operacao.case == "valido" and (resposta is not None or operacao.status != FAILED):
            itens_aceitos += 1

    if rng.random() < 0.7:
        terminal.execute(
            sale.enviar_cozinha(terminal, order_ref, rng, offline=na_fila or not terminal.online),
            force_queue=na_fila,
        )

    if total <= 0:
        total = cash.total_esperado(refs, max(itens_aceitos, 1))
    fechamento = sale.fechar(terminal, order_ref, total, rng, chaos_ratio)
    resposta_fechamento = terminal.execute(fechamento, force_queue=na_fila)
    total_autoritativo = total
    reconciliado = False
    if isinstance(resposta_fechamento, dict):
        reconciliado = bool(resposta_fechamento.get("total_reconciled"))
        try:
            total_autoritativo = Decimal(str(resposta_fechamento.get("total") or total))
        except (TypeError, ValueError):
            pass

    pagamento = sale.receber(terminal, refs, order_ref, total_autoritativo, rng, chaos_ratio)
    resposta_pagamento = None
    if pagamento is not None:
        resposta_pagamento = terminal.execute(pagamento, force_queue=na_fila)

    registro = {
        "order_ref": order_ref,
        "confirmado": confirmado,
        "abrir": abrir,
        "fechamento_reconciliado": reconciliado,
        "total": str(total_autoritativo),
        "pagamento": pagamento,
        "pagamento_ok": isinstance(resposta_pagamento, dict) and bool(resposta_pagamento.get("id")),
        "pagamento_valido": bool(pagamento and pagamento.case == "valido"),
    }
    terminal.sales.append(registro)
    return registro


def venda_balanca(terminal, refs, rng, chaos_ratio):
    """Balanca Rapida: online cria a leitura antes; offline manda o peso bruto."""
    if not refs.scale:
        return None
    if terminal.online and rng.random() < 0.7:
        leitura = cash.leitura_de_peso(refs, rng, chaos_ratio)
        if leitura is None:
            return None
        corpo = terminal.execute(leitura)
        reading_id = corpo.get("id") if isinstance(corpo, dict) else None
        if reading_id is None:
            # Sem leitura registrada, o caminho honesto e o mesmo do offline:
            # a pesagem existe, o `ScaleReading` do servidor nao.
            operacao = cash.checkout_balanca(refs, rng, peso_bruto=round(rng.uniform(0.1, 2.5), 3),
                                             chaos_ratio=chaos_ratio)
        else:
            operacao = cash.checkout_balanca(refs, rng, reading_id=str(reading_id), chaos_ratio=chaos_ratio)
    else:
        operacao = cash.checkout_balanca(refs, rng, peso_bruto=round(rng.uniform(0.1, 2.5), 3),
                                         chaos_ratio=chaos_ratio)
    if operacao is None:
        return None
    return terminal.execute(operacao)


def turno(terminal, refs, rng, config, *, com_caixa=True, vendas=None):
    """Abre o caixa, vende N vezes com quedas de rede no meio e fecha o caixa."""
    quantidade = vendas if vendas is not None else config.sales
    if com_caixa:
        abertura = cash.abrir_caixa(terminal, refs, rng)
        if abertura is not None:
            corpo = terminal.execute(abertura)
            if isinstance(corpo, dict) and corpo.get("id"):
                terminal.cash_register = str(corpo["id"])

    for indice in range(quantidade):
        # Queda de rede no meio do expediente: nao avisa, nao espera.
        if rng.random() < config.offline_ratio and terminal.online:
            terminal.go_offline(f"na venda {indice + 1}")
        elif not terminal.online and rng.random() < 0.4:
            terminal.reconnect()

        if rng.random() < 0.25 and refs.scale and terminal.online:
            venda_balanca(terminal, refs, rng, config.chaos_ratio)
        else:
            executar_venda(terminal, refs, rng, config.chaos_ratio)

        if terminal.cash_register and rng.random() < 0.15:
            movimento = cash.movimento(terminal, rng, config.chaos_ratio)
            if movimento is not None:
                terminal.execute(movimento)

    terminal.reconnect()
    if com_caixa and terminal.cash_register and rng.random() < 0.6:
        fechamento = cash.fechar_caixa(terminal, rng, config.chaos_ratio)
        if fechamento is not None:
            terminal.execute(fechamento)
    return terminal.summary()
