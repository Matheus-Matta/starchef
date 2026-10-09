"""O número do evento sem travar linha nenhuma (PostgreSQL).

O número vinha de um `UPDATE` na linha do nó (`sequence_counter + 1`), e a trava
dessa linha durava até o fim da transação. Toda gravação que sincroniza passava
por ela — lançar na comanda, pesar, abrir o caixa, receber —, e com vários
terminais as transações se esperavam em círculo até o PostgreSQL derrubar uma
(`deadlock detected`, 500 no caixa). Achado pela simulação do dia a dia.

Uma SEQUENCE do banco entrega o número sem trava: `nextval` não espera a
transação de ninguém. O preço é que um número reservado por uma transação que
desfaz fica sem uso — e buraco não é problema: a fila anda por ESTADO
(`pending_outbound`), não por cursor contínuo, e o destino ordena pelo número.

No SQLite (testes) a escrita já é serializada pelo banco inteiro: não há
círculo possível, e o contador da linha continua valendo.
"""
from django.db import connection

NOME = "sync_event_sequence"


def disponivel():
    return connection.vendor == "postgresql"


def proxima():
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [NOME])
        return int(cursor.fetchone()[0])


def atual():
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT last_value FROM {NOME}")
        return int(cursor.fetchone()[0])


def garantir_acima_de(valor):
    """Põe a sequence à frente de `valor` (nunca para trás)."""
    if not valor:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT setval(%s, greatest(%s, (SELECT last_value FROM {NOME})))", [NOME, int(valor)]
        )


def contador_atual(origem):
    """O último número de evento reservado aqui (a sequence, no PostgreSQL)."""
    return atual() if disponivel() else origem.sequence_counter
