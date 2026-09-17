"""Comprovantes do caixa em texto: abertura, sangria, suprimento e fechamento.

Quem monta o papel e o SERVIDOR, nao o terminal. O PDV escolhe a impressora e
poe no papel — e ele quem enxerga o equipamento do balcao —, mas o conteudo
sai daqui, do mesmo lugar que ja monta recibo, comanda e DANFE.

A razao de nao deixar isso no cliente: o relatorio de fechamento e o documento
que o operador assina e o gerente confere. Duas implementacoes (uma no Flutter,
outra aqui) divergiriam no primeiro ajuste de regra, e a divergencia apareceria
no papel assinado — o pior lugar possivel para descobrir.

Largura e coluna de valor sao as mesmas de `services.py`, para o papel do caixa
ter a cara do papel da venda.
"""

from decimal import Decimal

from django.utils import timezone

from apps.payments.models import CashMovement, CashRegister
from apps.printers.services import (
    LARGURA_CUPOM,
    _establishment_info,
    _establishment_lines,
    _linha_valor,
)

_REGUA = "-" * 42
_ASSINATURA = "_" * 30

_ROTULO_STATUS = {
    CashRegister.STATUS_CLOSED: "FECHADO",
    CashRegister.STATUS_CLOSED_DIFFERENCE: "FECHADO COM DIVERGENCIA",
    CashRegister.STATUS_PENDING_APPROVAL: "AGUARDANDO APROVACAO GERENCIAL",
    CashRegister.STATUS_PENDING_CLOSING: "AGUARDANDO FECHAMENTO",
    CashRegister.STATUS_OPEN: "ABERTO",
    CashRegister.STATUS_BLOCKED: "BLOQUEADO",
    CashRegister.STATUS_PENDING_OPENING: "AGUARDANDO ABERTURA",
    CashRegister.STATUS_CANCELLED: "CANCELADO",
}

# Ordem em que o operador confere os comprovantes no fechamento: a gaveta
# primeiro, depois as maquininhas, depois o resto.
_ORDEM_FORMAS = ["cash", "card:credit", "card:debit", "card", "pix", "voucher", "other"]
_ROTULO_FORMAS = {
    "cash": "Dinheiro",
    "card:credit": "Cartao credito",
    "card:debit": "Cartao debito",
    "card": "Cartao",
    "pix": "PIX",
    "voucher": "Vale/voucher",
    "other": "Outras formas",
}


def _dinheiro(valor):
    return f"{Decimal(valor or 0):.2f}"


def _quando(valor=None):
    momento = timezone.localtime(valor) if valor else timezone.localtime()
    return momento.strftime("%d/%m/%Y %H:%M:%S")


def _centralizado(texto, largura=LARGURA_CUPOM):
    return str(texto)[:largura].center(largura)


def _corta(texto, largura=LARGURA_CUPOM):
    return str(texto)[:largura]


def _cabecalho(session, titulo):
    """Identificacao do estabelecimento + titulo do documento.

    `_establishment_info` foi escrito para um pedido, mas so le `restaurant` e
    `branch` — os mesmos campos que a sessao de caixa tem. Um objeto simples com
    esses dois atributos evita duplicar a regra de "filial primeiro, matriz
    depois" que define o CNPJ impresso.
    """
    info = _establishment_info(
        type("_Escopo", (), {"restaurant": session.restaurant, "branch": session.branch})()
    )
    return [*_establishment_lines(info), _REGUA, _centralizado(titulo), _REGUA]


def _linhas_sessao(session, operator_name=""):
    estacao = (session.cash_station.name if session.cash_station_id else session.station) or ""
    terminal = session.opened_terminal_label or ""
    from apps.payments.terminals import operator_label

    operador = (operator_name or "").strip() or operator_label(session.opened_by)
    linhas = []
    if estacao:
        linhas.append(_corta(f"Caixa: {estacao}"))
    if operador:
        linhas.append(_corta(f"Operador: {operador}"))
    if terminal:
        linhas.append(_corta(f"Terminal: {terminal}"))
    return linhas


def _linhas_observacao(rotulo, valor):
    texto = str(valor or "").strip()
    return [_corta(f"{rotulo}: {texto}")] if texto else []


def _rodape():
    return [_REGUA, f"Impresso em {_quando()}", ""]


def opening_text(session, *, operator_name=""):
    """Comprovante de abertura (fundo de troco inicial)."""
    linhas = [
        *_cabecalho(session, "COMPROVANTE DE ABERTURA DE CAIXA"),
        f"Data: {_quando(session.opened_at)}",
        *_linhas_sessao(session, operator_name),
        _REGUA,
        _linha_valor("Valor inserido (troco)", _dinheiro(session.opening_amount)),
        "Motivo: Fundo de troco inicial",
        *_linhas_observacao("Obs", session.notes),
        _REGUA,
        f"Assinatura: {_ASSINATURA}",
        *_rodape(),
    ]
    return "\n".join(linhas)


def movement_text(movement, *, operator_name="", authorized_by="", manager_reason=""):
    """Comprovante de sangria ou suprimento.

    `authorized_by` e quem liberou o movimento: o gerente, ou "senha de acoes do
    caixa" quando a autorizacao foi por senha e nao ha usuario por tras dela.
    """
    session = movement.cash_register
    saida = movement.movement_type == CashMovement.TYPE_WITHDRAWAL
    linhas = [
        *_cabecalho(
            session,
            "COMPROVANTE DE SANGRIA DE CAIXA" if saida else "COMPROVANTE DE SUPRIMENTO DE CAIXA",
        ),
        f"Data: {_quando(movement.created_at)}",
        *_linhas_sessao(session, operator_name),
    ]
    if str(authorized_by or "").strip():
        linhas.append(_corta(f"Autorizado por: {authorized_by.strip()}"))
    linhas += [
        _REGUA,
        _linha_valor(
            "Valor retirado" if saida else "Valor inserido",
            _dinheiro(abs(movement.amount)),
        ),
        *_linhas_observacao("Motivo", movement.reason),
        *_linhas_observacao("Destino" if saida else "Origem", movement.destination),
        *_linhas_observacao("Justificativa", manager_reason),
        _REGUA,
        "Assinatura do responsavel:",
        _ASSINATURA,
        *_rodape(),
    ]
    return "\n".join(linhas)


def _gaveta(session):
    """A gaveta em centavos: o que entrou e o que saiu em DINHEIRO.

    Os valores saem dos movimentos aprovados, com o sinal que cada tipo carrega
    — a mesma conta do saldo esperado. Uma sangria ligada a um pagamento nao e
    sangria: e o troco de um cartao/PIX saindo da gaveta, e sai em linha
    propria porque o operador precisa distinguir as duas coisas ao conferir.
    """
    abertura = supri = sangria = troco = estorno = vendas = 0
    tem_abertura = False
    for movimento in session.movements.all():
        if movimento.status != "approved":
            continue
        centavos = int((abs(Decimal(movimento.amount)) * 100).to_integral_value())
        if movimento.movement_type == CashMovement.TYPE_OPENING:
            abertura += centavos
            tem_abertura = True
        elif movimento.movement_type == CashMovement.TYPE_SALE:
            vendas += centavos
        elif movimento.movement_type == CashMovement.TYPE_SUPPLY:
            supri += centavos
        elif movimento.movement_type == CashMovement.TYPE_WITHDRAWAL:
            if movimento.payment_id:
                troco += centavos
            else:
                sangria += centavos
        elif movimento.movement_type == CashMovement.TYPE_REFUND:
            estorno += centavos
    if not tem_abertura:
        abertura = int((Decimal(session.opening_amount or 0) * 100).to_integral_value())
    esperado = int((Decimal(session.expected_amount or 0) * 100).to_integral_value())
    contado = int((Decimal(session.actual_amount or 0) * 100).to_integral_value())
    diferenca = int((Decimal(session.difference_amount or 0) * 100).to_integral_value())
    return {
        "abertura": abertura,
        "vendas": vendas,
        "suprimentos": supri,
        "sangrias": sangria,
        "troco": troco,
        "estornos": estorno,
        "esperado": esperado,
        "contado": contado,
        "diferenca": diferenca,
    }


def _vendas_por_forma(session):
    """Recebimentos da sessao agrupados por forma de pagamento.

    `movements` so conhece o dinheiro. O que o operador confere contra a
    maquininha e o comprovante do PIX esta aqui.
    """
    from django.db.models import Q

    from apps.payments.models import Payment

    recebimentos = (
        Payment.objects.filter(status=Payment.STATUS_APPROVED)
        .filter(Q(metadata__cash_register=str(session.pk)) | Q(cash_movements__cash_register_id=session.pk))
        .select_related("payment_method")
        .distinct()
    )
    totais = {}
    total = quantidade = 0
    for recebimento in recebimentos:
        tipo = (recebimento.payment_method.method_type or "other").strip().lower()
        subtipo = (recebimento.card_subtype or "").strip().lower()
        chave = f"card:{subtipo}" if tipo == "card" and subtipo else tipo
        if chave not in _ROTULO_FORMAS:
            chave = "other"
        centavos = int((Decimal(recebimento.amount or 0) * 100).to_integral_value())
        totais[chave] = totais.get(chave, 0) + centavos
        total += centavos
        quantidade += 1
    return {
        "linhas": [(_ROTULO_FORMAS[chave], totais[chave]) for chave in _ORDEM_FORMAS if chave in totais],
        "total": total,
        "dinheiro": totais.get("cash", 0),
        "quantidade": quantidade,
    }


def _centavos(rotulo, centavos):
    return _linha_valor(rotulo, f"{Decimal(centavos) / 100:.2f}")


def closing_text(session, *, operator_name=""):
    """Relatorio de fechamento: a gaveta (dinheiro) e as vendas por forma."""
    gaveta = _gaveta(session)
    vendas = _vendas_por_forma(session)
    linhas = [
        *_cabecalho(session, "RELATORIO DE FECHAMENTO DE CAIXA"),
        *_linhas_sessao(session, operator_name),
        f"Abertura: {_quando(session.opened_at)}",
        f"Fechamento: {_quando(session.closed_at)}",
        _REGUA,
        _centralizado("MOVIMENTO DA GAVETA (DINHEIRO)"),
        _centavos("(+) Abertura (troco)", gaveta["abertura"]),
        _centavos("(+) Vendas em dinheiro", gaveta["vendas"]),
        _centavos("(+) Suprimentos", gaveta["suprimentos"]),
        _centavos("(-) Sangrias", gaveta["sangrias"]),
    ]
    if gaveta["troco"]:
        linhas.append(_centavos("(-) Troco de outras formas", gaveta["troco"]))
    if gaveta["estornos"]:
        linhas.append(_centavos("(-) Estornos em dinheiro", gaveta["estornos"]))
    linhas += [
        _centavos("(=) Esperado em caixa", gaveta["esperado"]),
        _centavos("Valor contado", gaveta["contado"]),
        _centavos("Diferenca", gaveta["diferenca"]),
        _REGUA,
        _centralizado("VENDAS POR FORMA DE PAGAMENTO"),
        *[_centavos(rotulo, centavos) for rotulo, centavos in vendas["linhas"]],
        _centavos("Total de vendas", vendas["total"]),
        _centavos("Comprovantes (nao dinheiro)", vendas["total"] - vendas["dinheiro"]),
        f"Recebimentos: {vendas['quantidade']}",
        _REGUA,
        f"Status: {_ROTULO_STATUS.get(session.status, session.status.upper())}",
        *_linhas_observacao("Obs", session.notes),
        "Assinatura do gerente:",
        _ASSINATURA,
        *_rodape(),
    ]
    return "\n".join(linhas)
