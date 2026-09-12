"""Valor de UM campo a partir do nome e do tipo que o OpenAPI declara.

Os nomes seguem convencao (preco, telefone, documento, cor...) e o gerador usa
essa convencao para mandar algo que um operador mandaria — com o `limpo=False`
produzindo o erro classico de digitacao de cada tipo.
"""
import datetime

from . import fakes
from .decimais import decimal_within

TEXT_HINTS = ("description", "notes", "note", "observ", "instructions", "reason", "address")


def string_value(field, meta, r, limpo=True):
    limit = meta.get("max_length") or 240
    fmt = meta.get("format")
    if meta.get("enum"):
        return r.choice(meta["enum"])
    if fmt == "date":
        return (datetime.date.today() - datetime.timedelta(days=r.randint(0, 900))).isoformat()
    if fmt == "time":
        return f"{r.randint(0, 23):02d}:{r.randint(0, 59):02d}" if limpo else "meia-noite"
    if fmt == "date-time":
        return (datetime.datetime.now() - datetime.timedelta(minutes=r.randint(0, 90000))).isoformat()
    if fmt == "uuid":
        return fakes.uuid4(r)
    if fmt == "email" or "email" in field:
        return fakes.email(r, limpo)
    if fmt == "uri" or "url" in field or "endpoint" in field:
        return f"https://exemplo.test/{fakes.codigo(r, 6).lower()}"
    if fmt == "decimal" or any(t in field for t in ("price", "amount", "total", "cost", "value", "fee")):
        return str(decimal_within(meta, fakes.dinheiro(r, limpo=limpo), limpo))
    if "phone" in field or "whatsapp" in field or "telefone" in field:
        return fakes.telefone(r, limpo)
    if "cnpj" in field:
        return fakes.cnpj(r, limpo)
    # `document_model` (max 2) tambem contem "document": so e CPF se couber um.
    if ("document" in field or "cpf" in field) and limit >= 11:
        return fakes.cpf(r, limpo)
    if "username" in field:
        return fakes.usuario(r, limpo)
    if any(t in field for t in TEXT_HINTS):
        return fakes.texto(r, limpo=limpo)[:limit]
    if "slug" in field or "handle" in field:
        return f"lt-{fakes.unico()}"  # unico na conta, e o sorteio repete entre fases
    if field == "host" or field.endswith("_ip"):
        return f"10.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}" if limpo else "impressora.local"
    if "ean" in field or "gtin" in field or "barcode" in field:
        return fakes.ean13(r) if limpo else fakes.codigo(r, 8)
    if "code" in field:
        return fakes.codigo(r, min(limit, 12))
    if field == "number":
        return str(10_000 + fakes.unico())[:limit]
    if "color" in field:
        return f"#{r.randint(0, 0xFFFFFF):06x}"
    if "name" in field or "title" in field or "label" in field:
        # Sufixo unico: setor, local de estoque e entregador sao unicos por
        # filial, e o sorteio de nomes e pequeno demais para nao repetir.
        base = fakes.nome_produto(r) if r.random() < 0.5 else fakes.pessoa(r)
        return f"{base} {fakes.unico() % 100_000}"[:limit]
    if "port" in field:
        return r.choice(["COM3", "/dev/ttyUSB0", "9100"])
    return fakes.texto(r, curto=True, limpo=limpo)[:limit] or "LT"


def number_value(field, meta, r, limpo=True):
    if any(t in field for t in ("price", "amount", "total", "cost", "value", "fee", "balance")):
        return fakes.dinheiro(r, limpo=limpo)
    if "weight" in field or "kg" in field:
        return fakes.peso(r, limpo)
    if "percent" in field or "rate" in field:
        return round(r.uniform(0, 25), 2)
    if "quantity" in field or "qty" in field or "stock" in field:
        return r.choice([1, 1, 2, 3, 5, 10, 0.5, 1.25])
    if field == "number":
        # Comanda/mesa: unico por restaurante. Passo de 1000 porque o servidor
        # numera sozinho com max+1 quando o campo e omitido — sequencia colada
        # ao contador colidiria com essa numeracao automatica.
        return 1_000 * (fakes.unico() % 2_000_000) + 500
    if meta.get("type") == "integer":
        return r.randint(1, 999)
    return round(r.uniform(1, 500), 2)
