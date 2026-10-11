"""A API do comunicador: o backend chama, a ACBrLib executa, a resposta volta.

Sem estado e sem banco: a nota pendente mora no backend (docs/FISCAL_ACBRLIB.md).
Cada falha vira o `erro` que o backend classifica — é o que decide contingência
(`sem_comunicacao`), consulta (`incerto`), recusa e configuração.
"""
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from app import modelos, sefaz
from app.motor import criar_motor

app = FastAPI(title="StarChef — comunicador ACBrLib", version="1.0")
motor = criar_motor()

_ERROS = {
    sefaz.FalhaDeComunicacao: (503, "sem_comunicacao"),
    # 500 e não 504: um 504 o backend lê como "comunicador fora", e aqui o
    # envio PODE ter acontecido — o certo é consultar.
    sefaz.FalhaIncerta: (500, "incerto"),
    sefaz.DocumentoInvalido: (422, "documento_invalido"),
    sefaz.FalhaDeConfiguracao: (500, "configuracao"),
}


def autenticar(authorization: str = Header(default="")):
    esperado = os.environ.get("ACBRLIB_TOKEN", "")
    recebido = authorization.removeprefix("Bearer ").strip()
    if esperado and not secrets.compare_digest(recebido, esperado):
        raise HTTPException(status_code=401, detail="token inválido")


@app.exception_handler(sefaz.FalhaFiscal)
async def _falha(_request, erro):
    for classe, (status, codigo) in _ERROS.items():
        if isinstance(erro, classe):
            return JSONResponse({"erro": codigo, "mensagem": str(erro)}, status_code=status)
    return JSONResponse({"erro": "incerto", "mensagem": f"Falha inesperada: {erro}"}, status_code=500)


@app.get("/health")
def health():
    corpo = {"ok": motor.nome != "ausente", "motor": motor.nome, "lib": motor.nome == "acbrlib",
             "simulador": motor.nome == "simulador"}
    if motor.nome == "ausente":
        # 503 marca o container unhealthy no `docker ps` — visível, sem reiniciar.
        return JSONResponse({**corpo, "mensagem": motor.mensagem}, status_code=503)
    return corpo


@app.post("/v1/status-servico", dependencies=[Depends(autenticar)])
def status_servico(pedido: modelos.Contexto):
    return motor.status_servico(pedido)


@app.post("/v1/nfe/emitir", dependencies=[Depends(autenticar)])
def emitir(pedido: modelos.Emitir):
    return motor.emitir(pedido)


@app.post("/v1/nfe/transmitir", dependencies=[Depends(autenticar)])
def transmitir(pedido: modelos.Transmitir):
    return motor.transmitir(pedido)


@app.post("/v1/nfe/consultar", dependencies=[Depends(autenticar)])
def consultar(pedido: modelos.Consultar):
    return motor.consultar(pedido)


@app.post("/v1/nfe/cancelar", dependencies=[Depends(autenticar)])
def cancelar(pedido: modelos.Cancelar):
    return motor.cancelar(pedido)


if motor.nome == "simulador":
    @app.post("/_simulador/modo", dependencies=[Depends(autenticar)])
    def modo_do_simulador(corpo: dict):
        """Só no simulador: o teste de ponta a ponta troca o "estado da SEFAZ"."""
        os.environ["ACBR_SIMULAR_SEFAZ"] = str(corpo.get("modo", "online"))
        return {"modo": os.environ["ACBR_SIMULAR_SEFAZ"]}
