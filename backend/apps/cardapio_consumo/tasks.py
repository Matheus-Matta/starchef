from celery import shared_task


@shared_task(name="cardapio_consumo.executar_vencidos")
def executar_vencidos_task():
    """A baixa dos cardápios que venceram hoje e já passaram do horário."""
    from apps.cardapio_consumo.execucao import executar_vencidos

    return executar_vencidos()


@shared_task(name="cardapio_consumo.avisar_faltas_de_amanha")
def avisar_faltas_de_amanha_task():
    """Véspera: avisa no sino o que vai faltar para os cardápios de amanhã."""
    from apps.cardapio_consumo.previsao import avisar_faltas_de_amanha

    return avisar_faltas_de_amanha()
