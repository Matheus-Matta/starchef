"""Serializa e materializa uma instância de model para o protocolo.

Genérico de propósito: um serializador DRF por entidade significaria manter 45
arquivos em sincronia com os dois lados. Aqui os campos concretos viram um
dicionário JSON e as chaves estrangeiras viram o UUID do alvo — que é o mesmo
nos dois bancos, por construção (§6: nada de ID sequencial como identidade).
"""
import datetime
import decimal
import uuid

from django.db import models
from django.db.models.fields.files import FieldFile

from apps.synchronization.constants import SCHEMA_VERSION

#: Campos que nunca viajam, em nenhuma entidade. Segredo, sessão ou derivado.
#:
#: A comparação é por SUBSTRING do nome, então `focus_token_production` é pego
#: por "token". É uma rede grosseira de propósito: ela precisa pegar o campo que
#: alguém criar amanhã sem lembrar desta lista.
#:
#: `certificate` entrou depois de uma auditoria constatar que
#: `focus_certificate_base64` — o certificado A1 da empresa — estava viajando
#: em cada evento e ficando gravado na tabela de eventos dos DOIS lados,
#: enquanto `focus_certificate_password`, ali do lado, era bloqueado por conter
#: "password". O inverso do que qualquer um esperaria.
CAMPOS_PROIBIDOS = {
    "password", "token", "secret", "csc_token", "private_key", "api_key",
    "certificate",
}

#: Teto de aninhamento ao limpar um JSON. Nenhum payload legítimo chega perto;
#: o limite existe para um documento montado de propósito não virar recursão
#: sem fim dentro do `json.dumps` que grava o evento.
MAX_PROFUNDIDADE_JSON = 24


def _limpar_segredos(valor, _profundidade=0):
    """Tira chaves proibidas de DENTRO de um JSON, recursivamente.

    `_campo_permitido` olha o nome do campo Django — e para ali. Um
    `JSONField` chamado `metadata` passa no filtro e leva junto tudo o que
    houver dentro dele, incluindo uma chave `token` devolvida pela maquininha
    e gravada sem ninguém reparar. O nome do campo estava limpo; o conteúdo
    não.

    É o caso do `payments.Payment.metadata`, que nasce de entrada do cliente:
    o PDV manda o dicionário e ele viaja inteiro para a nuvem. Hoje só há ali
    identificador de terminal e motivo de gerente, mas "hoje não tem" não é
    controle — controle é o segredo não conseguir passar nem se alguém puser.

    O teto de profundidade existe para um JSON aninhado de propósito não virar
    recursão sem fim na hora de gravar o evento.
    """
    if _profundidade > MAX_PROFUNDIDADE_JSON:
        return "[profundidade máxima excedida]"
    if isinstance(valor, dict):
        return {
            chave: _limpar_segredos(item, _profundidade + 1)
            for chave, item in valor.items()
            if _nome_limpo(str(chave))
        }
    if isinstance(valor, (list, tuple)):
        return [_limpar_segredos(item, _profundidade + 1) for item in valor]
    return valor


def _nome_limpo(nome):
    return not any(proibido in nome.lower() for proibido in CAMPOS_PROIBIDOS)


def _encode(valor):
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, (dict, list, tuple)):
        # JSONField: o conteúdo passa pelo mesmo crivo que o nome do campo.
        return _limpar_segredos(valor)
    if isinstance(valor, decimal.Decimal):
        # String, não float: `float(Decimal("0.1"))` muda o valor e um centavo
        # a menos no pagamento vira divergência de caixa na nuvem.
        return str(valor)
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return valor.isoformat()
    if isinstance(valor, (bytes, bytearray)):
        return valor.decode("utf-8", errors="replace")
    if isinstance(valor, models.Model):
        return str(valor.pk)
    if isinstance(valor, FieldFile):
        # Arquivo: viaja o NOME, nunca o conteúdo. O binário vai por HTTPS em
        # chunks (§16) — um `ImageFieldFile` dentro do JSONField explode o
        # `json.dumps` na hora de gravar o evento.
        return valor.name or ""
    return valor


def _campo_permitido(nome, entry):
    if nome in entry.exclude_fields:
        return False
    # A exclusão vence sempre; a liberação nominal vence o filtro por
    # substring. Ordem importa: um campo em `exclude_fields` NÃO volta a viajar
    # por estar em `allow_fields`.
    if nome in getattr(entry, "allow_fields", ()):
        return True
    return not any(proibido in nome for proibido in CAMPOS_PROIBIDOS)


def serialize(instance, entry):
    """Instância -> dicionário JSON pronto para o payload do evento."""
    dados = {}
    for campo in instance._meta.concrete_fields:
        nome = campo.name
        if not _campo_permitido(nome, entry):
            continue
        if campo.is_relation:
            dados[f"{nome}_id"] = _encode(getattr(instance, campo.attname))
        else:
            dados[nome] = _encode(getattr(instance, nome))

    for campo, chave in (entry.m2m_fields or {}).items():
        # Lista de chaves naturais, ordenada: assim dois lados com o mesmo
        # vínculo produzem o mesmo payload, e o checksum não muda à toa só
        # porque o banco devolveu em outra ordem.
        relacao = getattr(instance, campo, None)
        if relacao is None:
            continue
        dados[campo] = sorted(
            str(valor) for valor in relacao.values_list(chave, flat=True)
        )
    return dados


def entity_version(instance):
    """A versão do registro que viaja no evento.

    `sync_version` quando o model tem (o caminho explícito); senão o
    `updated_at` em microssegundos, que é monotônico o bastante para ordenar
    duas edições do mesmo registro. Sem nenhum dos dois, 1 — e a política de
    conflito do catálogo decide sozinha.
    """
    versao = getattr(instance, "sync_version", None)
    if versao:
        return int(versao)
    atualizado = getattr(instance, "updated_at", None)
    if atualizado:
        return int(atualizado.timestamp() * 1_000_000)
    return 1


def tem_fonte_de_versao(instance):
    """O model consegue dizer QUANDO foi alterado pela última vez?

    `entity_version` devolve 1 quando não há nem `sync_version` nem
    `updated_at`. Aí o número é uma constante, e comparar duas constantes não
    informa nada — mas o resolvedor de conflito tratava "igual" como "já
    apliquei, ignore".

    `auth.User` é hoje a única entidade nessa situação, e o efeito era grave:
    depois do primeiro apply, NENHUM evento de usuário voltava a ser aplicado.
    A nuvem podia mandar o hash da senha para sempre que a loja descartaria.
    """
    if instance is None:
        return False
    if getattr(instance, "sync_version", None):
        return True
    return getattr(instance, "updated_at", None) is not None


def build_payload(instance, entry, *, origin_node_id):
    """O payload completo de um evento de entidade."""
    return {
        "schema_version": SCHEMA_VERSION,
        "entity_type": entry.entity_type,
        "entity_id": str(instance.pk),
        "entity_version": entity_version(instance),
        "origin_node_id": str(origin_node_id),
        "fields": serialize(instance, entry),
    }


def _decode_para_campo(campo, valor):
    """Converte o valor do JSON de volta para o tipo que o campo espera."""
    if valor is None:
        return None
    if isinstance(campo, models.DecimalField):
        return decimal.Decimal(str(valor))
    if isinstance(campo, models.DateTimeField):
        return _parse_datetime(valor)
    if isinstance(campo, models.DateField):
        return datetime.date.fromisoformat(valor) if isinstance(valor, str) else valor
    if isinstance(campo, models.TimeField):
        return datetime.time.fromisoformat(valor) if isinstance(valor, str) else valor
    return valor


def _parse_datetime(valor):
    if not isinstance(valor, str):
        return valor
    from django.utils.dateparse import parse_datetime

    return parse_datetime(valor) or valor


def deserialize(model, fields):
    """Dicionário do payload -> kwargs prontos para `Model(**kwargs)`.

    Campos que o model local não conhece são DESCARTADOS em silêncio: é assim
    que uma nuvem mais nova consegue falar com uma loja que ainda não atualizou
    (§17, mudança aditiva primeiro).
    """
    por_nome = {}
    for campo in model._meta.concrete_fields:
        por_nome[campo.name] = campo
        por_nome[campo.attname] = campo

    kwargs = {}
    for nome, valor in fields.items():
        campo = por_nome.get(nome)
        if campo is None:
            continue
        destino = campo.attname if campo.is_relation else campo.name
        kwargs[destino] = _decode_para_campo(campo, valor)
    return kwargs
