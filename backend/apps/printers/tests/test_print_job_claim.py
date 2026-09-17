"""A reserva de um cupom de impressao.

A fila de impressao e da UNIDADE, nao de um terminal: dois PDVs no mesmo
restaurante consultam a mesma lista de pendentes, e uma impressora de rede e
alcancavel dos dois. Sem uma reserva atomica, os dois ingerem o mesmo trabalho
entre uma consulta e outra e a comanda sai duas vezes na cozinha.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.printers.models import PrintJob

pytestmark = pytest.mark.django_db

# `PrintJob.objects` e tenant-scoped: fora de uma requisicao ele devolve
# `.none()`, e um `.update()` por ali nao altera linha nenhuma — silenciosamente.
# `all_objects` e o manager cru, que e o que um teste precisa para montar o
# estado de partida.
_rows = PrintJob.all_objects


@pytest.fixture
def job(account, restaurant, branch, admin_user):
    return PrintJob.all_objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        job_type=PrintJob.TYPE_KITCHEN,
        status=PrintJob.STATUS_PENDING,
        payload={"text_content": "X-BURGER"},
        created_by=admin_user,
        updated_by=admin_user,
    )


def _claim(client, job, terminal):
    return client.post(
        f"/api/v1/print-jobs/{job.id}/claim/",
        {},
        format="json",
        headers={"X-Terminal-Id": terminal},
    )


def test_o_primeiro_terminal_leva_o_cupom(admin_client, job):
    resposta = _claim(admin_client, job, "terminal-a")

    assert resposta.status_code == 200
    job.refresh_from_db()
    assert job.status == PrintJob.STATUS_CLAIMED
    assert job.payload["claimed_by_terminal"] == "terminal-a"


def test_o_segundo_terminal_recebe_409_e_nao_imprime(admin_client, job):
    _claim(admin_client, job, "terminal-a")

    resposta = _claim(admin_client, job, "terminal-b")

    # 409 e o que faz o outro PDV ignorar este cupom em vez de manda-lo para a
    # impressora. Sem isso, a comanda sai nas duas pontas da loja.
    assert resposta.status_code == 409
    job.refresh_from_db()
    assert job.payload["claimed_by_terminal"] == "terminal-a"


def test_o_dono_renova_a_propria_reserva(admin_client, job):
    """Uma impressora sem papel pode insistir por mais tempo que o TTL.

    Se a reserva expirasse no meio dessa insistencia, outro terminal pegaria o
    mesmo cupom e a comanda sairia duas vezes.
    """
    _claim(admin_client, job, "terminal-a")
    job.refresh_from_db()
    _rows.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(minutes=4)
    )

    resposta = _claim(admin_client, job, "terminal-a")

    assert resposta.status_code == 200
    job.refresh_from_db()
    assert job.status == PrintJob.STATUS_CLAIMED
    assert job.updated_at > timezone.now() - timedelta(minutes=1)


def test_reserva_abandonada_volta_para_a_fila(admin_client, job):
    """O PDV que reservou foi fechado e nunca imprimiu.

    Sem devolver, o cupom ficaria `claimed` para sempre — invisivel para os
    outros terminais, que so olham `pending` e `rendered` — e a cozinha nunca
    receberia a comanda.
    """
    _claim(admin_client, job, "terminal-a")
    _rows.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(minutes=10)
    )

    # A varredura roda na listagem, que e o que o agente de cada terminal
    # consulta a cada ciclo.
    assert admin_client.get("/api/v1/print-jobs/").status_code == 200

    job.refresh_from_db()
    assert job.status == PrintJob.STATUS_PENDING

    assert _claim(admin_client, job, "terminal-b").status_code == 200


def test_release_devolve_o_cupom_para_quem_conseguir_imprimir(admin_client, job):
    _claim(admin_client, job, "terminal-a")

    resposta = admin_client.post(f"/api/v1/print-jobs/{job.id}/release/", {}, format="json")

    assert resposta.status_code == 200
    assert resposta.json()["released"] is True
    job.refresh_from_db()
    assert job.status == PrintJob.STATUS_PENDING


def test_cupom_ja_impresso_nao_pode_ser_reservado(admin_client, job):
    _rows.filter(pk=job.pk).update(status=PrintJob.STATUS_PRINTED)

    assert _claim(admin_client, job, "terminal-a").status_code == 409
