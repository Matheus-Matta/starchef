"""As quedas, de verdade, nos containers do par.

| queda              | o que simula                          | como                          |
|--------------------|---------------------------------------|-------------------------------|
| loja_sem_rede      | o servidor da loja some da rede       | tira o backend da loja da rede|
| loja_reinicia      | o serviço da loja reinicia            | `docker restart`              |
| loja_oscila        | a loja instável, cai e volta          | 3x fora 4 s / dentro 6 s      |
| nuvem_fora         | a nuvem fora do ar                    | tira o backend da nuvem da rede|
| internet_da_loja   | a loja sem internet (só o sync cai)   | congela o `sync_worker`       |

Toda queda é desfeita no fim (`restaurar`), mesmo se a simulação parar no meio.
"""
import random
import subprocess
import time
from datetime import datetime

REDE = "starchef-syncpair"
CONTAINER = {
    "loja": "syncpair-backend-store-1",
    "nuvem": "syncpair-backend-cloud-1",
    "worker": "syncpair-sync_worker-1",
}
APELIDO = {"loja": "backend-store", "nuvem": "backend-cloud"}
QUEDAS = ["loja_sem_rede", "internet_da_loja", "loja_oscila", "nuvem_fora", "loja_reinicia"]


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def tirar_da_rede(alvo):
    docker("network", "disconnect", "-f", REDE, CONTAINER[alvo])


def por_na_rede(alvo):
    docker("network", "connect", "--alias", APELIDO[alvo], REDE, CONTAINER[alvo])


def restaurar():
    for alvo in ("loja", "nuvem"):
        por_na_rede(alvo)
    docker("unpause", CONTAINER["worker"])


def _esperar_saude(porta, limite=120):
    import urllib.request

    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/health/", timeout=2):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(2)
    return False


def _fora_por(desligar, ligar, segundos):
    desligar()
    time.sleep(segundos)
    ligar()


def provocar(queda, duracao):
    if queda == "loja_sem_rede":
        _fora_por(lambda: tirar_da_rede("loja"), lambda: por_na_rede("loja"), duracao)
    elif queda == "nuvem_fora":
        _fora_por(lambda: tirar_da_rede("nuvem"), lambda: por_na_rede("nuvem"), duracao)
    elif queda == "internet_da_loja":
        _fora_por(lambda: docker("pause", CONTAINER["worker"]),
                  lambda: docker("unpause", CONTAINER["worker"]), duracao)
    elif queda == "loja_oscila":
        for _ in range(3):
            _fora_por(lambda: tirar_da_rede("loja"), lambda: por_na_rede("loja"), 4)
            time.sleep(6)
    elif queda == "loja_reinicia":
        docker("restart", "-t", "2", CONTAINER["loja"])
        _esperar_saude(8022)


def maestro(registro, parar, *, intervalo=(25, 45), duracao=(15, 35)):
    """Uma queda de cada tipo, em ordem embaralhada, até a simulação acabar."""
    fila = []
    while not parar.wait(random.uniform(*intervalo)):
        if not fila:
            fila = random.sample(QUEDAS, len(QUEDAS))
        queda = fila.pop()
        segundos = random.uniform(*duracao)
        inicio = datetime.now().strftime("%H:%M:%S")
        provocar(queda, segundos)
        registro.anotar("eventos", {"queda": queda, "inicio": inicio,
                                    "fim": datetime.now().strftime("%H:%M:%S")})
