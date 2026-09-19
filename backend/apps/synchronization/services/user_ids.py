"""A faixa de ids que a LOJA usa para usuário criado nela.

`auth.User` é a única das 52 entidades sincronizadas cujo id não é UUID — é um
inteiro sequencial, porque é a classe embutida do Django. E `apply._inserir`
grava com `model(pk=event.entity_id)`: a loja **adota o id da nuvem**.

Ela é obrigada a adotar. Todo payload carrega FK de usuário como id cru
(`opened_by_id: 15`, `created_by_id: 15`), e são 145 chaves estrangeiras
apontando para `User` no projeto. Se a loja numerasse por conta própria, todas
passariam a apontar para a pessoa errada.

O preço é que inserir com id explícito **não avança a sequência local**.
Medido no nó de produção: sequência em `last_value=1` enquanto os usuários
vindos da nuvem ocupavam 10 a 16. O nono usuário criado na loja receberia o
id 10 — que já era de outra pessoa.

E o modo de falhar é silencioso: `_inserir` pega o `IntegrityError` e cai no
caminho de ATUALIZAR, porque "id que já existe" normalmente significa "o mesmo
registro chegando de novo". Aqui significa duas pessoas diferentes com o mesmo
número, e uma sobrescreve a outra — hash de senha inclusive.

Separar a lógica aqui, e não deixá-la dentro da migration, é o que permite ao
`manage.py check` conferir a mesma coisa numa instalação que já estava no ar.
"""
from django.conf import settings

#: Primeiro id que a loja entrega a usuário criado nela.
#:
#: O teto do `int4` é 2.147.483.647, então sobra mais de um bilhão de ids de
#: cada lado da fronteira. A nuvem precisaria de um bilhão de usuários para
#: alcançar esta faixa.
PRIMEIRO_ID_LOCAL = 1_000_000_000


def e_no_local():
    return str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().lower() == "local"


def _sequencia(connection):
    """Nome da sequência de `auth_user.id`, ou None fora do PostgreSQL.

    Vem de `pg_get_serial_sequence` em vez do nome fixo `auth_user_id_seq`:
    custa uma consulta e não quebra se a tabela for renomeada um dia.
    """
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_serial_sequence('auth_user', 'id')")
        linha = cursor.fetchone()
    return linha[0] if linha and linha[0] else None


def valor_atual(connection):
    """Onde a sequência está agora. None quando não há como saber."""
    sequencia = _sequencia(connection)
    if not sequencia:
        return None
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT last_value FROM {sequencia}")
        linha = cursor.fetchone()
    return linha[0] if linha else None


def dentro_da_faixa_da_nuvem(connection):
    """Esta instalação ainda numera usuário onde a nuvem numera?"""
    if not e_no_local():
        return False
    atual = valor_atual(connection)
    return atual is not None and atual < PRIMEIRO_ID_LOCAL


def reservar_faixa(connection):
    """Empurra a sequência para a faixa da loja. Devolve True se mexeu.

    Só age numa instalação LOCAL: na nuvem a sequência é a autoridade e
    precisa continuar normal. Nunca RECUA — rodar de novo numa loja já
    reservada não desfaz nada.
    """
    if not e_no_local():
        return False
    sequencia = _sequencia(connection)
    if not sequencia:
        return False
    atual = valor_atual(connection)
    if atual is not None and atual >= PRIMEIRO_ID_LOCAL:
        return False
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER SEQUENCE {sequencia} RESTART WITH {PRIMEIRO_ID_LOCAL}")
    return True
