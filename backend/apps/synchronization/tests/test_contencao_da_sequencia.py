"""A sequência do nó serializa a escrita do negócio? Medido, não suposto.

A pergunta de produção: com muitos caixas vendendo ao mesmo tempo, a captura de
eventos vira gargalo?

Onde mora o risco. Toda gravação sincronizada chama `outbox.record()` DENTRO da
transação do negócio, e ele chama `SyncNode.next_sequence()`:

    UPDATE synchronization_syncnode
       SET sequence_counter = sequence_counter + 1
     WHERE id = <o nó desta instalação>

É sempre a MESMA linha — a instalação tem uma só. No PostgreSQL esse UPDATE
pega lock exclusivo de linha, liberado só no COMMIT. Como o `record` roda
dentro da transação da venda, o lock fica preso até ela terminar.

Estes testes existem em PostgreSQL de propósito: o SQLite serializa a escrita
do banco inteiro, então ele "passaria" por um motivo que não tem nada a ver com
o que se quer medir — e esconderia o problema em vez de revelá-lo.

A verificação é por ORDEM, não por cronômetro: um teste que afirma
"demorou menos que X ms" falha no dia em que a máquina de CI estiver ocupada.
"""
import threading
import time

import pytest
from django.db import connection, transaction

from apps.synchronization.models import SyncNode

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="A contenção de linha é do PostgreSQL; o SQLite serializa tudo "
               "e passaria pelo motivo errado.",
    ),
]


def _fechar_conexao():
    """Cada thread precisa da própria conexão, e precisa devolvê-la."""
    connection.close()


def test_a_sequencia_bloqueia_a_transacao_seguinte(como_nuvem):
    """A prova: a segunda transação só avança quando a primeira commita.

    Se este teste passar, a serialização é REAL — e a consequência prática é
    que duas vendas simultâneas não são simultâneas: a segunda espera o commit
    da primeira, com o lock preso pelo resto daquela transação.
    """
    no = como_nuvem
    primeira_pegou = threading.Event()
    pode_commitar = threading.Event()
    ordem = []
    erros = []

    def segura_o_lock():
        try:
            with transaction.atomic():
                SyncNode.objects.get(pk=no.pk).next_sequence()
                ordem.append("A pegou")
                primeira_pegou.set()
                # Segura o lock enquanto a outra thread tenta.
                pode_commitar.wait(timeout=10)
            ordem.append("A commitou")
        except Exception as erro:  # noqa: BLE001
            erros.append(erro)
        finally:
            _fechar_conexao()

    def tenta_pegar():
        try:
            primeira_pegou.wait(timeout=10)
            # Dá tempo de a tentativa chegar ao banco e ficar esperando.
            time.sleep(0.2)
            pode_commitar.set()
            with transaction.atomic():
                SyncNode.objects.get(pk=no.pk).next_sequence()
                ordem.append("B pegou")
        except Exception as erro:  # noqa: BLE001
            erros.append(erro)
        finally:
            _fechar_conexao()

    a = threading.Thread(target=segura_o_lock)
    b = threading.Thread(target=tenta_pegar)
    a.start()
    b.start()
    a.join(timeout=20)
    b.join(timeout=20)

    assert not erros, f"erro nas threads: {erros}"
    assert ordem.index("A commitou") < ordem.index("B pegou"), (
        "B conseguiu a sequência antes de A commitar — o UPDATE não estaria "
        f"bloqueando. Ordem observada: {ordem}"
    )


def test_a_sequencia_nao_pula_nem_repete_sob_concorrencia(como_nuvem):
    """Serializar é lento, mas tem de ser CORRETO.

    Se o lock não existisse, duas transações leriam o mesmo contador e
    gravariam a mesma sequência — e `sync_unique_sequence_per_source` recusaria
    o segundo evento. Pior que lento: perda de evento.
    """
    no = como_nuvem
    sequencias = []
    trava = threading.Lock()
    erros = []
    quantas = 20

    def uma():
        try:
            with transaction.atomic():
                valor = SyncNode.objects.get(pk=no.pk).next_sequence()
            with trava:
                sequencias.append(valor)
        except Exception as erro:  # noqa: BLE001
            erros.append(erro)
        finally:
            _fechar_conexao()

    threads = [threading.Thread(target=uma) for _ in range(quantas)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not erros, f"erro nas threads: {erros}"
    assert len(sequencias) == quantas
    assert len(set(sequencias)) == quantas, (
        f"sequência repetida sob concorrência: {sorted(sequencias)}"
    )


def test_o_custo_da_serializacao_fica_registrado(como_nuvem, capsys):
    """Não reprova nada: MEDE, e deixa o número no relatório da suíte.

    Um teste que reprovasse por tempo falharia no dia em que a máquina de CI
    estivesse ocupada. O que importa aqui é o número ficar visível para quem
    for decidir se vale trocar o contador por algo sem linha quente.
    """
    no = como_nuvem
    amostras = 30

    inicio = time.perf_counter()
    for _ in range(amostras):
        with transaction.atomic():
            SyncNode.objects.get(pk=no.pk).next_sequence()
    sequencial = (time.perf_counter() - inicio) / amostras * 1000

    tempos = []
    trava = threading.Lock()

    def uma():
        try:
            comeco = time.perf_counter()
            with transaction.atomic():
                SyncNode.objects.get(pk=no.pk).next_sequence()
            with trava:
                tempos.append((time.perf_counter() - comeco) * 1000)
        finally:
            _fechar_conexao()

    threads = [threading.Thread(target=uma) for _ in range(amostras)]
    inicio = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    total_paralelo = time.perf_counter() - inicio

    with capsys.disabled():
        print(
            f"\n  [contenção da sequência] sequencial: {sequencial:.1f}ms por "
            f"incremento | {amostras} em paralelo: {total_paralelo * 1000:.0f}ms "
            f"no total, {max(tempos or [0]):.0f}ms o pior caso"
        )
    assert tempos, "nenhuma thread concluiu"
