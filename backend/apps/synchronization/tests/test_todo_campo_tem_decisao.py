"""A trava que faltava: CAMPO novo também precisa de decisão.

`sync_check_registry` reprova o deploy quando um MODEL novo aparece sem decisão.
Ele não diz nada sobre um CAMPO novo num model que já sincroniza — e essa é a
porta por onde os defeitos desta área entram, porque ela não tem porteiro.

Já custou três vezes nesta base:

* `OrderItem.command` teria ficado fora e a nuvem não saberia de quem é o item;
* `ScaleReading.notes` chegava sempre em branco (append-only descartava o
  UPDATE que a preenchia);
* `certificate_valid_until` é bloqueado pelo filtro de segredos só porque o
  nome contém "certificate" — uma tela de "seu certificado vence em N dias" na
  loja nunca funcionaria, e ninguém saberia por quê.

O filtro de segredos é por SUBSTRING (`password`, `token`, `secret`,
`certificate`, ...). Ele acerta o alvo quase sempre, e quando erra, erra em
silêncio. Este arquivo transforma o silêncio em reprovação.
"""
import pytest

from apps.synchronization.services import serialization
from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def _nome_no_payload(campo):
    """Chave estrangeira viaja como `<nome>_id`; o resto, pelo próprio nome."""
    return f"{campo.name}_id" if campo.is_relation else campo.name


def test_todo_campo_declarado_ou_viaja():
    """Nenhum campo pode deixar de viajar sem alguém ter decidido isso.

    Duas saídas legítimas para um campo que não viaja, e as duas são
    explícitas:

    * `exclude_fields` — a decisão de que ele não deve viajar (segredo, cache,
      derivado, FK para entidade que não sincroniza);
    * `allow_fields` — a decisão de que ele deve viajar apesar de o nome cair
      no filtro global (hoje só o hash de senha do usuário).

    Cair no filtro sem estar em nenhuma das duas não é decisão: é acidente.
    """
    acidentes = []

    for entrada in registry.entries.values():
        payload = set(serialization.serialize(entrada.model(), entrada).keys())
        for campo in entrada.model._meta.concrete_fields:
            if _nome_no_payload(campo) in payload:
                continue
            if campo.name in entrada.exclude_fields:
                continue
            acidentes.append(
                f"{entrada.entity_type}.{campo.name} "
                f"({entrada.model_label})"
            )

    assert not acidentes, (
        "Estes campos NÃO chegam ao outro lado, e ninguém declarou isso.\n\n"
        "Quase sempre é o filtro global de segredos casando por substring "
        "(`password`, `token`, `secret`, `certificate`, `private_key`, "
        "`api_key`) num nome que não é segredo.\n\n"
        "O sintoma aparece na loja dias depois, como \"sumiu\".\n\n"
        "Resolva declarando a decisão em `catalog.py`:\n"
        "  • não deve viajar  -> `exclude_fields`, com o motivo ao lado\n"
        "  • deve viajar      -> `allow_fields`, e diga por que o segredo é "
        "aceitável\n\n  " + "\n  ".join(sorted(acidentes))
    )


def test_o_filtro_de_segredos_continua_pegando_o_que_importa():
    """Se alguém afrouxar `CAMPOS_PROIBIDOS`, isto reprova.

    O teste acima empurra na direção de declarar campos; este segura a outra
    ponta, para "declarar" nunca virar "liberar o segredo".
    """
    from apps.synchronization.services.serialization import CAMPOS_PROIBIDOS

    for termo in ("password", "token", "secret", "private_key", "api_key", "certificate"):
        assert termo in CAMPOS_PROIBIDOS, (
            f"`{termo}` saiu do filtro global de segredos — um campo com esse "
            "nome passaria a viajar no payload de sincronização."
        )


def test_o_segredo_FISCAL_nao_viaja():
    """A senha e o arquivo que abrem o certificado A1 que assina a nota.

    Nunca saem do servidor por lugar nenhum — nem por sincronização, nem por
    endpoint. Quem assina é o backend; o terminal nunca precisa da chave.
    """
    for tipo, campo in (
        ("fiscal_config", "certificate_password"),
        ("fiscal_config", "certificate_file"),
    ):
        entrada = registry.require(tipo)
        payload = serialization.serialize(entrada.model(), entrada)
        assert campo not in payload, f"{tipo}.{campo} está viajando no payload"
        assert campo in entrada.exclude_fields, (
            f"{tipo}.{campo} não viaja por acidente do filtro, e não por "
            "decisão escrita — declare em `exclude_fields`"
        )


def test_a_senha_do_caixa_viaja_COMO_HASH_e_nunca_em_texto():
    """A senha de ações do caixa é o caso oposto, e de propósito.

    Ela estava em `exclude_fields`, e a exclusão não protegia nada: o MESMO
    hash já sai do servidor por `/restaurants/{id}/cash-auth/`, que é como o
    PDV o guarda para verificar sem rede (`payments._cash_password_proof`
    depende disso). O que a exclusão fazia era deixar a LOJA sem ele — e a
    loja é quem precisa autorizar sangria e cancelamento quando a nuvem cai.

    O que este teste protege é o que continua valendo: viaja o HASH, nunca o
    texto. `set_cash_action_password` codifica antes de gravar, então o texto
    puro não existe nem no banco.
    """
    from django.contrib.auth.hashers import identify_hasher

    from apps.restaurants.models import Restaurant

    entrada = registry.require("restaurant")
    restaurante = Restaurant()
    restaurante.set_cash_action_password("senha-da-casa")

    payload = serialization.serialize(restaurante, entrada)

    viajou = payload.get("cash_action_password")
    assert viajou, "a loja precisa do hash para autorizar com a nuvem fora"
    assert viajou != "senha-da-casa", "o texto puro da senha viajou"
    assert identify_hasher(viajou), "o que viajou não é um hash reconhecível"
