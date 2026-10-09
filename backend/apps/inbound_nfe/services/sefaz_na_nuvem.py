"""Com a loja sincronizada, quem fala com a SEFAZ é a NUVEM.

A nota de entrada sincroniza nos dois sentidos (a loja é um clone). Se a loja
e a nuvem consultassem a SEFAZ cada uma por conta própria, a MESMA nota
nasceria duas vezes, com ids diferentes — e as duas cópias brigariam na chave
única pela chave de acesso. A manifestação seria enviada duas vezes.

Então a loja sincronizada não consulta nem manifesta: ela recebe da nuvem o
que a nuvem baixou. Instalação sem sincronização (ou a própria nuvem) segue
falando com a SEFAZ como sempre.
"""
from django.conf import settings


class SefazSoNaNuvem(RuntimeError):
    """A loja sincronizada tentou falar com a SEFAZ."""


def esta_instalacao_fala_com_a_sefaz():
    if not getattr(settings, "SYNC_ENABLED", False):
        return True
    tipo = str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower()
    return tipo != "local"


def exigir_que_fale_com_a_sefaz():
    if not esta_instalacao_fala_com_a_sefaz():
        raise SefazSoNaNuvem(
            "Nesta loja a SEFAZ é consultada pela nuvem: as notas de entrada "
            "chegam pela sincronização. Faça a consulta ou a manifestação no "
            "painel da nuvem."
        )
