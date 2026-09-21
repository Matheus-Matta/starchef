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


def test_o_segredo_do_caixa_e_do_fiscal_nao_viaja():
    """As duas senhas que, se vazassem, custariam dinheiro direto.

    `cash_action_password` autoriza sangria e cancelamento no caixa;
    `certificate_password` abre o certificado A1 que assina nota fiscal.
    """
    for tipo, campo in (
        ("restaurant", "cash_action_password"),
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
