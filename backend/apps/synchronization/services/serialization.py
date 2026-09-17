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
CAMPOS_PROIBIDOS = {"password", "token", "secret", "csc_token", "private_key", "api_key"}


def _encode(valor):
    if isinstance(valor, uuid.UUID):
        return str(valor)
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
