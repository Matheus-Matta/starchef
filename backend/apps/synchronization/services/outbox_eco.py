"""Não gerar eco ao aplicar um evento que veio do outro nó.

Aplicar um produto vindo da nuvem geraria um evento de volta para a nuvem, que
geraria outro de volta para a loja: o laço infinito que o §13.2 manda evitar.

Separado de `outbox.py` porque é outra pergunta: lá se decide o que vira
evento; aqui se decide QUANDO a captura fica desligada. `outbox` reexporta os
dois nomes, então quem já importava de lá não muda.
"""
import logging
import threading

from django.db import transaction

logger = logging.getLogger(__name__)


#: Enquanto ligado, nada do que este processo grava vira evento novo. É o
#: `SET LOCAL app.sync_apply = '1'` do plano, na versão que funciona também no
#: SQLite do desenvolvimento: uma flag por thread, ligada só durante o apply.
_estado = threading.local()


def is_applying():
    return getattr(_estado, "applying", False)


class applying_remote_event:
    """Context manager que desliga a captura durante a aplicação de um evento.

    Sem isso, aplicar um produto vindo da nuvem geraria um evento de volta para
    a nuvem, que geraria outro de volta para a loja: o laço infinito que o §13.2
    manda evitar.

    Desliga os DOIS caminhos de captura: a flag por thread (que os signals
    consultam) e, no PostgreSQL, a variável `app.sync_apply` da transação (que
    a trigger consulta). Desligar só um deixaria o laço vivo pelo outro.
    """

    def __enter__(self):
        self.anterior = is_applying()
        _estado.applying = True
        # `SET LOCAL` só tem efeito DENTRO de uma transação: em autocommit o
        # PostgreSQL o aceita, emite um aviso e não faz nada. Se quem chamou
        # não abriu transação, a supressão da trigger sumiria em silêncio — e o
        # sintoma seria um laço de eco, descoberto muito depois. Então o bloco
        # é garantido aqui, e não confiado a quem chama.
        self._transacao = None
        if not transaction.get_connection().in_atomic_block:
            self._transacao = transaction.atomic()
            self._transacao.__enter__()
        self._marcar_sessao()
        return self

    def __exit__(self, tipo, valor, traco):
        _estado.applying = self.anterior
        if self._transacao is not None:
            self._transacao.__exit__(tipo, valor, traco)
        return False

    def _marcar_sessao(self):
        """`SET LOCAL app.sync_apply = '1'`. Morre com a transação.

        Falhar aqui não pode abortar a aplicação: sem PostgreSQL não há
        trigger, e a flag por thread já cobre os signals.
        """
        try:
            from apps.synchronization.services import triggers

            triggers.mark_apply_session()
        except Exception:  # noqa: BLE001
            logger.debug("sync: não foi possível marcar app.sync_apply", exc_info=True)
