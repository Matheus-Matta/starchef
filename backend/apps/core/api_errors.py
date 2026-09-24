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
