"""Executar o cardápio do dia: uma saída de estoque comum, criada sozinha.

A saída passa pelo mesmo caminho da tela (separação FIFO/FEFO e confirmação
em `stock/lots.py`), então lote, custo e movimento saem iguais aos de uma
saída lançada à mão.

Sem saldo, baixa o que tem (decisão do dono, 2026-11-08): o insumo sem nada
sai do documento, o parcial passa a pedir o que foi separado, e o que faltou
fica em `faltas` e no aviso. O aviso ANTES do dia é `aviso_antecipado.py`.
"""
import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cardapio_consumo.agenda import vence_em
from apps.cardapio_consumo.models import CardapioConsumo, ExecucaoCardapio
from apps.cardapio_consumo.necessidade import necessidade_do_cardapio
from apps.cardapio_consumo.quem_executa import este_servidor_executa, garantir_que_este_servidor_executa
from apps.core.tenant import tenant_context
from apps.stock.lots import QUANTITY_PLACES, post_stock_exit, suggest_exit_lots
from apps.stock.models import StockExit, StockExitItem

logger = logging.getLogger(__name__)


class JaExecutado(Exception):
    """O cardápio já tem execução neste dia (o índice único barrou)."""


def executar_vencidos(agora=None):
    """Chamado pelo beat. Só o dia de HOJE: servidor parado não acumula dias."""
    if not este_servidor_executa():
        return 0
    agora = timezone.localtime(agora or timezone.now())
    hoje = agora.date()
    candidatos = (
        CardapioConsumo.all_objects.filter(ativo=True, deleted_at__isnull=True, comeca_em__lte=hoje,
                                           horario__lte=agora.time())
        .exclude(execucoes__data=hoje)
        .select_related("account", "local")
    )
    feitos = 0
    for cardapio in candidatos:
        if not vence_em(cardapio, hoje):
            continue
        try:
            executar(cardapio, hoje)
        except JaExecutado:
            continue
        feitos += 1
    return feitos


def responsavel(cardapio):
    """Quem assina a baixa: o movimento de estoque exige um operador."""
    from apps.notifications.services import managers_of_account

    return cardapio.updated_by or cardapio.created_by or managers_of_account(cardapio.account_id).first()


def executar(cardapio, data, user=None):
    """Cria (e, se o cardápio pede, confirma) a saída do dia. Uma vez por dia."""
    from apps.cardapio_consumo.avisos import avisar_execucao

    garantir_que_este_servidor_executa()
    user = user or responsavel(cardapio)
    with tenant_context(cardapio.account):
        try:
            with transaction.atomic():
                execucao = ExecucaoCardapio.objects.create(
                    account=cardapio.account, restaurant=cardapio.restaurant, branch=cardapio.branch,
                    cardapio=cardapio, data=data, situacao=ExecucaoCardapio.PARA_CONFERIR,
                    created_by=user, updated_by=user,
                )
                _baixar(execucao, user)
        except IntegrityError as exc:
            if ExecucaoCardapio.all_objects.filter(cardapio=cardapio, data=data).exists():
                raise JaExecutado(f"{cardapio.nome} já foi executado em {data:%d/%m/%Y}.") from exc
            execucao = _registrar_falha(cardapio, data, exc, user)
        except Exception as exc:  # noqa: BLE001 — a falha vira registro e aviso, não um beat quebrado.
            logger.exception("Cardápio de consumo %s falhou em %s", cardapio.pk, data)
            execucao = _registrar_falha(cardapio, data, exc, user)
    avisar_execucao(execucao)
    return execucao


def _registrar_falha(cardapio, data, exc, user):
    try:
        return ExecucaoCardapio.objects.create(
            account=cardapio.account, restaurant=cardapio.restaurant, branch=cardapio.branch,
            cardapio=cardapio, data=data, situacao=ExecucaoCardapio.FALHOU, mensagem=str(exc)[:500],
            created_by=user, updated_by=user,
        )
    except IntegrityError as erro:
        raise JaExecutado(f"{cardapio.nome} já foi executado em {data:%d/%m/%Y}.") from erro


def _baixar(execucao, user):
    cardapio = execucao.cardapio
    necessidade = necessidade_do_cardapio(cardapio)
    execucao.mensagem = " ".join(necessidade.avisos)[:2000]
    linhas = necessidade.linhas()
    if not linhas:
        raise ValueError("Nada para baixar: o cardápio não tem itens que viram insumo. " + execucao.mensagem)
    if user is None:
        raise ValueError("Ninguém para assinar a baixa: a conta não tem gerente ativo.")

    saida = _criar_saida(cardapio, execucao.data, linhas, user)
    faltas = suggest_exit_lots(exit_document=saida, user=user)
    execucao.saida = saida
    execucao.faltas = _faltas_legiveis(saida, faltas)
    if not cardapio.confirma_sozinho:
        execucao.situacao = ExecucaoCardapio.PARA_CONFERIR
    elif not saida.items.filter(fulfilled_quantity__gt=0).exists():
        execucao.situacao = ExecucaoCardapio.SEM_SALDO
    else:
        _ficar_com_o_que_tem(saida)
        # A confirmação automática não tem quem leia etiqueta; a exigência
        # da configuração vale para a saída feita à mão.
        StockExit.objects.filter(pk=saida.pk).update(require_label_scan=False)
        post_stock_exit(exit_document=saida, user=user)
        execucao.situacao = ExecucaoCardapio.CONFIRMADA
    execucao.save()


def _criar_saida(cardapio, data, linhas, user):
    local = cardapio.local
    comum = {"account": cardapio.account, "restaurant": local.restaurant, "branch": local.branch,
             "created_by": user, "updated_by": user}
    saida = StockExit.objects.create(
        **comum, location=local, effective_date=data, exit_type=StockExit.TYPE_CONSUMPTION,
        reason=f"Cardápio de consumo: {cardapio.nome} ({data:%d/%m/%Y})",
    )
    for ingredient, quantidade in linhas:
        StockExitItem.objects.create(**comum, exit=saida, ingredient=ingredient, requested_quantity=quantidade,
                                     notes="Cardápio de consumo")
    return saida


def _ficar_com_o_que_tem(saida):
    for item in saida.items.all():
        separado = Decimal(str(item.fulfilled_quantity))
        if separado <= 0:
            StockExitItem.all_objects.filter(pk=item.pk).delete()
        elif separado < Decimal(str(item.requested_quantity)):
            item.requested_quantity = separado
            item.save(update_fields=["requested_quantity", "updated_at"])


def _faltas_legiveis(saida, faltas):
    pedidos = {str(item.ingredient_id): item for item in saida.items.select_related("ingredient")}
    legiveis = []
    for falta in faltas:
        item = pedidos[falta["ingredient"]]
        legiveis.append({
            "ingredient": falta["ingredient"], "nome": item.ingredient.name, "unidade": item.ingredient.unit,
            "pedido": str(Decimal(str(item.requested_quantity)).quantize(QUANTITY_PLACES)),
            "baixado": str(Decimal(str(item.fulfilled_quantity)).quantize(QUANTITY_PLACES)),
            "faltou": falta["missing"],
        })
    return legiveis
