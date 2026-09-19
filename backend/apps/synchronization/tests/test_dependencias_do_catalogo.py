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


# ── segredo nunca viaja ─────────────────────────────────────────────────────
#
# Uma auditoria encontrou o certificado A1 da empresa
# (`focus_certificate_base64`) viajando em cada evento e gravado na tabela de
# eventos dos DOIS lados — enquanto a SENHA dele, no campo ao lado, era
# bloqueada por conter "password". O inverso do que qualquer um esperaria.
PALAVRAS_DE_SEGREDO = (
    "password", "senha", "token", "secret", "segredo", "certificate",
    "certificado", "private_key", "api_key", "csc",
)


def test_nenhum_campo_com_cara_de_segredo_viaja():
    problemas = []
    for entrada in registry.entries.values():
        for campo in entrada.model._meta.concrete_fields:
            nome = campo.name.lower()
            if not any(palavra in nome for palavra in PALAVRAS_DE_SEGREDO):
                continue
            from apps.synchronization.services.serialization import _campo_permitido

            if campo.name in entrada.allow_fields:
                continue  # liberação nominal, conferida pelo teste abaixo
            if _campo_permitido(campo.name, entrada):
                problemas.append(f"{entrada.entity_type}.{campo.name}")

    assert not problemas, (
        "Campo com cara de segredo viajando no payload. Segredo fica gravado na "
        "tabela de eventos dos DOIS lados e sai em qualquer dump.\n"
        "Resolva incluindo a palavra em `CAMPOS_PROIBIDOS` (vale para todas as "
        "entidades) ou o campo em `exclude_fields`:\n  " + "\n  ".join(problemas)
    )


def test_exclude_fields_aponta_para_campo_que_existe():
    """Exclusão que mira no vazio dá a impressão de proteger e não protege.

    Havia duas no catálogo — `csc_token_homologation` e `csc_token_production` —
    e o CSC só estava protegido por acidente, porque `csc_token` contém "token"
    e caía no filtro global. Bastava alguém renomear o campo para o segredo
    passar a viajar, com a exclusão ali parecendo cuidar do assunto.
    """
    problemas = []
    for entrada in registry.entries.values():
        # ManyToMany entra na conta: ele E campo, so nao e concreto. Excluir
        # um vinculo e decisao legitima (`user.groups`, que este projeto nao
        # usa), e sem inclui-los aqui o teste acusaria essa decisao de mirar
        # no vazio.
        existentes = {c.name for c in entrada.model._meta.concrete_fields}
        existentes |= {c.name for c in entrada.model._meta.many_to_many}
        for campo in entrada.exclude_fields:
            if campo not in existentes:
                problemas.append(f"{entrada.entity_type}.{campo}")

    assert not problemas, (
        "`exclude_fields` aponta para campo inexistente:\n  " + "\n  ".join(problemas)
    )


def test_local_only_fields_aponta_para_campo_que_existe():
    problemas = []
    for entrada in registry.entries.values():
        existentes = {c.name for c in entrada.model._meta.concrete_fields}
        for campo in entrada.local_only_fields:
            if campo not in existentes:
                problemas.append(f"{entrada.entity_type}.{campo}")

    assert not problemas, (
        "`local_only_fields` aponta para campo inexistente:\n  " + "\n  ".join(problemas)
    )


def test_a_lista_de_segredos_liberados_e_esta_e_nenhuma_outra():
    """Liberar segredo é decisão, não descuido — então fica escrita aqui.

    Qualquer campo novo em `allow_fields` quebra este teste até alguém
    adicioná-lo à lista, o que força a decisão a aparecer no diff e a ser
    discutida em vez de passar despercebida.
    """
    liberados = {
        f"{e.entity_type}.{campo}"
        for e in registry.entries.values()
        for campo in e.allow_fields
    }
    assert liberados == {
        # Sem o hash, a loja recebe os usuários e ninguém entra no backend
        # local — o que apaga a razão de ele existir.
        "user.password",
    }, f"liberação de segredo não declarada neste teste: {liberados}"
