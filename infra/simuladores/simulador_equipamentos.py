from __future__ import annotations

import io
import json
import logging
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import barcode as barcode_lib
from barcode.writer import ImageWriter
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import serial

# ============================================================
# CONFIGURAÇÕES
# ============================================================

HOST = "127.0.0.1"

PORTA_IMPRESSORA = 9002

# A leitura de balança no app é sempre serial (flutter_libserialport), nunca
# rede — por isso o simulador precisa escrever numa porta serial de verdade,
# não abrir um socket TCP. Use um par de porta virtual (com0com, Eterlogic
# Virtual Serial Port etc.): o simulador escreve em PORTA_SERIAL_BALANCA e o
# app é configurado para ler a outra ponta do par.
PORTA_SERIAL_BALANCA = "COM3"
BAUD_RATE_BALANCA = 9600
INTERVALO_TRANSMISSAO_SEGUNDOS = 1.0

PESO_FIXO_KG = 2.350

# Ancoradas na pasta do proprio script, nunca no diretorio de onde ele foi
# chamado: um caminho relativo aqui faz o resultado (e o log) ir parar em
# outro lugar dependendo de onde o comando roda, e o trabalho mais recente
# parece "sumido".
PASTA_BASE = Path(__file__).resolve().parent
PASTA_IMPRESSOES = PASTA_BASE / "impressoes"
PASTA_LOGS = PASTA_BASE / "logs"

TAMANHO_MAXIMO_ARQUIVO = 20 * 1024 * 1024  # 20 MB


# ============================================================
# PREPARAÇÃO DAS PASTAS E LOGS
# ============================================================

PASTA_IMPRESSOES.mkdir(parents=True, exist_ok=True)
PASTA_LOGS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            PASTA_LOGS / "equipamentos.log",
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("simulador")


# ============================================================
# SIMULADOR DE BALANÇA
# ============================================================
#
# `ScaleProtocol` (scale_protocol.dart) decodifica um quadro STX (0x02) +
# dígitos + ETX/LF/CR (0x03/0x0a/0x0d), e o protocolo "Genérico" — o padrão do
# app — extrai o último número do quadro. `SerialScaleReader` também pode
# escrever `weightRequest` (ENQ, 0x05) pedindo uma pesagem sob demanda; este
# simulador responde a isso e, independente disso, transmite em modo
# contínuo, cobrindo os dois jeitos que uma balança real se comporta.

def montar_quadro_peso(peso_kg: float) -> bytes:
    texto = f"{peso_kg:.3f}"
    return b"\x02" + texto.encode("ascii") + b"\x03"


def simular_balanca_serial() -> None:
    try:
        porta = serial.Serial(
            PORTA_SERIAL_BALANCA,
            baudrate=BAUD_RATE_BALANCA,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
        )
    except serial.SerialException as erro:
        logger.error(
            "Balança: não foi possível abrir %s: %s. Configure um par de "
            "porta serial virtual (com0com, Eterlogic Virtual Serial Port) "
            "e aponte o app para a outra ponta do par.",
            PORTA_SERIAL_BALANCA,
            erro,
        )
        return

    logger.info(
        "Balança virtual escrevendo em %s (%s baud). Configure o app na "
        "outra ponta do par de porta virtual.",
        PORTA_SERIAL_BALANCA,
        BAUD_RATE_BALANCA,
    )

    quadro = montar_quadro_peso(PESO_FIXO_KG)
    ultimo_envio = 0.0

    try:
        with porta:
            while True:
                pedido = porta.read(max(porta.in_waiting, 1))

                if pedido and 0x05 in pedido:
                    # ENQ: a balança está respondendo a um "pegar peso".
                    porta.write(quadro)
                    ultimo_envio = time.monotonic()
                    logger.info(
                        "Balança: pedido (ENQ) recebido, %.3f kg enviado.",
                        PESO_FIXO_KG,
                    )
                    continue

                agora = time.monotonic()

                if agora - ultimo_envio >= INTERVALO_TRANSMISSAO_SEGUNDOS:
                    porta.write(quadro)
                    ultimo_envio = agora

    except serial.SerialException as erro:
        logger.error(
            "Balança: erro na porta %s: %s",
            PORTA_SERIAL_BALANCA,
            erro,
        )


# ============================================================
# SIMULADOR DE IMPRESSORA
# ============================================================
#
# O app Flutter (LocalDeviceAgent.printForPrinter) fala ESC/POS puro sobre
# TCP: abre a conexão, escreve os bytes brutos de uma vez (sem cabeçalho, sem
# prefixo de tamanho), dá flush e fecha — igual a uma impressora térmica de
# rede de verdade na porta 9100. Ele nunca lê uma resposta de volta. Por isso
# este simulador só precisa ler até a conexão fechar e guardar o que chegou;
# o protocolo antigo de cabeçalho JSON + tamanho exato não corresponde a
# nenhum cliente real do projeto.

LARGURA_BOBINA_MM = 80.0


def interpretar_stream_escpos(dados: bytes) -> list[tuple[str, str]]:
    """Separa o stream ESC/POS em segmentos ("texto", ...) e ("barras", valor).

    Não é um interpretador ESC/POS genérico — reconhece só os comandos que o
    `LocalDeviceAgent` (rawTransportBytes/escPosCode128Bytes, em
    local_device_agent.dart) realmente emite: alinhamento, os parâmetros do
    código de barras Code128 e o corte de papel. Sem isso, esses bytes de
    controle sobram como texto quebrado na prévia (ex.: "aHhPwkI{B0012") —
    os bytes de comando somem, mas os bytes de parâmetro que por acaso caem
    na faixa imprimível do ASCII ficam, formando lixo visual.
    """
    segmentos: list[tuple[str, str]] = []
    buffer = bytearray()
    indice = 0
    total = len(dados)

    def descarregar_texto():
        if buffer:
            segmentos.append(("texto", bytes(buffer).decode("utf-8", errors="replace")))
            buffer.clear()

    while indice < total:
        byte = dados[indice]

        if byte == 0x1B and indice + 2 < total and dados[indice + 1] == 0x61:
            indice += 3  # ESC a n: alinhamento — não aparece na prévia.
            continue

        if byte == 0x1D and indice + 1 < total:
            comando = dados[indice + 1]
            if comando in (0x48, 0x68, 0x77) and indice + 2 < total:
                indice += 3  # GS H/h/w n: parâmetros do código de barras.
                continue
            if comando == 0x56 and indice + 2 < total:
                indice += 3  # GS V n: corte de papel.
                continue
            if comando == 0x6B and indice + 3 < total:
                # GS k m n d1..dn: código de barras. Extrai o valor pra
                # mostrar como texto legível e desenhar as barras de verdade,
                # em vez dos bytes crus do comando.
                tamanho = dados[indice + 3]
                inicio = indice + 4
                fim = inicio + tamanho
                bruto = dados[inicio:fim].decode("ascii", errors="replace")
                # "{B"/"{A"/"{C" no início seleciona o conjunto de caracteres
                # do Code128 — não faz parte do valor codificado de verdade.
                valor = bruto[2:] if bruto[:1] == "{" else bruto
                descarregar_texto()
                segmentos.append(("barras", valor))
                indice = fim
                continue

        buffer.append(byte)
        indice += 1

    descarregar_texto()
    return segmentos


def _sanitizar_para_pdf(texto: str) -> str:
    """Reduz o texto ao alfabeto que as fontes padrão do PDF suportam.

    O que sobra de `errors="replace"` na decodificação (U+FFFD) e qualquer
    caractere fora do Latin-1 travam a fonte Courier embutida; virar "?" é
    aceitável aqui porque isso já é só uma prévia visual, não o comprovante.
    """
    return texto.encode("latin-1", errors="replace").decode("latin-1")


def _imagem_code128(valor: str) -> bytes | None:
    """PNG do código de barras Code128, ou None se o valor for vazio/inválido."""
    if not valor:
        return None
    try:
        buffer = io.BytesIO()
        code128 = barcode_lib.get("code128", valor, writer=ImageWriter())
        code128.write(buffer, options={"write_text": False, "module_height": 12.0})
        return buffer.getvalue()
    except Exception:
        logger.warning("Impressora: falha ao gerar codigo de barras para %r.", valor)
        return None


def gerar_pdf_recibo(dados: bytes) -> bytes:
    """Renderiza o trabalho recebido como um PDF em largura de bobina térmica.

    Interpreta o alinhamento/corte/código de barras que o app realmente
    envia (ver `interpretar_stream_escpos`); o resto do ESC/POS (negrito,
    fontes alternativas etc.) ainda não é usado pelo app, então não precisa
    de suporte aqui.
    """
    pdf = FPDF(unit="mm", format=(LARGURA_BOBINA_MM, 297))
    pdf.set_margins(left=2, top=4, right=2)
    pdf.set_auto_page_break(auto=True, margin=4)
    pdf.add_page()
    # Courier do PDF é mais largo por caractere que a Font A real de uma
    # impressora térmica de 80mm — em 8pt as LARGURA_CUPOM (48) colunas não
    # cabem na largura útil e o fpdf2 quebra a linha sozinho, jogando o fim
    # dela (ex.: o valor de `_linha_valor`) para a linha de baixo. 7pt é o
    # maior tamanho que ainda cabe: 48 * 0.6 * 7pt ≈ 201.6pt, dentro dos
    # ~215pt úteis (80mm - 2×2mm de margem).
    TAMANHO_FONTE_CUPOM = 7
    ALTURA_LINHA_CUPOM = 3.2
    pdf.set_font("Courier", size=TAMANHO_FONTE_CUPOM)

    for tipo, conteudo in interpretar_stream_escpos(dados):
        if tipo == "barras":
            imagem = _imagem_code128(conteudo)
            largura_disponivel = pdf.epw
            if imagem:
                pdf.image(io.BytesIO(imagem), x=pdf.l_margin, w=largura_disponivel, h=12)
                pdf.ln(1)
            pdf.set_font("Courier", size=TAMANHO_FONTE_CUPOM)
            pdf.multi_cell(
                0,
                ALTURA_LINHA_CUPOM,
                _sanitizar_para_pdf(conteudo).center(32) if conteudo else " ",
                align="C",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
            continue

        linhas = conteudo.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for linha in linhas:
            # Bytes de controle residuais fora dos comandos reconhecidos
            # acima ainda podem sobrar; um recibo de verdade nao usa esses
            # codigos, entao remove-los aqui e seguro.
            limpa = "".join(c for c in linha if c == "\t" or c >= " ")
            pdf.multi_cell(
                0,
                ALTURA_LINHA_CUPOM,
                _sanitizar_para_pdf(limpa) or " ",
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )

    return bytes(pdf.output())


def atender_impressora(
    conexao: socket.socket,
    endereco: tuple[str, int],
) -> None:
    logger.info(
        "Impressora: cliente conectado de %s:%s",
        endereco[0],
        endereco[1],
    )

    try:
        conexao.settimeout(30)

        pedacos = bytearray()

        while len(pedacos) <= TAMANHO_MAXIMO_ARQUIVO:
            parte = conexao.recv(4096)

            if not parte:
                break

            pedacos.extend(parte)

        if not pedacos:
            logger.warning(
                "Impressora: conexão de %s:%s fechada sem enviar dados.",
                endereco[0],
                endereco[1],
            )
            return

        if len(pedacos) > TAMANHO_MAXIMO_ARQUIVO:
            raise ValueError("O trabalho ultrapassa o limite de 20 MB.")

        conteudo = bytes(pedacos)
        momento = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        pasta_trabalho = PASTA_IMPRESSOES / f"trabalho_{momento}"
        pasta_trabalho.mkdir(parents=True, exist_ok=True)

        arquivo_bruto = pasta_trabalho / "impressao.bin"
        arquivo_bruto.write_bytes(conteudo)

        # Separa texto e código de barras pelos mesmos comandos ESC/POS que o
        # LocalDeviceAgent gera, em vez de decodificar tudo como texto puro —
        # senão os bytes de comando viram lixo legível na prévia.
        segmentos = interpretar_stream_escpos(conteudo)
        texto_legivel = "".join(
            conteudo if tipo == "texto" else f"\n[CODIGO DE BARRAS CODE128: {conteudo}]\n"
            for tipo, conteudo in segmentos
        )
        arquivo_legivel = pasta_trabalho / "impressao.txt"
        arquivo_legivel.write_text(texto_legivel, encoding="utf-8")

        arquivo_pdf = pasta_trabalho / "impressao.pdf"
        arquivo_pdf.write_bytes(gerar_pdf_recibo(conteudo))

        relatorio = {
            "status": "impresso",
            "tamanho_bytes": len(conteudo),
            "ip_cliente": endereco[0],
            "porta_cliente": endereco[1],
            "data_hora": datetime.now().isoformat(timespec="seconds"),
        }

        (pasta_trabalho / "relatorio_impressao.json").write_text(
            json.dumps(relatorio, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

        logger.info(
            "Impressora: %s bytes recebidos de %s:%s e salvos em %s",
            len(conteudo),
            endereco[0],
            endereco[1],
            pasta_trabalho.resolve(),
        )

    except socket.timeout:
        logger.warning(
            "Impressora: conexão de %s:%s expirou sem enviar dados.",
            endereco[0],
            endereco[1],
        )

    except Exception as erro:
        logger.exception(
            "Erro no atendimento da impressora: %s",
            erro,
        )

    finally:
        conexao.close()

        logger.info(
            "Impressora: conexão encerrada com %s:%s",
            endereco[0],
            endereco[1],
        )


def iniciar_impressora() -> None:
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    servidor.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    servidor.bind((HOST, PORTA_IMPRESSORA))
    servidor.listen()

    logger.info(
        "Impressora virtual disponível em %s:%s",
        HOST,
        PORTA_IMPRESSORA,
    )

    while True:
        conexao, endereco = servidor.accept()

        thread = threading.Thread(
            target=atender_impressora,
            args=(conexao, endereco),
            daemon=True,
        )

        thread.start()


# ============================================================
# INICIALIZAÇÃO
# ============================================================

def main() -> None:
    logger.info("=" * 60)
    logger.info("INICIANDO SIMULADOR DE EQUIPAMENTOS")
    logger.info("=" * 60)

    thread_balanca = threading.Thread(
        target=simular_balanca_serial,
        daemon=True,
    )

    thread_impressora = threading.Thread(
        target=iniciar_impressora,
        daemon=True,
    )

    thread_balanca.start()
    thread_impressora.start()

    print()
    print("Simuladores iniciados:")
    print(
        f"  Balança:    porta serial {PORTA_SERIAL_BALANCA} "
        f"({BAUD_RATE_BALANCA} baud) — configure o app na outra ponta do par virtual"
    )
    print(
        f"  Impressora: {HOST}:{PORTA_IMPRESSORA}"
    )
    print()
    print("Pressione Ctrl+C para encerrar.")
    print()

    try:
        thread_balanca.join()
        thread_impressora.join()

    except KeyboardInterrupt:
        logger.info("Simuladores encerrados pelo usuário.")


if __name__ == "__main__":
    main()