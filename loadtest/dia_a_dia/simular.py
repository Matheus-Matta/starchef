#!/usr/bin/env python
"""Um dia de salão contra o PAR nuvem + loja, com quedas de rede no meio.

    bash loadtest/scripts/start_sync_pair.sh
    python loadtest/dia_a_dia/simular.py --minutos 8

2 balanças lançando pesagens nas comandas, 5 garçons anotando consumo e 3
caixas fechando contas e recebendo — cada terminal com o desvio para a nuvem
do PDV real (`cliente.py`). Enquanto isso, `caos.py` derruba a loja, a nuvem e
a internet da loja. No fim, `conferir.py` diz se os dois bancos batem e se
algo foi duplicado ou perdido.

Nunca roda em CI nem contra produção: são containers descartáveis do par.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import atores  # noqa: E402
import caixa  # noqa: E402
import caos  # noqa: E402
import conferir  # noqa: E402
from cliente import Terminal  # noqa: E402
from registro import Registro, Salao  # noqa: E402

LOJA = "http://127.0.0.1:8022/api/v1"
NUVEM = "http://127.0.0.1:8021/api/v1"


def preparar():
    roteiro = (AQUI / "preparar.py").read_text(encoding="utf-8")
    feito = subprocess.run(
        ["docker", "exec", "-i", "syncpair-backend-cloud-1", "python", "manage.py", "shell"],
        input=roteiro, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    linhas = [linha for linha in feito.stdout.splitlines() if linha.startswith("{")]
    if not linhas:
        raise SystemExit(f"preparo falhou:\n{feito.stderr[-2000:]}")
    return json.loads(linhas[-1])


def esperar_na_loja(dados, limite=300):
    """O cenário nasce na nuvem: a loja só serve depois de recebê-lo."""
    alvo = len(dados["comandas"])
    consulta = (f"SELECT count(*) FROM restaurants_command WHERE restaurant_id='{dados['restaurante']}'"
                " AND number BETWEEN 501 AND 540")
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if int(conferir.sql("loja", consulta)[0][0]) >= alvo:
            usuarios = conferir.sql("loja", "SELECT count(*) FROM auth_user WHERE username LIKE 'sim.%'")
            if int(usuarios[0][0]) >= 8:
                return True
        time.sleep(5)
    return False


def _vigiado(registro, nome, alvo):
    """Um ator que quebra vira ACHADO, em vez de sumir calado da simulação."""
    def rodar(*args):
        try:
            alvo(*args)
        except Exception as erro:  # noqa: BLE001
            registro.anomalia(nome, f"o ator parou: {type(erro).__name__}: {erro} "
                                    f"{getattr(erro, 'corpo', '') or ''}"[:300])
    return rodar


def terminais(dados):
    senha = dados["senha"]
    pessoas = [(f"garcom{i + 1}", u) for i, u in enumerate(dados["garcons"])]
    pessoas += [(f"caixa{i + 1}", c["usuario"]) for i, c in enumerate(dados["caixas"])]
    pessoas += [("balanca1", "admin"), ("balanca2", "admin")]
    saida = {}
    for nome, usuario in pessoas:
        terminal = Terminal(nome, LOJA, NUVEM)
        terminal.entrar(usuario, "admin12345" if usuario == "admin" else senha)
        saida[nome] = terminal
    return saida


def main():
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--minutos", type=float, default=8)
    argumentos.add_argument("--sem-caos", action="store_true")
    opcoes = argumentos.parse_args()

    print("preparando o salão na nuvem...", flush=True)
    dados = preparar()
    print("esperando o salão descer para a loja...", flush=True)
    if not esperar_na_loja(dados):
        raise SystemExit("o cenário não chegou à loja em 5 minutos — a carga inicial travou")
    desde = datetime.now(timezone.utc).isoformat()
    registro, salao = Registro(), Salao(dados["comandas"])
    parar = threading.Event()
    todos = terminais(dados)
    contador = {"n": 0, "trava": threading.Lock()}

    fios = [threading.Thread(target=_vigiado(registro, f"garcom{i}", atores.garcom), args=(todos[f"garcom{i}"], dados, salao, registro, parar))
            for i in range(1, 6)]
    fios += [threading.Thread(target=_vigiado(registro, f"balanca{i}", atores.balanca), args=(todos[f"balanca{i}"], dados, salao, registro,
                                                            parar, dados["balancas"][i - 1], contador))
             for i in (1, 2)]
    fios += [threading.Thread(target=_vigiado(registro, f"caixa{i}", caixa.caixa), args=(todos[f"caixa{i}"], dados, salao, registro, parar,
                                                         dados["caixas"][i - 1]["estacao"]))
             for i in (1, 2, 3)]
    if not opcoes.sem_caos:
        fios.append(threading.Thread(target=caos.maestro, args=(registro, parar)))
    for fio in fios:
        fio.daemon = True
        fio.start()
    print(f"salão aberto por {opcoes.minutos} min...", flush=True)
    try:
        time.sleep(opcoes.minutos * 60)
    finally:
        parar.set()
        for fio in fios:
            fio.join(timeout=180)
        caos.restaurar()

    print("salão fechado. esperando a sincronização assentar...", flush=True)
    assentou, transito = conferir.esperar_assentar()
    from relatorio import escrever

    escrever(registro, todos, desde, assentou, transito, AQUI / "resultado")


if __name__ == "__main__":
    main()
