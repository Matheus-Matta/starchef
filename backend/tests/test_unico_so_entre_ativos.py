"""Excluir não pode prender o nome/código para sempre.

Excluir é só marcar `deleted_at`. Uma regra de "não pode repetir" que conta
os excluídos faz o item apagado continuar dono do nome: recriar o "Caixa 01",
reimportar um perfil fiscal ou cadastrar de novo a mesa 5 dava "Já existe um
registro com estes dados (valor duplicado)" sem nada com aquele nome na tela.
"""
import uuid

import pytest
from django.apps import apps

from apps.payments.models import CashStation
from apps.synchronization.services import adoption

#: Regras que DEVEM contar os excluídos, e por quê. Fora desta lista, toda
#: regra única de model com exclusão lógica tem de ignorar os excluídos.
CONTAM_OS_EXCLUIDOS = {
    "accounts.Role": "catálogo fixo provisionado por código; não se exclui pela tela",
    "images.ProductImage": "a mesma imagem não entra duas vezes no mesmo produto, nem depois",
    "orders.Order": "número do pedido é documento: não se reaproveita",
    "orders.OrderBatch": "rodada de produção é histórico do pedido",
    "orders.OrderItem": "um item de comanda vira no máximo um item de pedido, para sempre",
    "orders.CommandBatch": "rodada de produção é histórico da comanda",
    "kitchen.KdsItemPosition": "posição interna do KDS, não é cadastro",
    "payments.PdvTerminal": "identidade da instalação: a mesma máquina não vira outra",
    "payments.Payment": "chave de idempotência: reaproveitar duplicaria a cobrança",
    "printers.PrintJob": "um cancelamento por item, para sempre",
    "inbound_nfe.DFeDistributionDocument": "NSU da SEFAZ é único na vida do CNPJ",
    "inbound_nfe.InboundNFe": "a chave de acesso da NF-e é única no país",
    "inbound_nfe.NFeEvent": "evento fiscal é único por chave/código/sequência",
    "inbound_nfe.NFeManifestation": "manifestação é única por nota/evento/sequência",
    "inbound_nfe.InboundNFeItem": "item é único dentro da nota",
}


def _regras_que_contam_excluidos():
    for model in apps.get_models():
        if not any(campo.name == "deleted_at" for campo in model._meta.fields):
            continue
        for regra in model._meta.constraints:
            if regra.__class__.__name__ != "UniqueConstraint":
                continue
            if regra.condition is None or "deleted_at" not in str(regra.condition):
                yield model._meta.label, regra.name


def test_toda_regra_unica_ignora_os_excluidos_ou_tem_motivo_para_nao():
    sem_motivo = sorted(
        f"{label}.{nome}"
        for label, nome in _regras_que_contam_excluidos()
        if label not in CONTAM_OS_EXCLUIDOS
    )
    assert sem_motivo == [], (
        "Regra única que conta os excluídos: o item apagado prende o nome para "
        "sempre. Use condition=models.Q(deleted_at__isnull=True), ou explique "
        f"em CONTAM_OS_EXCLUIDOS por que deve contar: {sem_motivo}"
    )


@pytest.mark.django_db
def test_excluir_o_caixa_e_criar_outro_com_o_mesmo_codigo(admin_client, restaurant):
    corpo = {"name": "Caixa 01", "code": "CX01", "restaurant": str(restaurant.id)}
    criado = admin_client.post("/api/v1/cash-stations/", corpo, format="json")
    assert admin_client.delete(f"/api/v1/cash-stations/{criado.json()['id']}/").status_code == 204

    recriado = admin_client.post("/api/v1/cash-stations/", corpo, format="json")

    assert recriado.status_code == 201, recriado.json()
    assert admin_client.post("/api/v1/cash-stations/", corpo, format="json").status_code in (400, 409)


@pytest.mark.django_db
def test_sincronizacao_nao_trata_o_excluido_como_duplicata(account, restaurant):
    """A adoção APAGA a linha local que disputa a chave. Com a regra parcial,
    o excluído não disputa nada — adotá-lo apagaria o registro errado."""
    excluido = CashStation.all_objects.create(
        account=account, restaurant=restaurant, name="Caixa 01", code="CX01"
    )
    excluido.delete()

    duplicada, _ = adoption.find_local_duplicate(
        CashStation, {"restaurant_id": restaurant.id, "code": "CX01"}, remote_pk=uuid.uuid4()
    )

    assert duplicada is None
