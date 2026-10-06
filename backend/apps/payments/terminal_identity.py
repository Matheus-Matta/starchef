"""O id do PdvTerminal, igual na loja e na nuvem."""
import uuid

#: Fixo para sempre: trocar muda o id de todo terminal cadastrado daqui em diante.
_NAMESPACE = uuid.UUID("6f1c2a52-9d0e-4b8f-a3c4-5e7d9b1f0a26")


def terminal_id(account, installation_id):
    """Mesma instalação na mesma conta, mesmo id — em qualquer nó.

    Os dois servidores cadastram o terminal sozinhos: a loja quando o PDV abre
    o caixa, a nuvem quando ele recebe por ela com a loja fora. Com `uuid4`
    cada lado gerava o seu, o índice único (conta, instalação) recusava o do
    outro na sincronização, e a sessão de caixa que apontava para ele não
    aplicava — a abertura e o fechamento paravam de chegar.
    """
    return uuid.uuid5(_NAMESPACE, f"{account.pk}:{installation_id}")
