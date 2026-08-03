from __future__ import annotations

import time

import serial


# Outra ponta do par virtual em que o simulador escreve (veja
# PORTA_SERIAL_BALANCA em simulador_equipamentos.py).
PORTA = "COM4"
BAUD_RATE = 9600
DURACAO_SEGUNDOS = 6


def consultar_balanca() -> None:
    try:
        porta = serial.Serial(PORTA, baudrate=BAUD_RATE, timeout=1)
    except serial.SerialException as erro:
        print(f"Não foi possível abrir {PORTA}: {erro}")
        print(
            "Confira se o simulador está rodando e se o par de porta "
            "virtual está configurado."
        )
        return

    print(f"Ouvindo {PORTA} por {DURACAO_SEGUNDOS}s...")
    fim = time.monotonic() + DURACAO_SEGUNDOS
    recebido = bytearray()

    with porta:
        while time.monotonic() < fim:
            pedaco = porta.read(64)
            if pedaco:
                recebido.extend(pedaco)

    if not recebido:
        print("Nada chegou. Confira a porta e se o simulador está ligado.")
        return

    print(f"{len(recebido)} bytes recebidos:")
    print(recebido.decode("ascii", errors="replace"))


if __name__ == "__main__":
    consultar_balanca()
