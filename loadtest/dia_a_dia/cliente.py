"""O cliente HTTP de um terminal simulado — com o desvio para a nuvem do PDV real.

As regras são as de `pdv_desktop/lib/core/network/` — a simulação só vale se o
terminal falso decide como o verdadeiro.

* Tenta a loja. Conexão recusada/derrubada ou 502/503/504 → confere o
  `/health/` da loja (prazo curto); fora, repete NA NUVEM com a mesma chave.
* Tempo esgotado numa ESCRITA não desvia: a loja pode ter gravado.
* Fiscal e caixa (`/invoices/`, `/cash-register/`) nunca desviam.
* Confirmada a queda, as próximas vão direto à nuvem pela janela do veredito
  (30 s, dobrando a cada recaída até 5 min).
* Escrita com tempo esgotado é repetida UMA vez com a MESMA chave, se a loja
  responde ao `/health/` (`_repetirSeAPerdeu`).
* 404 da loja num caminho com id que a nuvem criou há pouco vai para a nuvem
  (`afinidade_com_a_nuvem.dart`).
* Cada chamada gera uma `Idempotency-Key` nova — menos a repetição IDÊNTICA
  (mesma rota e corpo) de uma escrita que falhou na rede há menos de 2 min,
  que reaproveita a chave (`chaves_de_repeticao.dart`).
"""
import http.client
import json
import socket
import time
import urllib.error
import urllib.request
import uuid

from veredito import Veredito

NUNCA_DESVIAM = ("/invoices/", "/cash-register/", "/cash-registers/")
SEM_BACKEND = {502, 503, 504}


class Falha(Exception):
    def __init__(self, texto, *, status=None, conectividade=False, chegou=False, corpo=None):
        super().__init__(texto)
        self.status, self.conectividade, self.chegou, self.corpo = status, conectividade, chegou, corpo


class Terminal:
    def __init__(self, nome, loja, nuvem, *, timeout=8.0):
        self.nome, self.loja, self.nuvem, self.timeout = nome, loja, nuvem, timeout
        self.instalacao = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sim-{nome}"))
        self.token = None
        self.veredito = Veredito()
        self.origens = {"loja": 0, "nuvem": 0}
        self._da_nuvem = {}  # id -> quando a nuvem o devolveu
        self._repeticoes = {}  # assinatura -> (chave, quando falhou)

    def _lembrar(self, resposta):
        if isinstance(resposta, dict) and isinstance(resposta.get("id"), str):
            self._da_nuvem[resposta["id"]] = time.monotonic()

    def _nasceu_na_nuvem(self, caminho):
        agora = time.monotonic()
        return any(i in caminho for i, t in self._da_nuvem.items() if agora - t < 600)

    def _na_loja(self, metodo, caminho, corpo, chave):
        try:
            return self._http(self.loja, metodo, caminho, corpo, chave, self.timeout)
        except Falha as erro:
            if metodo == "GET" or not erro.chegou or not self._loja_responde():
                raise
            return self._http(self.loja, metodo, caminho, corpo, chave, self.timeout)

    # ── transporte ──────────────────────────────────────────────────────────
    def _http(self, base, metodo, caminho, corpo, chave, timeout):
        cabecalhos = {"Content-Type": "application/json", "X-Terminal-Id": self.instalacao,
                      "X-Terminal-Name": self.nome}
        if self.token:
            cabecalhos["Authorization"] = f"Bearer {self.token}"
        if chave:
            cabecalhos["Idempotency-Key"] = chave
        dados = json.dumps(corpo).encode() if corpo is not None else None
        pedido = urllib.request.Request(f"{base}{caminho}", data=dados, method=metodo,
                                        headers=cabecalhos)
        try:
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                texto = resposta.read().decode() or "{}"
                return json.loads(texto)
        except urllib.error.HTTPError as erro:
            texto = erro.read().decode(errors="replace")
            try:
                corpo_erro = json.loads(texto)
            except ValueError:
                corpo_erro = {"bruto": texto[:200]}
            raise Falha(f"HTTP {erro.code}", status=erro.code, corpo=corpo_erro) from None
        except (socket.timeout, TimeoutError):
            raise Falha("tempo esgotado", conectividade=True, chegou=True) from None
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException, OSError) as erro:
            motivo = getattr(erro, "reason", erro)
            if isinstance(motivo, (socket.timeout, TimeoutError)):
                raise Falha("tempo esgotado", conectividade=True, chegou=True) from None
            raise Falha(f"sem conexão: {motivo}", conectividade=True) from None

    def _loja_responde(self):
        raiz = self.loja.rsplit("/api/", 1)[0]
        try:
            with urllib.request.urlopen(f"{raiz}/health/", timeout=2) as resposta:
                return resposta.status < 500
        except Exception:  # noqa: BLE001 — qualquer falha é "não respondeu"
            return False

    def _desvia(self, metodo, caminho, falha):
        if caminho.startswith(NUNCA_DESVIAM):
            return False
        if not (falha.conectividade or falha.status in SEM_BACKEND):
            return False
        return metodo == "GET" or not falha.chegou

    # ── a chamada, como o PDV faz ───────────────────────────────────────────
    def chamar(self, metodo, caminho, corpo=None):
        if metodo == "GET":
            return self._chamar(metodo, caminho, corpo, None)
        assinatura = f"{metodo} {caminho} {json.dumps(corpo)}"
        guardada = self._repeticoes.get(assinatura)
        recente = guardada and time.monotonic() - guardada[1] < 120
        chave = guardada[0] if recente else str(uuid.uuid4())
        try:
            resultado = self._chamar(metodo, caminho, corpo, chave)
        except Falha as erro:
            if erro.conectividade:
                self._repeticoes[assinatura] = (chave, time.monotonic())
            raise
        self._repeticoes.pop(assinatura, None)
        return resultado

    def _chamar(self, metodo, caminho, corpo, chave):
        # Fechar comanda tenta a loja antes, mesmo na janela (cobrança em dobro).
        direto = not caminho.startswith(NUNCA_DESVIAM) and not caminho.endswith("/attach-commands/")
        if self.veredito.fora() and direto:
            try:
                resposta = self._http(self.nuvem, metodo, caminho, corpo, chave, self.timeout)
                self.origens["nuvem"] += 1
                self._lembrar(resposta)
                return resposta, "nuvem"
            except Falha as erro:
                if erro.status == 409 and "cobrar_na_loja" in str(erro.corpo):
                    self.veredito.respondeu()  # a loja está no ar: a janela acabou
                elif not erro.conectividade:
                    raise
        try:
            resposta = self._na_loja(metodo, caminho, corpo, chave)
            self.veredito.respondeu()
            self.origens["loja"] += 1
            return resposta, "loja"
        except Falha as erro:
            if erro.status == 404 and not caminho.startswith(NUNCA_DESVIAM)                     and self._nasceu_na_nuvem(caminho):
                resposta = self._http(self.nuvem, metodo, caminho, corpo, chave, self.timeout)
                self.origens["nuvem"] += 1
                return resposta, "nuvem"
            if not self._desvia(metodo, caminho, erro):
                raise
            if self._loja_responde():
                self.veredito.respondeu()
                raise
            self.veredito.caiu()
            try:
                resposta = self._http(self.nuvem, metodo, caminho, corpo, chave, self.timeout)
            except Falha as da_nuvem:
                raise (da_nuvem if da_nuvem.status == 409 else erro) from None
            self.origens["nuvem"] += 1
            self._lembrar(resposta)
            return resposta, "nuvem"

    def entrar(self, usuario, senha):
        resposta, _ = self.chamar("POST", "/auth/login/", {"username": usuario, "password": senha})
        self.token = resposta.get("access") or resposta.get("access_token") or resposta.get("token")
        if not self.token:
            raise Falha(f"login sem token: {list(resposta)}")
