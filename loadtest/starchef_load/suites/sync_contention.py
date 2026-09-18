"""Contenção da sincronização: a fila serializa a escrita do negócio?

A pergunta que esta fase existe para responder: **em produção, com muita
venda ao mesmo tempo, a captura de eventos vira gargalo?**

Onde mora o risco, concretamente. Toda gravação sincronizada chama
`outbox.record()` DENTRO da transação do negócio, e ele chama
`SyncNode.next_sequence()`:

    UPDATE synchronization_syncnode
       SET sequence_counter = sequence_counter + 1
     WHERE id = <o nó desta instalação>

É sempre a MESMA linha — a instalação tem uma só. No PostgreSQL esse UPDATE
pega um lock exclusivo de linha que só é liberado no COMMIT. Como o `record`
roda dentro da transação da venda, o lock fica preso por todo o resto dela.

A consequência, se for real: duas vendas simultâneas não são simultâneas — a
segunda espera a primeira commitar. Com N caixas vendendo, a escrita
serializa em N, e a latência cresce em linha reta com a concorrência.

E na nuvem é pior por um fator que ninguém espera: `targets_for` devolve um
destino por loja ativa, então UMA gravação na nuvem com 10 lojas faz DEZ
incrementos na mesma linha, na mesma transação.

**Como medir sem instrumentar o banco.** A carga fala HTTP, não SQL — não dá
para ler `pg_locks` daqui. Mas serialização tem uma assinatura observável: a
latência mediana cresce proporcionalmente à concorrência enquanto a vazão fica
plana. Então esta fase mede a mesma gravação em concorrência 1 e em
concorrência N, e compara.

Um sistema que paraleliza bem mantém a mediana perto de estável e multiplica a
vazão. Um que serializa multiplica a mediana por ~N e mantém a vazão plana.
O número que a fase reporta é essa razão.
"""
import threading
import time

from ..workers import LoadRunner
from . import sync_phases

SUITE = "sync"

#: Abaixo disto, a diferença é ruído de rede e não serialização.
FATOR_ACEITAVEL = 2.5


def _medir(ctx, rng, *, workers, amostras, rotulo):
    """Roda `amostras` gravações em `workers` threads. Devolve as latências."""
    latencias = []
    trava = threading.Lock()

    def uma(_worker, indice):
        inicio = time.perf_counter()
        resposta = sync_phases.escrever_na_loja(ctx, SUITE, rng, indice)
        decorrido = (time.perf_counter() - inicio) * 1000
        if resposta is not None and resposta.status in (200, 201):
            with trava:
                latencias.append(decorrido)
        return resposta

    inicio = time.perf_counter()
    LoadRunner(workers=workers, count=amostras).run(uma)
    duracao = time.perf_counter() - inicio

    latencias.sort()
    if not latencias:
        return None
    return {
        "rotulo": rotulo,
        "workers": workers,
        "amostras": len(latencias),
        "p50": latencias[len(latencias) // 2],
        "p95": latencias[min(len(latencias) - 1, int(len(latencias) * 0.95))],
        "vazao": len(latencias) / duracao if duracao else 0,
    }


def fase_contencao(ctx):
    """Mede se a captura de eventos serializa a escrita do negócio."""
    ctx.log(f"[{SUITE}] fase extra — contenção da sequência sob concorrência")
    rng = ctx.rng(7777)

    # Com a sincronização DESLIGADA no alvo, `outbox.record` sai cedo e
    # `next_sequence` nunca é chamado. A medição continua válida como carga de
    # escrita, mas atribuí-la ao lock da sequência seria mentira — e relatório
    # que atribui a causa errada é pior que relatório nenhum.
    estado = sync_phases.status(ctx, SUITE, "loja", sync_phases.alvo_loja(ctx))
    ligada = bool(estado.get("enabled"))
    if not ligada:
        ctx.note(
            SUITE,
            "contenção: a sincronização está DESLIGADA neste alvo. Os números "
            "abaixo medem a escrita do backend (servidor, banco, pool) e NÃO o "
            "lock da sequência — para medir o lock, aponte para um alvo com "
            "SYNC_ENABLED=true e nó provisionado.",
        )

    # Amostras suficientes para a mediana ser estável, e poucas o bastante para
    # a fase não dominar a suíte inteira.
    amostras = max(20, min(120, ctx.config.count or 60))
    concorrentes = max(4, ctx.config.workers or 8)

    sozinho = _medir(ctx, rng, workers=1, amostras=amostras, rotulo="sequencial")
    if sozinho is None:
        ctx.note(SUITE, "contenção: nenhuma gravação passou; fase não conclui nada")
        return

    junto = _medir(ctx, rng, workers=concorrentes, amostras=amostras,
                   rotulo=f"{concorrentes} em paralelo")
    if junto is None:
        ctx.note(SUITE, "contenção: gravação concorrente falhou por inteiro")
        return

    for medida in (sozinho, junto):
        ctx.note(
            SUITE,
            f"contenção [{medida['rotulo']}]: p50={medida['p50']:.0f}ms "
            f"p95={medida['p95']:.0f}ms vazão={medida['vazao']:.1f}/s "
            f"({medida['amostras']} gravações)",
        )

    fator = junto["p50"] / sozinho["p50"] if sozinho["p50"] else 0
    ganho = junto["vazao"] / sozinho["vazao"] if sozinho["vazao"] else 0
    ctx.note(
        SUITE,
        f"contenção: com {concorrentes}x mais escritores, a mediana ficou "
        f"{fator:.1f}x maior e a vazão {ganho:.1f}x. Serialização perfeita daria "
        f"fator ~{concorrentes} e ganho ~1; paralelismo perfeito daria fator ~1 "
        f"e ganho ~{concorrentes}.",
    )

    ctx.check(
        SUITE,
        "a concorrência não serializa a escrita na fila",
        (not ligada) or fator < FATOR_ACEITAVEL or ganho > 1.5,
        f"mediana {fator:.1f}x maior com {concorrentes} escritores e vazão só "
        f"{ganho:.1f}x — assinatura de lock disputado. O suspeito é o UPDATE de "
        f"`sequence_counter` na linha do nó, que `outbox.record` executa dentro "
        f"da transação da venda (ver `SyncNode.next_sequence`).",
    )

    # Latência absoluta importa por si: uma venda que demora é uma fila no caixa.
    ctx.check(
        SUITE,
        "a gravação sob concorrência continua respondendo rápido",
        junto["p95"] < 2000,
        f"p95 de {junto['p95']:.0f}ms com {concorrentes} escritores simultâneos",
    )
