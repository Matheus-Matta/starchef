"""A baixa do dia: sai do estoque como uma saída comum, uma vez só."""
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cardapio_consumo.execucao import JaExecutado, executar, executar_vencidos
from apps.cardapio_consumo.quem_executa import BaixaSoNaNuvem
from apps.cardapio_consumo.models import CardapioConsumo, ExecucaoCardapio
from apps.notifications.models import Notification
from apps.stock.models import StockExit, StockLot

pytestmark = pytest.mark.django_db
HOJE = date(2026, 11, 10)  # terça


def _saldo(ingredient):
    return sum(lote.quantity for lote in StockLot.objects.filter(ingredient=ingredient))


def test_confirma_sozinho_baixa_do_estoque_como_saida_comum(cardapio, insumo, estoque):
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    buffet = cardapio([(arroz, 8)], confirma_sozinho=True)

    execucao = executar(buffet, HOJE)

    assert execucao.situacao == ExecucaoCardapio.CONFIRMADA and execucao.faltas == []
    assert StockExit.objects.get(pk=execucao.saida_id).status == StockExit.STATUS_POSTED
    assert _saldo(arroz) == Decimal("12.000")


def test_sem_saldo_baixa_o_que_tem_e_diz_quanto_faltou(cardapio, insumo, estoque):
    """Decisão do dono: pediu 8 kg, há 5 kg → saem 5 kg e o aviso diz que faltaram 3 kg."""
    arroz, oleo = insumo("Arroz"), insumo("Óleo", "l")
    estoque(arroz, 5)
    buffet = cardapio([(arroz, 8), (oleo, 1)], confirma_sozinho=True)

    execucao = executar(buffet, HOJE)

    assert execucao.situacao == ExecucaoCardapio.CONFIRMADA
    assert _saldo(arroz) == Decimal("0.000")
    faltas = {falta["nome"]: falta["faltou"] for falta in execucao.faltas}
    assert faltas == {"Arroz": "3.000", "Óleo": "1.000"}
    aviso = Notification.all_objects.get(object_id=str(execucao.pk))
    assert aviso.title == "Baixa parcial: Buffet"
    assert "Faltou 3 kg de Arroz; faltou 1 l de Óleo" in aviso.body


def test_para_conferir_deixa_a_saida_em_rascunho_sem_mexer_no_estoque(cardapio, insumo, estoque):
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    execucao = executar(cardapio([(arroz, 8)], confirma_sozinho=False), HOJE)

    assert execucao.situacao == ExecucaoCardapio.PARA_CONFERIR
    assert execucao.saida.status == StockExit.STATUS_DRAFT
    assert _saldo(arroz) == Decimal("20.000")


def test_produto_sai_pela_ficha_tecnica_e_unidade_e_convertida(cardapio, insumo, estoque, produto_com_ficha):
    """Lasanha com ficha de 10 porções: 20 porções gastam o dobro da ficha."""
    massa, queijo = insumo("Massa"), insumo("Queijo")
    estoque(massa, 10)
    estoque(queijo, 10)
    lasanha = produto_com_ficha("Lasanha", 10, [(massa, 1, "kg"), (queijo, 500, "g")])
    execucao = executar(cardapio([(lasanha, 20), (queijo, 250, "g")], confirma_sozinho=True), HOJE)

    assert execucao.situacao == ExecucaoCardapio.CONFIRMADA
    assert _saldo(massa) == Decimal("8.000")
    assert _saldo(queijo) == Decimal("8.750")


def test_o_mesmo_dia_nunca_baixa_duas_vezes(cardapio, insumo, estoque):
    """Worker reiniciado no meio, ou dois no mesmo minuto: o índice único barra o segundo."""
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    buffet = cardapio([(arroz, 8)], confirma_sozinho=True)
    executar(buffet, HOJE)

    with pytest.raises(JaExecutado):
        executar(buffet, HOJE)
    assert _saldo(arroz) == Decimal("12.000")
    assert StockExit.objects.count() == 1


def test_agendador_so_executa_o_que_venceu_hoje_e_passou_do_horario(cardapio, insumo, estoque):
    arroz = insumo("Arroz")
    estoque(arroz, 50)
    terca = cardapio([(arroz, 1)], nome="Terça", frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[1])
    quarta = cardapio([(arroz, 1)], nome="Quarta", frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[2])
    mais_tarde = cardapio([(arroz, 1)], nome="Noite", horario=time(20, 0))
    oito_horas = timezone.make_aware(datetime.combine(HOJE, time(8, 0)))

    assert executar_vencidos(oito_horas) == 1
    assert executar_vencidos(oito_horas) == 0
    executados = set(ExecucaoCardapio.objects.values_list("cardapio__nome", flat=True))
    assert executados == {terca.nome} and quarta.nome not in executados and mais_tarde.nome not in executados


def test_loja_ligada_a_nuvem_nunca_baixa_so_recebe(cardapio, insumo, estoque, settings):
    """Os dois agendadores rodam. Se a loja também baixasse, o estoque sairia em
    dobro — e no dia da instalação ela baixava de novo o que a nuvem já baixou
    de manhã, antes de a execução da nuvem chegar."""
    settings.SYNC_ENABLED, settings.SYNC_NODE_TYPE = True, "local"
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    buffet = cardapio([(arroz, 8)], confirma_sozinho=True)

    assert executar_vencidos(timezone.make_aware(datetime.combine(HOJE, time(8, 0)))) == 0
    with pytest.raises(BaixaSoNaNuvem):
        executar(buffet, HOJE)
    assert _saldo(arroz) == Decimal("20.000")
    assert not ExecucaoCardapio.all_objects.exists()


def test_nuvem_baixa_mesmo_com_servidor_de_loja(cardapio, insumo, estoque, settings, account):
    """Quem baixa é sempre a nuvem; a loja recebe a saída pela sincronização."""
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    settings.SYNC_ENABLED, settings.SYNC_NODE_TYPE = True, "cloud"
    SyncNode.objects.create(account=account, node_type=NodeType.LOCAL, name="Loja", status="ACTIVE")
    arroz = insumo("Arroz")
    estoque(arroz, 20)
    cardapio([(arroz, 8)], confirma_sozinho=True)

    assert executar_vencidos(timezone.make_aware(datetime.combine(HOJE, time(8, 0)))) == 1
    assert _saldo(arroz) == Decimal("12.000")
