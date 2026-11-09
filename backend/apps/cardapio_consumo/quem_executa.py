"""Quem baixa o cardápio é a NUVEM; a loja só recebe (decisão do dono, 2026-11-09).

Loja e nuvem têm o mesmo cadastro (sincronização) e o mesmo agendador. Se os
dois baixassem, cada um criaria a sua saída — com ids diferentes, as duas
sincronizariam e o arroz sairia duas vezes. A regra antiga ("com loja, baixa a
loja") tinha uma janela: no dia em que a loja era matriculada, a nuvem já tinha
baixado de manhã e a loja baixava de novo antes de a execução da nuvem chegar.

Agora a loja ligada à nuvem não baixa nunca — nem pelo agendador, nem pelo
"Executar agora", nem manda o aviso de véspera. A saída feita na nuvem desce
pela sincronização como qualquer saída de estoque.

A loja SEM nuvem (`SYNC_ENABLED` desligado) continua baixando: não existe
outro servidor para fazer isso por ela.
"""
from django.conf import settings


class BaixaSoNaNuvem(Exception):
    """A loja ligada à nuvem pediu para baixar: quem baixa é a nuvem."""

    mensagem = ("A baixa do cardápio é feita pela nuvem; esta loja só recebe a saída pela "
                "sincronização. Use o painel da nuvem para executar agora.")

    def __init__(self):
        super().__init__(self.mensagem)


def este_servidor_executa():
    if not getattr(settings, "SYNC_ENABLED", False):
        return True
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower() != "local"


def garantir_que_este_servidor_executa():
    if not este_servidor_executa():
        raise BaixaSoNaNuvem()
