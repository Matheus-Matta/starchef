"""Peças da varredura da API (`bench_varredura_da_api.py`): rotas, campos e coleta de erros."""
import logging
import re
import traceback

from django.urls import get_resolver
from django.urls.resolvers import URLResolver

PULAR = re.compile(r"auth/(logout|password|refresh|verify)|/ws/|health|webhook|stream|export.*download")
LIXO_DE_LISTA = [
    {"page_size": "-1"}, {"page_size": "abc"}, {"page_size": "999999999999"},
    {"page": "0"}, {"page": "abc"}, {"page": "99999"},
    {"ordering": "campo_que_nao_existe"}, {"ordering": "-__class__"},
    {"search": "\x00%' OR 1=1 --"}, {"search": "x" * 5000},
    {"limit": "-5", "offset": "-5"},
]
VALORES_RUINS = ["lixo", -1, 10 ** 30, [], {"a": {"b": [1]}}, None, "", "1e309", True, "NaN"]


class _Coletor(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.registros = []

    def emit(self, record):
        if record.exc_info:
            self.registros.append(record.exc_info)


def _origem(exc_info):
    tipo, valor, tb = exc_info
    frames = [f for f in traceback.extract_tb(tb) if "apps" in f.filename and "site-packages" not in f.filename]
    onde = f"{frames[-1].filename.split('backend')[-1]}:{frames[-1].lineno} {frames[-1].name}" if frames else "?"
    return f"{tipo.__name__}: {str(valor)[:140]}", onde


def _rotas():
    saida = []

    def andar(padroes, prefixo="", callback_pai=None):
        for p in padroes:
            if isinstance(p, URLResolver):
                andar(p.url_patterns, prefixo + str(p.pattern))
            else:
                saida.append((prefixo + str(p.pattern), p.callback))

    andar(get_resolver().url_patterns)
    vistas = set()
    for padrao, callback in saida:
        if not padrao.startswith("api/v1/") or "format" in padrao:
            continue
        # O router do DRF dá regex: `(?P<pk>[^/.]+)` vira `<pk>`.
        padrao = re.sub(r"\(\?P<(\w+)>[^)]*\)", r"<>", padrao)
        rota = "/" + padrao.replace("^", "").replace("$", "").replace("\\", "")
        if rota in vistas or PULAR.search(rota):
            continue
        vistas.add(rota)
        yield rota, callback


def _campos_de_filtro(cls):
    campos = set()
    fs = getattr(cls, "filterset_fields", None) or {}
    campos.update(fs if isinstance(fs, (list, tuple)) else fs.keys())
    fc = getattr(cls, "filterset_class", None)
    if fc is not None:
        try:
            campos.update(fc.base_filters.keys())
        except Exception:  # noqa: BLE001
            pass
    return sorted(campos)


def _campos_graváveis(cls):
    try:
        serializer = cls.serializer_class() if getattr(cls, "serializer_class", None) else None
    except Exception:  # noqa: BLE001
        return []
    if serializer is None:
        return []
    try:
        return [n for n, f in serializer.fields.items() if not f.read_only]
    except Exception:  # noqa: BLE001
        return []
