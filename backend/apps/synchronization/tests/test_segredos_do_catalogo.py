"""O que NUNCA pode viajar no payload — e o que pode, por decisão escrita.

Uma auditoria encontrou o certificado A1 da empresa
(`focus_certificate_base64`) viajando em cada evento e gravado na tabela de
eventos dos DOIS lados — enquanto a SENHA dele, no campo ao lado, era bloqueada
por conter "password". O inverso do que qualquer um esperaria.

Estes testes existem para que liberar um segredo seja sempre uma decisão que
aparece no diff, nunca um descuido do filtro por substring.
"""
import pytest

from apps.synchronization.services.registry import registry

pytestmark = pytest.mark.django_db


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
        # Mesmo motivo, e a exclusão anterior não protegia nada: este hash já
        # sai do servidor por `/restaurants/{id}/cash-auth/`, que é como o PDV
        # o guarda para verificar sem rede. Excluí-lo da sincronização só
        # deixava a LOJA sem ele — e é ela quem precisa autorizar sangria e
        # cancelamento quando a nuvem cai.
        "restaurant.cash_action_password",
        # ── Os três abaixo NÃO são segredo. ──────────────────────────────────
        #
        # Eles estão aqui porque `CAMPOS_PROIBIDOS` casa por SUBSTRING, e os
        # três contêm "certificate" no nome: uma data de validade, um CNPJ (que
        # já viaja em `restaurant.cnpj`) e o nome do titular. Nenhum revela a
        # chave privada nem a senha — essas continuam em `exclude_fields`.
        #
        # O buraco que isso fecha era silencioso, e é o pior formato:
        # `fiscal_config` DESCE da nuvem para a loja, então uma tela da loja
        # avisando "seu certificado vence em 10 dias" nunca receberia a data, e
        # ninguém saberia por quê.
        "fiscal_config.certificate_valid_until",
        "fiscal_config.certificate_cnpj",
        "fiscal_config.certificate_name",
    }, f"liberação de segredo não declarada neste teste: {liberados}"
