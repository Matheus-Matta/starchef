"""As recusas que a API precisa que o CLIENTE reconheca.

Nao sao erros de preenchimento: em todas o corpo do pedido esta certo e o que
barra e o estado. Cada uma tem `status_code` e `default_code` proprios porque
o terminal decide o que oferecer a partir deles — tentar de novo, pedir uma
autorizacao, ou avisar quem administra a conta.
"""
from rest_framework import status
from rest_framework.exceptions import APIException


class LimitReached(APIException):
    """Limite de tenancy atingido (ex.: nº de usuários/restaurantes do plano).

    Usa 409 (conflito com o estado atual da conta) e um `default_code` próprio
    para que o frontend possa reconhecer o caso e exibir a mensagem personalizada.
    A mensagem é passada na criação da exceção e chega ao usuário via envelope.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Limite do plano atingido."
    default_code = "limit_reached"


class CancelBlocked(APIException):
    """O item não pode mais ser cancelado — e existe um caminho de saída.

    409, e não 400, pela mesma razão do `attach-commands`: o corpo do pedido
    está certo. O que barra é o ESTADO — o prato já foi para a produção há
    tempo demais, ou está numa coluna do KDS que bloqueia. Um 400 mandaria o
    PDV tratar como erro de preenchimento e reenviar o mesmo corpo para
    sempre.

    O `default_code` é o que permite ao terminal reconhecer o caso e oferecer
    a autorização do supervisor, em vez de mostrar a mensagem e parar ali.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Este item não pode mais ser cancelado."
    default_code = "cancel_blocked"


class MediaStorageUnavailable(APIException):
    """Não há como gravar a imagem agora (storage sem credencial ou fora do ar).

    503 e não 500: o servidor está de pé e o resto da API funciona — só o
    destino do arquivo é que não está disponível, e o cliente pode tentar de
    novo depois que a configuração for corrigida. O `default_code` permite ao
    frontend reconhecer o caso e orientar quem administra a conta, em vez de
    mostrar "erro inesperado" para um problema com solução conhecida.

    Levantada pelo `apps.core.storage` no momento da gravação — nunca no boot.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "O armazenamento de imagens não está disponível."
    default_code = "media_storage_unavailable"


class CouponRejected(APIException):
    """O cupom existe, mas quem esta pedindo nao tem direito a ele agora.

    422, e nao 400: o corpo esta certo e o codigo foi digitado certo. O que
    barra e uma REGRA — o CPF ja usou, o pedido nao alcanca o minimo, o cupom
    venceu ontem. Um 400 faria o PDV tratar como erro de digitacao e pedir o
    codigo de novo, quando o codigo nunca foi o problema.

    O `default_code` unico deixa o terminal distinguir "cupom invalido" (nao
    existe) de "cupom recusado" (existe e nao se aplica) — sao duas conversas
    diferentes com o cliente, que esta ouvindo.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Este cupom não pode ser aplicado a este pedido."
    default_code = "coupon_rejected"
