"""Dois eventos da MESMA entidade não se aplicam ao mesmo tempo.

Achado no par Docker (`loadtest/dia_a_dia`): a nuvem recebeu as 5 versões de um
pedido em ordem — a última "pago" — e terminou com a 3ª ("aberto"), sem
descarte nenhum. Dois workers aplicavam versões do mesmo pedido em paralelo:
cada um LIA a linha sem trava e decidia "sou a mais nova" com o que tinha
lido; a 3ª, decidida antes da 5ª gravar, sobrescreveu. A trava por entidade
vem ANTES da leitura: a segunda aplicação decide com o que a primeira gravou.

No PostgreSQL é `pg_advisory_xact_lock` (vale até para a linha que ainda não
existe); aqui, sem ele, o teste prova a ordem: trava, depois lê.
"""
import uuid

import pytest

from apps.synchronization.services import apply
from apps.synchronization.tests.test_apply import _evento

pytestmark = pytest.mark.django_db


def test_trava_a_entidade_antes_de_ler_a_linha(como_loja, conta, no_nuvem, no_loja, monkeypatch):
    ordem = []
    ler = apply._encontrar
    monkeypatch.setattr(apply, "trava_da_entidade", lambda tipo, pk: ordem.append(("trava", tipo, str(pk))))
    monkeypatch.setattr(apply, "_encontrar", lambda m, pk: (ordem.append(("le",)), ler(m, pk))[1])
    restaurante_id = uuid.uuid4()

    apply.apply_event(_evento(conta, no_nuvem, no_loja, entity_type="restaurant",
                              entity_id=restaurante_id,
                              fields={"account_id": str(conta.id), "legal_name": "T LTDA",
                                      "trade_name": "T", "is_active": True}))

    assert ordem[0] == ("trava", "restaurant", str(restaurante_id))
    assert ("le",) in ordem[1:]
