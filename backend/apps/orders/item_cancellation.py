"""Quando um item JÁ NA PRODUÇÃO ainda pode ser cancelado.

São duas regras, e as duas dizem a mesma coisa por caminhos diferentes: o
prato já está sendo feito, e tirá-lo da conta não desfaz o insumo nem o tempo
do cozinheiro.

* **tempo** — `Restaurant.item_cancel_window_seconds` conta do despacho para
  frente. Vale para item de pedido E para anotação de comanda, porque as duas
  guardam `sent_to_kitchen_at` na mesma base.
* **coluna do KDS** — `KdsColumn.blocks_cancel`. Vale só para item de pedido,
  que é quem está no quadro; a anotação de comanda só entra no KDS depois de
  virar item do pedido, no caixa.

NÃO SE CONFUNDE COM A CARÊNCIA. `cancellation_grace_seconds` ATRASA o envio:
dentro dela nada chegou à cozinha, cancelar é de graça e não sai cupom de
cancelamento. Estas regras começam onde aquela termina.

As duas nascem desligadas (`0` e `False`). Uma regra nova que nasce ligada
tranca operação no dia do deploy, sem ninguém ter pedido.
"""
from django.core.exceptions import ValidationError
from django.utils import timezone


class CancelamentoBloqueado(ValidationError):
    """O item não pode mais ser cancelado sem autorização de quem responde.

    É `ValidationError` para as rotas continuarem devolvendo 400 com a
    mensagem, mas tem tipo próprio: quem chama precisa distinguir "o gesto é
    inválido" de "o gesto é válido e precisa de alguém que autorize" — só o
    segundo tem um caminho de saída.
    """


def _restaurante_do(item):
    """O restaurante que responde por este item.

    O próprio item guarda a chave, mas nem sempre: dependendo de por onde ele
    foi criado o campo pode vir vazio, e aí a regra sumiria em silêncio — o
    pior jeito de uma regra de dinheiro falhar, porque ninguém percebe que ela
    parou de valer. Por isso o item é só a primeira fonte: o pedido e a
    comanda sempre sabem de quem são.
    """
    restaurante = getattr(item, "restaurant", None)
    if restaurante is not None:
        return restaurante
    pedido = getattr(item, "order", None)
    if pedido is not None and getattr(pedido, "restaurant", None) is not None:
        return pedido.restaurant
    comanda = getattr(item, "command", None)
    return getattr(comanda, "restaurant", None)


def motivo_de_bloqueio(item):
    """Por que este item não pode ser cancelado agora, ou `None` se pode.

    A frase volta pronta para o operador: ela diz a regra que barrou e o que
    ele consegue fazer a respeito. "Não permitido" sozinho manda ele tentar de
    novo até desistir.
    """
    return _bloqueio_por_tempo(item) or _bloqueio_por_coluna(item)


def _bloqueio_por_tempo(item):
    restaurante = _restaurante_do(item)
    janela = int(getattr(restaurante, "item_cancel_window_seconds", 0) or 0)
    if janela <= 0:
        return None
    enviado = getattr(item, "sent_to_kitchen_at", None)
    if enviado is None:
        # Ainda não chegou à produção: quem manda aqui é a carência, não esta
        # regra. Cancelar continua de graça.
        return None
    decorrido = (timezone.now() - enviado).total_seconds()
    if decorrido <= janela:
        return None
    return (
        f"O prazo para cancelar este item terminou: ele foi para a produção há "
        f"{_em_minutos(decorrido)} e o limite do restaurante é "
        f"{_em_minutos(janela)}."
    )


def _bloqueio_por_coluna(item):
    """O item está parado numa coluna do KDS que barra cancelamento?

    Basta UMA. Um item pode estar em mais de uma estação ao mesmo tempo (o
    prato na chapa e a bebida no bar), e se a chapa já começou não importa que
    o bar ainda não tenha pegado: aquele insumo já foi.
    """
    posicoes = getattr(item, "kds_positions", None)
    if posicoes is None:
        return None  # anotação de comanda não entra no quadro
    bloqueada = (
        posicoes.select_related("column", "station")
        .filter(column__blocks_cancel=True)
        .first()
    )
    if bloqueada is None:
        return None
    return (
        f"Este item já está em '{bloqueada.column.name}' "
        f"({bloqueada.station.name}), e itens nessa coluna não podem ser "
        "cancelados."
    )


def _em_minutos(segundos):
    """Tempo como o operador fala, não como o banco guarda."""
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    minutos, resto = divmod(segundos, 60)
    if minutos < 60:
        return f"{minutos}min" if not resto else f"{minutos}min{resto:02d}s"
    horas, minutos = divmod(minutos, 60)
    return f"{horas}h{minutos:02d}min"


def assert_pode_cancelar(item, *, authorized=False):
    """Barra o cancelamento quando alguma regra fecha — e ninguém autorizou.

    `authorized` é a saída, e ela existe de propósito: o prato queimou, o
    cliente passou mal, o garçom lançou na mesa errada. Uma regra sem exceção
    vira uma regra que o salão aprende a contornar por fora — cancelando o
    pedido inteiro, ou não cobrando e acertando depois.

    Quem autoriza fica registrado por quem chama, junto do motivo.
    """
    if authorized:
        return None
    motivo = motivo_de_bloqueio(item)
    if motivo:
        raise CancelamentoBloqueado(
            f"{motivo} Um supervisor pode liberar informando a senha de "
            "operação do restaurante ou as credenciais dele."
        )
    return None
