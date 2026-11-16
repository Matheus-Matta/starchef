"""Varredura de TODAS as rotas da API com entrada inválida (não é teste de CI).

Para cada rota: parâmetros de listagem estragados (paginação, ordenação,
busca, cada filtro com lixo), detalhe com id inexistente ou malformado, e
corpos inválidos em POST/PATCH (cada campo do serializer com um tipo errado).
Toda resposta 5xx entra no relatório com a exceção e a linha do projeto onde
ela nasceu; toda resposta acima de 1 s entra como lenta.

    pytest -s -p no:cacheprovider apps/core/tests/bench_varredura_da_api.py

Rede de saída bloqueada: SEFAZ, Focus e afins viram "rede fora" — é um dos
erros que a varredura quer ver tratado.
"""
import collections
import io
import json
import logging
import re
import socket
import time
import uuid

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.tests.varredura_apoio import (
    LIXO_DE_LISTA,
    VALORES_RUINS,
    _campos_de_filtro,
    _campos_graváveis,
    _Coletor,
    _origem,
    _rotas,
)


@pytest.mark.django_db
def test_varredura(monkeypatch):
    from django.contrib.auth import get_user_model

    from apps.core.management.commands._demo_defaults import DEFAULT_USERNAME

    conectar = socket.socket.connect

    def so_local(self, endereco):
        host = endereco[0] if isinstance(endereco, tuple) else str(endereco)
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise OSError("rede de saída bloqueada na varredura")
        return conectar(self, endereco)

    monkeypatch.setattr(socket.socket, "connect", so_local)
    # O limite por hora da API barraria a varredura no meio (429): desligado aqui.
    from rest_framework.views import APIView

    monkeypatch.setattr(APIView, "check_throttles", lambda self, request: None)

    call_command("seed_demo", skip_tenant_2=True, stdout=io.StringIO())
    admin = get_user_model().objects.get(username=DEFAULT_USERNAME)
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}")

    coletor = _Coletor()
    for nome in ("api.errors", "django.request"):
        logging.getLogger(nome).addHandler(coletor)

    falhas = collections.OrderedDict()
    lentas = []
    total = 0

    def chamar(metodo, rota, rotulo, **kw):
        nonlocal total
        total += 1
        coletor.registros.clear()
        inicio = time.perf_counter()
        try:
            resposta = getattr(cliente, metodo)(rota, **kw)
            status = resposta.status_code
        except Exception:  # noqa: BLE001 — o test client relança o que a view não tratou
            import sys
            coletor.registros.append(sys.exc_info())
            status, resposta = 599, None
        ms = (time.perf_counter() - inicio) * 1000
        if ms > 1000:
            lentas.append((ms, metodo.upper(), rota, rotulo))
        if status >= 500:
            erro, onde = _origem(coletor.registros[0]) if coletor.registros else (f"HTTP {status}", "?")
            chave = (onde, erro.split(":")[0])
            falhas.setdefault(chave, []).append((metodo.upper(), rota, rotulo, erro))
        return resposta

    rotas = list(_rotas())
    ids_reais = {}
    for rota, callback in rotas:
        if "<" in rota:
            continue
        cls = getattr(callback, "cls", None)
        resposta = chamar("get", rota, "normal")
        if resposta is not None and resposta.status_code == 200:
            try:
                dados = resposta.json()
                linhas = dados.get("results", dados) if isinstance(dados, dict) else dados
                if isinstance(linhas, list) and linhas and isinstance(linhas[0], dict) and "id" in linhas[0]:
                    ids_reais[rota] = str(linhas[0]["id"])
            except (ValueError, AttributeError):
                pass
        for params in LIXO_DE_LISTA:
            chamar("get", rota, f"params {list(params)[0]}", data=params)
        for campo in _campos_de_filtro(cls) if cls else []:
            for valor in ("lixo", "-1", "2026-13-45", str(uuid.uuid4()), "a,b,c"):
                chamar("get", rota, f"filtro {campo}={valor[:10]}", data={campo: valor})
        if cls and "post" in getattr(cls, "http_method_names", []):
            chamar("post", rota, "corpo []", data=[], format="json")
            chamar("post", rota, "corpo texto", data="isto não é json", content_type="application/json")
            for valor in VALORES_RUINS:
                corpo = {campo: valor for campo in _campos_graváveis(cls)} or {"x": valor}
                chamar("post", rota, f"campos={str(valor)[:12]}", data=corpo, format="json")

    for rota, callback in rotas:
        if "<" not in rota:
            continue
        base = re.sub(r"<[^>]+>.*$", "", rota)
        resto = re.sub(r"^.*?<[^>]+>", "", rota)
        candidatos = {"inexistente": str(uuid.uuid4()), "nao-uuid": "nao-e-uuid", "inteiro": "123"}
        if base in ids_reais:
            candidatos["real"] = ids_reais[base]
        for rotulo, valor in candidatos.items():
            alvo = re.sub(r"<[^>]+>", valor, rota, count=1)
            if "<" in alvo:
                alvo = re.sub(r"<[^>]+>", str(uuid.uuid4()), alvo)
            chamar("get", alvo, f"id {rotulo}")
            if resto.strip("/"):  # ação (`/cancel/`, `/print/`...): POST com lixo
                for valor_ruim in ("lixo", None, [], {"a": 1}):
                    chamar("post", alvo, f"acao id {rotulo} corpo={str(valor_ruim)[:8]}",
                           data={"x": valor_ruim, "reason": valor_ruim, "status": valor_ruim,
                                 "amount": valor_ruim, "column": valor_ruim}, format="json")
            elif rotulo == "real":
                for valor_ruim in VALORES_RUINS[:6]:
                    cls = getattr(callback, "cls", None)
                    corpo = {c: valor_ruim for c in (_campos_graváveis(cls) if cls else [])} or {"x": valor_ruim}
                    chamar("patch", alvo, f"patch real campos={str(valor_ruim)[:10]}", data=corpo, format="json")

    print(f"\n[VARREDURA] {len(rotas)} rotas, {total} requisições, {len(falhas)} defeitos distintos (5xx)")
    for (onde, _tipo), casos in falhas.items():
        metodo, rota, rotulo, erro = casos[0]
        rotas_afetadas = sorted({c[1] for c in casos})
        print(f"\n[5xx] {erro}")
        print(f"      origem: {onde}")
        print(f"      exemplo: {metodo} {rota}  ({rotulo})  — {len(casos)} caso(s) em {len(rotas_afetadas)} rota(s)")
        for r in rotas_afetadas[:6]:
            print(f"        · {r}")
    print(f"\n[LENTAS >1s] {len(lentas)}")
    for ms, metodo, rota, rotulo in sorted(lentas, reverse=True)[:15]:
        print(f"      {ms:7.0f} ms  {metodo} {rota}  ({rotulo})")
    with open("varredura_api.json", "w", encoding="utf-8") as saida:
        json.dump({"falhas": [{"origem": k[0], "tipo": k[1], "casos": v} for k, v in falhas.items()],
                   "lentas": lentas}, saida, ensure_ascii=False, indent=1, default=str)
