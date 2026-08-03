from __future__ import annotations

import argparse
import socket
from pathlib import Path


HOST = "127.0.0.1"
PORTA = 9002


def enviar_para_impressora(caminho: Path) -> None:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    if not caminho.is_file():
        raise ValueError("O caminho informado não é um arquivo.")

    conteudo = caminho.read_bytes()

    # Mesmo protocolo do LocalDeviceAgent (Flutter): conecta, escreve os
    # bytes brutos, dá flush e fecha — sem cabeçalho e sem ler resposta.
    with socket.create_connection((HOST, PORTA), timeout=10) as conexao:
        conexao.sendall(conteudo)
        conexao.shutdown(socket.SHUT_WR)

    print(f"{len(conteudo)} bytes enviados.")
    print("Veja o resultado em infra/simuladores/impressoes/<trabalho>/.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envia um arquivo para o simulador de impressora."
    )
    parser.add_argument(
        "arquivo",
        type=Path,
        help="Caminho do arquivo a enviar (texto ou binário).",
    )
    argumentos = parser.parse_args()

    try:
        enviar_para_impressora(argumentos.arquivo)
    except ConnectionRefusedError:
        print("A impressora virtual não está ligada.")
    except FileNotFoundError as erro:
        print(erro)
    except Exception as erro:
        print(f"Erro: {erro}")


if __name__ == "__main__":
    main()
