"""Agente local da balanca StarChef.

Roda no PC do caixa e faz duas coisas (cada uma em sua thread):

1. LEITURA: le o peso da balanca (serial/USB) e envia para a API. O PDV busca a
   ultima leitura via GET /api/v1/scales/{id}/latest-reading/.

2. IMPRESSAO: faz polling das notas de pesagem pendentes da impressora da balanca
   e as envia para a impressora termica (ESC/POS via rede) — ou imprime no console
   em modo --simulate. Ao terminar, marca o job como impresso na API.

Uso:
    pip install pyserial requests
    python scale_agent.py --api http://localhost:8001/api/v1 \
        --username caixa.maria --password ... \
        --scale-id <uuid da balanca> --port COM3 --baudrate 9600 \
        --printer-id <uuid da impressora> --printer-host 192.168.0.50 --printer-port 9100

Homologacao sem hardware:
    ...  --simulate            (gera pesos aleatorios)
    ...  --print-simulate      (imprime as notas no console em vez da termica)
"""
import argparse
import random
import re
import socket
import threading
import time

import requests

WEIGHT_RE = re.compile(r"(\d+[.,]?\d*)")

# Comandos ESC/POS basicos (inicializa e corta o papel).
ESC_INIT = b"\x1b\x40"
ESC_CUT = b"\x1d\x56\x00"


def parse_weight(raw: bytes) -> float | None:
    """Extrai kg do frame da balanca. Protocolos Toledo/Filizola/Urano enviam
    o peso em gramas ou kg dentro de um frame ASCII; ajuste o regex se necessario."""
    text = raw.decode("ascii", errors="ignore")
    match = WEIGHT_RE.search(text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if value > 500:  # balancas que reportam em gramas
        value = value / 1000.0
    return round(value, 3)


class Agent:
    def __init__(self, args):
        self.args = args
        self.session = requests.Session()
        self.token = None
        self.last_sent = None

    # ── Auth ────────────────────────────────────────────────────────────
    def login(self):
        res = requests.post(
            f"{self.args.api}/auth/login/",
            json={"username": self.args.username, "password": self.args.password},
            timeout=10,
        )
        res.raise_for_status()
        self.token = res.json()["access"]
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        print("[agente] autenticado")

    def _request(self, method, path, **kwargs):
        """Wrapper que reautentica uma vez em caso de 401."""
        res = self.session.request(method, f"{self.args.api}{path}", timeout=10, **kwargs)
        if res.status_code == 401:
            self.login()
            res = self.session.request(method, f"{self.args.api}{path}", timeout=10, **kwargs)
        return res

    # ── Leitura da balanca ──────────────────────────────────────────────
    def send(self, weight_kg: float, stable: bool = True):
        if self.last_sent == weight_kg:  # evita flood: so envia quando muda
            return
        res = self._request(
            "POST",
            "/scales/readings/",
            json={
                "scale": self.args.scale_id,
                "weight_kg": f"{weight_kg:.3f}",
                "tare_kg": f"{self.args.tare:.3f}",
                "is_stable": stable,
                "source": "agent",
            },
        )
        res.raise_for_status()
        self.last_sent = weight_kg
        print(f"[agente] peso enviado: {weight_kg:.3f} kg")

    def run_serial(self):
        import serial  # pyserial

        conn = serial.Serial(self.args.port, self.args.baudrate, timeout=2)
        print(f"[agente] lendo {self.args.port} @ {self.args.baudrate}")
        while True:
            raw = conn.readline()
            if not raw:
                continue
            weight = parse_weight(raw)
            if weight and weight > 0:
                self.send(weight)

    def run_simulate(self):
        print("[agente] leitura simulada: pesos aleatorios a cada 5s")
        while True:
            self.send(round(random.uniform(0.2, 1.2), 3))
            time.sleep(5)

    # ── Impressao das notas de pesagem ──────────────────────────────────
    def print_loop(self):
        """Faz polling das notas pendentes da impressora e as imprime."""
        print(f"[impressao] monitorando notas pendentes da impressora {self.args.printer_id}")
        while True:
            try:
                self._print_pending()
            except Exception as exc:  # nunca derruba o loop
                print(f"[impressao] erro no polling: {exc}")
            time.sleep(self.args.print_interval)

    def _print_pending(self):
        res = self._request(
            "GET",
            "/print-jobs/",
            params={"status": "pending", "job_type": "weigh_ticket", "printer": self.args.printer_id},
        )
        res.raise_for_status()
        data = res.json()
        jobs = data.get("results", data) if isinstance(data, dict) else data
        for job in jobs:
            self._print_one(job)

    def _print_one(self, job):
        text = (job.get("payload") or {}).get("text_content", "")
        try:
            self._send_to_printer(text)
            self._request("POST", f"/print-jobs/{job['id']}/mark-printed/")
            print(f"[impressao] nota {job['id'][:8]} impressa")
        except Exception as exc:
            self._request("POST", f"/print-jobs/{job['id']}/mark-failed/", json={"error": str(exc)})
            print(f"[impressao] falha na nota {job['id'][:8]}: {exc}")

    def _send_to_printer(self, text):
        payload = ESC_INIT + text.encode("cp850", errors="replace") + b"\n\n\n" + ESC_CUT
        if self.args.print_simulate or not self.args.printer_host:
            print("\n----- NOTA (simulada) -----\n" + text + "\n---------------------------\n")
            return
        # ESC/POS via rede (a maioria das termicas expoe uma porta TCP, ex.: 9100).
        with socket.create_connection((self.args.printer_host, self.args.printer_port), timeout=10) as sock:
            sock.sendall(payload)


def main():
    parser = argparse.ArgumentParser(description="Agente local da balanca StarChef")
    parser.add_argument("--api", required=True, help="Base da API, ex.: http://localhost:8001/api/v1")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--scale-id", required=True, help="UUID da balanca cadastrada em /scales/")
    # Leitura
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--tare", type=float, default=0.0, help="Tara fixa do prato em kg")
    parser.add_argument("--simulate", action="store_true", help="Gera pesos aleatorios sem balanca fisica")
    parser.add_argument("--no-read", action="store_true", help="Nao le a balanca (so imprime)")
    # Impressao
    parser.add_argument("--printer-id", help="UUID da impressora a monitorar (habilita a impressao)")
    parser.add_argument("--printer-host", help="IP/host da impressora ESC/POS (rede)")
    parser.add_argument("--printer-port", type=int, default=9100)
    parser.add_argument("--print-interval", type=float, default=2.0, help="Intervalo do polling de notas (s)")
    parser.add_argument("--print-simulate", action="store_true", help="Imprime as notas no console")
    args = parser.parse_args()

    agent = Agent(args)
    agent.login()

    threads = []
    if args.printer_id:
        threads.append(threading.Thread(target=agent.print_loop, daemon=True))
    if not args.no_read:
        threads.append(threading.Thread(target=agent.run_simulate if args.simulate else agent.run_serial, daemon=True))

    if not threads:
        parser.error("Nada a fazer: use leitura (padrao) e/ou --printer-id para impressao.")

    for thread in threads:
        thread.start()
    # Mantem o processo vivo enquanto as threads (daemon) trabalham.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[agente] encerrando.")


if __name__ == "__main__":
    main()
