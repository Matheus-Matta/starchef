"""Comanda automática: a balança escolhe a comanda, sem o cliente passar cartão.

Em vez de ler o cartão, a Balança Rápida lança na PRÓXIMA comanda livre, em
ordem crescente (1, 2, 3 ... 300, e volta ao 1). As três regras, todas aqui no
servidor — que é quem enxerga todas as balanças:

1. **Não pula número.** Pega a primeira comanda livre DEPOIS da última
   lançada; só passa por cima da que está ocupada. O último número só avança
   na mesma transação do lançamento: se a pesagem falhar (impressora, rede),
   tudo volta atrás e o número é oferecido de novo.
2. **Nunca duas pesagens no mesmo número.** A linha de `FilaDaComanda` do
   restaurante é travada (`select_for_update`) antes de escolher: duas balanças
   pesando juntas entram na fila uma de cada vez. E a comanda escolhida é
   travada e conferida DE NOVO depois da trava — o garçom pode ter anotado
   nela entre a consulta e o lock.
3. **Volta ao início.** Passou do maior número cadastrado, recomeça do menor.

"Livre" é a mesma regra do salão (`Command.em_uso`): sem anotação pendente e
sem pedido aberto.
"""
from django.utils import timezone

from apps.printers.models_fila import FilaDaComanda
from apps.restaurants.command_listing import anotar_estado


class SemComandaLivre(Exception):
    """Todas as comandas estão em uso. É estado, não entrada errada: vira 409."""


def _candidatas(restaurant, depois_de):
    """As livres na ordem da fila: as acima do último, depois as do começo."""
    from apps.restaurants.models import Command

    livres = list(
        anotar_estado(Command.objects.filter(restaurant=restaurant, is_active=True))
        .filter(pendentes=0, pedido_aberto=False)
        .order_by("number")
        .values_list("pk", "number")
    )
    return [c for c in livres if c[1] > depois_de] + [c for c in livres if c[1] <= depois_de]


def proxima_comanda_livre(scale):
    """Trava a fila, escolhe e devolve a comanda (travada). Chame dentro de `atomic`."""
    from apps.restaurants.models import Command

    FilaDaComanda.objects.get_or_create(restaurant_id=scale.restaurant_id)
    fila = FilaDaComanda.objects.select_for_update().get(restaurant_id=scale.restaurant_id)
    for pk, numero in _candidatas(scale.restaurant, fila.ultimo_numero):
        comanda = Command.objects.select_for_update().select_related("restaurant").get(pk=pk)
        # Relida DEPOIS do lock: conferir antes de travar não impede corrida.
        if comanda.em_uso:
            continue
        fila.ultimo_numero = numero
        fila.updated_at = timezone.now()
        fila.save(update_fields=["ultimo_numero", "updated_at"])
        return comanda
    raise SemComandaLivre("Nenhuma comanda livre para a comanda automática.")


def comanda_da_fila(scale, pesagem_id):
    """A comanda da fila — ou, no REENVIO da mesma pesagem, a que ela já usou.

    Sem olhar o reenvio primeiro, a mesma pesagem reenviada andaria a fila e
    cairia numa segunda comanda.
    """
    from apps.core import uuid_do_aparelho
    from apps.printers import pesagem_por_uuid

    ja_pesada = pesagem_por_uuid.ja_pesada(scale, uuid_do_aparelho.ler(pesagem_id, "pesagem"))
    if ja_pesada is not None:
        return ja_pesada.command_item.command
    return proxima_comanda_livre(scale)
