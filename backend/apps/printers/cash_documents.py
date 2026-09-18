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
from textwrap import wrap

from django.utils import timezone

from apps.payments.models import CashMovement, CashRegister
from apps.printers.cash_document_totals import gaveta, linha_centavos, vendas_por_forma
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
    if not texto:
        return []
    prefixo = f"{rotulo}: "
    partes = wrap(texto, width=max(1, LARGURA_CUPOM - len(prefixo))) or [""]
    return [f"{prefixo}{partes[0]}", *[f"{' ' * len(prefixo)}{parte}" for parte in partes[1:]]]


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


def opening_divergence_text(session, *, operator_name=""):
    """Comprovante emitido somente depois de autorizar a abertura divergente."""
    from apps.payments.terminals import operator_label

    autorizado_por = operator_label(session.approved_by) if session.approved_by_id else ""
    linhas = [
        *_cabecalho(session, "DIVERGENCIA AUTORIZADA NA ABERTURA"),
        f"Abertura: {_quando(session.opened_at)}",
        f"Autorizacao: {_quando(session.approved_at)}",
        *_linhas_sessao(session, operator_name),
        *_linhas_observacao("Autorizado por", autorizado_por),
        _REGUA,
        _linha_valor("Valor esperado", _dinheiro(session.expected_amount)),
        _linha_valor("Valor contado", _dinheiro(session.actual_amount)),
        _linha_valor("Diferenca", _dinheiro(session.difference_amount)),
        *_linhas_observacao("Justificativa", session.approval_reason),
        *_linhas_observacao("Obs", session.notes),
        _REGUA,
        "Assinatura do responsavel:",
        "",
        "",
        _ASSINATURA,
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
        "",
        "",
        _ASSINATURA,
        *_rodape(),
    ]
    return "\n".join(linhas)


def closing_text(session, *, operator_name=""):
    """Relatorio de fechamento: a gaveta (dinheiro) e as vendas por forma."""
    resumo_gaveta = gaveta(session)
    vendas = vendas_por_forma(session)
    linhas = [
        *_cabecalho(session, "RELATORIO DE FECHAMENTO DE CAIXA"),
        *_linhas_sessao(session, operator_name),
        f"Abertura: {_quando(session.opened_at)}",
        f"Fechamento: {_quando(session.closed_at)}",
        _REGUA,
        _centralizado("MOVIMENTO DA GAVETA (DINHEIRO)"),
        linha_centavos("(+) Abertura (troco)", resumo_gaveta["abertura"]),
        linha_centavos("(+) Vendas em dinheiro", resumo_gaveta["vendas"]),
        linha_centavos("(+) Suprimentos", resumo_gaveta["suprimentos"]),
        linha_centavos("(-) Sangrias", resumo_gaveta["sangrias"]),
    ]
    if resumo_gaveta["troco"]:
        linhas.append(linha_centavos("(-) Troco de outras formas", resumo_gaveta["troco"]))
    if resumo_gaveta["estornos"]:
        linhas.append(linha_centavos("(-) Estornos em dinheiro", resumo_gaveta["estornos"]))
    linhas += [
        linha_centavos("(=) Esperado em caixa", resumo_gaveta["esperado"]),
        linha_centavos("Valor contado", resumo_gaveta["contado"]),
        linha_centavos("Diferenca", resumo_gaveta["diferenca"]),
        _REGUA,
        _centralizado("VENDAS POR FORMA DE PAGAMENTO"),
        *[linha_centavos(rotulo, centavos) for rotulo, centavos in vendas["linhas"]],
        linha_centavos("Total de vendas", vendas["total"]),
        linha_centavos("Comprovantes (nao dinheiro)", vendas["total"] - vendas["dinheiro"]),
        f"Recebimentos: {vendas['quantidade']}",
        _REGUA,
        f"Status: {_ROTULO_STATUS.get(session.status, session.status.upper())}",
        *_linhas_observacao("Obs", session.notes),
        "Assinatura do gerente:",
        _ASSINATURA,
        *_rodape(),
    ]
    return "\n".join(linhas)
