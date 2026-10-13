"""Prazo de validade das tarefas periódicas do beat.

O beat enfileira no relógio, esteja o worker em dia ou não. Sem `expires`,
cada tique atrasado espera a vez na fila — e com o worker lento (CPU sem
crédito, um processo preso) a fila só cresce: na nuvem chegou a 1.034 + 919 +
288 tiques velhos, e o worker passou a rodar sem parar tarefa vencida que não
achava nada para fazer, segurando a CPU em 300% e o painel em 1,5 s.

Uma periódica é idempotente por natureza (a próxima faz o que esta faria),
então o tique que não rodou até o seguinte não serve para nada: o Celery o
descarta ao recebê-lo.
"""


def com_prazo(agenda):
    """Dá a cada periódica de intervalo fixo um `expires` igual ao intervalo.

    Não sobrescreve um `expires` escrito à mão. `crontab` fica de fora: o
    intervalo dele não é um número.
    """
    for entrada in agenda.values():
        intervalo = entrada.get("schedule")
        if isinstance(intervalo, (int, float)):
            entrada.setdefault("options", {}).setdefault("expires", intervalo)
    return agenda
