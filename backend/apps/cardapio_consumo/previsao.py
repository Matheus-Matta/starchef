"""Antes do dia: vai faltar? A previsão da tela e o aviso de véspera.

O dono pediu para saber ANTES ("faltam 3 kg de arroz para o buffet de
terça"), não só depois da baixa. A previsão soma os cardápios do mesmo local
num dia e compara com o saldo de AGORA: a conta é a que a separação faria se
rodasse neste instante.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.cardapio_consumo.agenda import vence_em
from apps.cardapio_consumo.avisos import avisar, quantidade
from apps.cardapio_consumo.models import CardapioConsumo
from apps.cardapio_consumo.necessidade import necessidade_do_cardapio, saldo_no_local
from apps.cardapio_consumo.quem_executa import este_servidor_executa
from apps.core.tenant import tenant_context
from apps.stock.lots import settings_for

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def previsao_para(cardapios, local):
    """[{nome, unidade, precisa, saldo, falta, cardapios}] e os avisos de cadastro."""
    total, usos, avisos = {}, defaultdict(set), []
    for cardapio in cardapios:
        necessidade = necessidade_do_cardapio(cardapio)
        avisos.extend(necessidade.avisos)
        for ingredient, qtd in necessidade.linhas():
            atual = total.setdefault(str(ingredient.pk), [ingredient, Decimal("0")])
            atual[1] += qtd
            usos[str(ingredient.pk)].add(cardapio.nome)
    config = settings_for(local.account)
    linhas = []
    for chave, (ingredient, precisa) in sorted(total.items(), key=lambda par: par[1][0].name):
        saldo = saldo_no_local(ingredient, local, config)
        linhas.append({
            "ingredient": chave, "nome": ingredient.name, "unidade": ingredient.unit,
            "precisa": str(precisa), "saldo": str(saldo), "falta": str(max(precisa - saldo, Decimal("0"))),
            "cardapios": sorted(usos[chave]),
        })
    return linhas, avisos


def avisar_faltas_de_amanha(hoje=None):
    """Um aviso por conta e local, só quando algo vai faltar. Devolve quantos."""
    if not este_servidor_executa():
        return 0
    amanha = (hoje or timezone.localdate()) + timedelta(days=1)
    grupos = defaultdict(list)
    for cardapio in CardapioConsumo.all_objects.filter(ativo=True, deleted_at__isnull=True).select_related(
            "account", "local"):
        if vence_em(cardapio, amanha):
            grupos[(cardapio.account_id, cardapio.local_id)].append(cardapio)

    enviados = 0
    for cardapios in grupos.values():
        conta, local = cardapios[0].account, cardapios[0].local
        with tenant_context(conta):
            linhas, _ = previsao_para(cardapios, local)
        faltas = [linha for linha in linhas if Decimal(linha["falta"]) > 0]
        if not faltas:
            continue
        lista = "; ".join(
            f"{quantidade(linha['falta'], linha['unidade'])} de {linha['nome']} ({', '.join(linha['cardapios'])})"
            for linha in faltas
        )
        avisar(conta, nivel="warning", titulo=f"Vai faltar estoque amanhã ({DIAS[amanha.weekday()]}, {amanha:%d/%m})",
               corpo=f"Em {local.name}, faltam: {lista}. Dê entrada antes da baixa automática.",
               url="/cardapios-consumo")
        enviados += 1
    return enviados
