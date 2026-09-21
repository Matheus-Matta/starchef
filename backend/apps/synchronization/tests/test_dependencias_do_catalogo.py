"""Nenhum campo do payload pode apontar para um modelo que não sincroniza.

O defeito que isto fecha, encontrado em produção: `Account.plan` é chave
estrangeira para `accounts.Plan`, que está em `decisions.py` como "a loja não
opera planos". As duas decisões são defensáveis sozinhas e incompatíveis
juntas — o evento da conta falhava com "Plan … ainda não existe aqui",
retentava e falhava de novo, para sempre. A conta ficava presa no esqueleto
"(aguardando sincronização)", inativa.

Este teste varre o catálogo inteiro e cobra a regra. Ele existe para que o
próximo modelo adicionado com uma FK para fora do catálogo quebre AQUI, e não
na primeira loja que tentar sincronizar.
"""
import pytest

from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


def _fks_que_viajam(entrada):
    """As chaves estrangeiras que o payload desta entidade realmente carrega."""
    from apps.synchronization.services.serialization import _campo_permitido

    return [
        campo for campo in entrada.model._meta.concrete_fields
        if campo.is_relation and _campo_permitido(campo.name, entrada)
    ]


def test_toda_fk_do_payload_aponta_para_entidade_sincronizada():
    sincronizados = {e.model for e in registry.entries.values()}
    problemas = []

    for entrada in registry.entries.values():
        for campo in _fks_que_viajam(entrada):
            alvo = campo.related_model
            if alvo in sincronizados:
                continue
            problemas.append(
                f"{entrada.entity_type}.{campo.name} -> "
                f"{alvo._meta.label} (não sincroniza)"
            )

    assert not problemas, (
        "Estes campos tornariam o evento impossível de aplicar no destino — "
        "ele falha com 'ainda não existe aqui' e retenta para sempre.\n"
        "Resolva incluindo o alvo no catálogo OU pondo o campo em "
        "`exclude_fields` (só se ele for nulável):\n  " + "\n  ".join(problemas)
    )


def test_campo_excluido_por_ser_orfao_precisa_ser_nulavel():
    """Excluir uma FK obrigatória troca um defeito por outro.

    Sem o campo, o destino tenta gravar a linha sem a chave e o banco recusa
    por NOT NULL. A exclusão só é saída legítima quando o campo aceita nulo.
    """
    sincronizados = {e.model for e in registry.entries.values()}
    problemas = []

    for entrada in registry.entries.values():
        for campo in entrada.model._meta.concrete_fields:
            if not campo.is_relation or campo.name not in entrada.exclude_fields:
                continue
            if campo.related_model in sincronizados:
                continue
            if not campo.null:
                problemas.append(f"{entrada.entity_type}.{campo.name} é NOT NULL")

    assert not problemas, (
        "Campo obrigatório fora do payload: o destino não consegue gravar a "
        "linha.\n  " + "\n  ".join(problemas)
    )


def test_a_conta_nao_leva_o_plano():
    """O caso concreto que originou os dois testes acima."""
    entrada = registry.require("account")
    assert "plan" in entrada.exclude_fields
    assert entrada.model._meta.get_field("plan").null, (
        "excluir `plan` só é válido porque ele aceita nulo"
    )


def test_dependencias_declaradas_existem_no_catalogo():
    """`dependencies` define a ordem da carga; apontar para o nada a quebra."""
    faltando = [
        f"{entrada.entity_type} -> {dep}"
        for entrada in registry.entries.values()
        for dep in entrada.dependencies
        if registry.get(dep) is None
    ]
    assert not faltando, "dependência declarada que não está no catálogo:\n  " + "\n  ".join(faltando)
