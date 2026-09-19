"""Row Level Security: o isolamento de conta imposto pelo BANCO, não pelo ORM.

Hoje quem separa as contas é o `TenantQuerySetMixin`. Ele funciona — e é
exatamente por isso que o risco não é visível: o isolamento depende de todo
`QuerySet` novo lembrar de passar por ele. Um endpoint escrito com pressa, um
comando de manutenção, uma task que consulta direto pelo `_base_manager`, e o
dado de uma conta aparece na tela de outra sem que nada acuse.

RLS inverte o ônus. A política vive na tabela: uma consulta que esqueceu o
filtro não devolve dado errado, devolve **nada**. O modo de falhar deixa de ser
vazamento silencioso e passa a ser lista vazia — que alguém percebe no mesmo
dia.

## Por que fica DESLIGADA por padrão

Ligar RLS não é só criar as políticas: é garantir que todo caminho que fala com
o banco diga em nome de quem está falando. A API diz (o `TenantMiddleware`
resolve a conta e `tenant.set_current_account` a empurra para a sessão do
PostgreSQL). Mas a nuvem tem trabalho legítimo que atravessa contas — o
despacho varre a fila de todas as lojas, as métricas contam tudo, o /admin
lista tudo. Com a política de pé e sem conta na sessão, esse trabalho passa a
enxergar zero linha.

Por isso existe `escopo_da_plataforma()`: um bloco explícito e fácil de
procurar, no mesmo espírito do `applying_remote_event()`. A regra prática é a
mesma: se você precisou abrir um, diga no código por quê.

## LIMITE CONHECIDO: a variável mora na CONEXÃO, e ela pode escapar

Medido sob carga, com RLS ligada: **uma escrita em ~500 falhou** com
`new row violates row-level security policy for table "stock_stockmovement"`.
O registro tinha conta válida — foi a SESSÃO do PostgreSQL que não sabia dela.

A causa é estrutural, não um descuido: `aplicar_conta` grava a variável na
conexão que o Django tem naquele instante. Sem `ATOMIC_REQUESTS`, a requisição
não é uma transação, e com o pool nativo (`POSTGRES_POOL=True`) somado ao ASGI
não há garantia de que a consulta seguinte use a MESMA conexão em que a
variável foi gravada. Quando escapa, a variável chega vazia, o `NULLIF` vira
NULL, a comparação não é verdadeira e o `WITH CHECK` recusa.

Falha FECHADA, que é a direção certa — recusa a escrita, não vaza dado de
outra conta. Mas é 500 na cara do operador, e por isso RLS **não está pronta
para produção** enquanto isto não for resolvido.

Os dois caminhos conhecidos, ambos fora do escopo de quem só liga a flag:

1. `ATOMIC_REQUESTS = True` mais `set_config(..., true)` (transacional): a
   variável passa a viver na transação, que por definição é uma conexão só.
   Custa uma transação por requisição no sistema inteiro.
2. Um wrapper de backend que reaplique a variável toda vez que uma conexão for
   adquirida do pool, em vez de uma vez por requisição.

## O que falta para isto ser hermético

Numa instalação endurecida, `escopo_da_plataforma()` deixaria de ser uma
variável de sessão e viraria um SEGUNDO usuário de banco, com `BYPASSRLS`,
usado só pelos processos de fundo — aí nem o código da API conseguiria abrir o
escopo, porque a conexão dele não teria o direito. Enquanto for variável de
sessão, o controle é disciplina apoiada por revisão, não impossibilidade.
Está escrito aqui para ninguém confundir os dois níveis.
"""
import logging
from contextlib import contextmanager

from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

POLITICA = "starchef_tenant"
CHAVE_CONTA = "app.current_account"
CHAVE_PLATAFORMA = "app.platform_scope"


def is_postgres():
    return connection.vendor == "postgresql"


def esta_ligada():
    """RLS só age quando explicitamente ligada E o banco a suporta."""
    return bool(getattr(settings, "RLS_ENABLED", False)) and is_postgres()


def tabelas_multitenant():
    """`(tabela, coluna_da_conta)` de tudo que pertence a uma conta.

    A coluna é descoberta, não listada à mão: uma tabela nova com `account`
    entra sozinha na próxima instalação. Uma lista fixa aqui envelheceria em
    silêncio, e o buraco seria justamente na tabela mais nova — a que ninguém
    ainda revisou.
    """
    achadas = []
    for model in django_apps.get_models():
        if model._meta.proxy or not model._meta.managed:
            continue
        tabela = model._meta.db_table
        if model._meta.label == "accounts.Account":
            achadas.append((tabela, "id"))
            continue
        for campo in model._meta.concrete_fields:
            if campo.name == "account" and campo.is_relation:
                achadas.append((tabela, campo.attname))
                break
    return sorted(set(achadas))


def _condicao(coluna):
    # `NULLIF(..., '')` porque `''::uuid` levanta erro: sem ele, uma sessão que
    # limpou a variável derrubaria a consulta em vez de não devolver linha.
    # E `current_setting(..., true)` devolve NULL quando a variável nunca foi
    # definida — a comparação vira NULL, que não é verdadeiro, então o padrão
    # de quem não se identificou é não ver nada. É o fail-closed do §5.
    return (
        "current_setting('" + CHAVE_PLATAFORMA + "', true) = '1' "
        'OR "' + coluna + "\" = NULLIF(current_setting('" + CHAVE_CONTA + "', true), '')::uuid"
    )


def _sql_politica(tabela, coluna):
    condicao = _condicao(coluna)
    return [
        'ALTER TABLE "' + tabela + '" ENABLE ROW LEVEL SECURITY',
        # FORCE inclui o DONO da tabela. Sem ele, o usuário que o Django usa
        # normalmente é o dono e a política não valeria justamente para quem
        # ela precisa valer.
        'ALTER TABLE "' + tabela + '" FORCE ROW LEVEL SECURITY',
        "DROP POLICY IF EXISTS " + POLITICA + ' ON "' + tabela + '"',
        "CREATE POLICY " + POLITICA + ' ON "' + tabela + '" FOR ALL '
        "USING (" + condicao + ") WITH CHECK (" + condicao + ")",
    ]


def install(*, log=logger.info):
    """(Re)cria as políticas. Idempotente: pode rodar em todo deploy."""
    if not is_postgres():
        log("rls: só existe no PostgreSQL; nada a fazer neste banco.")
        return 0

    total = 0
    with connection.cursor() as cursor:
        for tabela, coluna in tabelas_multitenant():
            for sql in _sql_politica(tabela, coluna):
                cursor.execute(sql)
            total += 1
            log("  política em " + tabela + " (" + coluna + ")")
    log("rls: " + str(total) + " tabela(s) protegida(s).")

    burla = papel_burla_rls()
    if burla:
        # Não é aviso de rodapé: sem isto, a instalação "deu certo" e a
        # proteção não existe. Ver `papel_burla_rls`.
        log(
            "rls: ATENÇÃO — o usuário '" + burla[0] + "' " + burla[1] + ". "
            "As políticas foram criadas mas NÃO valem para esta conexão. "
            "Crie um usuário de aplicação sem SUPERUSER e sem BYPASSRLS."
        )
    return total


def uninstall(*, log=logger.info):
    if not is_postgres():
        return 0
    total = 0
    with connection.cursor() as cursor:
        for tabela, _coluna in tabelas_multitenant():
            cursor.execute("DROP POLICY IF EXISTS " + POLITICA + ' ON "' + tabela + '"')
            cursor.execute('ALTER TABLE "' + tabela + '" NO FORCE ROW LEVEL SECURITY')
            cursor.execute('ALTER TABLE "' + tabela + '" DISABLE ROW LEVEL SECURITY')
            total += 1
    log("rls: " + str(total) + " tabela(s) liberada(s).")
    return total


def installed():
    """Tabelas que hoje têm a política. Vazio fora do PostgreSQL."""
    if not is_postgres():
        return set()
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_policies WHERE policyname = %s", [POLITICA])
        return {linha[0] for linha in cursor.fetchall()}


def papel_burla_rls():
    """`(nome, motivo)` se o usuário conectado IGNORA as políticas. Senão `None`.

    Este é o alçapão que torna RLS um teatro: `superuser` e `BYPASSRLS` passam
    por cima de qualquer política, e `FORCE ROW LEVEL SECURITY` **não** os
    alcança — ele só estende a política ao dono da tabela.

    O modo de falhar é o pior possível, porque é silencioso e parece sucesso:
    `install_rls` responde "48 tabelas protegidas", o `--status` mostra tudo
    verde, e nenhuma linha fica de fora de nenhuma consulta. Quem instalou vai
    embora convencido de que ligou a proteção.

    É por isso que este aviso aparece na instalação e no status, em vermelho:
    a única coisa pior que não ter RLS é achar que tem.
    """
    if not is_postgres():
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
        linha = cursor.fetchone()
    if linha is None:
        return None
    nome, super_usuario, bypass = linha
    if super_usuario:
        return (nome, "é SUPERUSER, e superusuário ignora toda política de linha")
    if bypass:
        return (nome, "tem BYPASSRLS, atributo que existe justamente para ignorar RLS")
    return None


def faltando():
    """Tabelas de conta SEM política. É o que o `--status` reclama."""
    if not is_postgres():
        return []
    existentes = installed()
    return [tabela for tabela, _ in tabelas_multitenant() if tabela not in existentes]


# ── quem está falando com o banco ───────────────────────────────────────────

def aplicar_conta(account):
    """Diz ao PostgreSQL em nome de qual conta esta sessão fala.

    Silenciosa quando RLS está desligada: o `tenant.py` chama isto em TODA
    troca de conta, e cobrar um banco PostgreSQL de quem roda os testes em
    SQLite quebraria a suíte inteira por uma proteção que nem está ligada.

    A variável é de SESSÃO, não de transação, porque aqui não existe
    `ATOMIC_REQUESTS`: a requisição não roda dentro de uma transação, e uma
    variável transacional evaporaria antes da primeira consulta. Quem devolve
    a conexão limpa ao pool é o `finally` do `TenantMiddleware`, que chama
    `clear_current_account()` em todo caminho de saída — inclusive no de erro.
    """
    if not esta_ligada():
        return False
    valor = "" if account is None else str(getattr(account, "pk", account) or "")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [CHAVE_CONTA, valor])
    return True


def limpar_conta():
    return aplicar_conta(None)


@contextmanager
def escopo_da_plataforma(motivo=""):
    """Trabalho que legitimamente atravessa contas, declarado como tal.

    Use em processo de fundo que precisa varrer todas as contas — o despacho
    da fila, as métricas, a limpeza por retenção. NÃO use para atender
    requisição: ali a conta é conhecida, e a política é justamente o que
    protege o endpoint que alguém escrever amanhã.
    """
    if not esta_ligada():
        yield
        return
    if motivo:
        logger.debug("rls: escopo de plataforma aberto (%s)", motivo)
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, '1', false)", [CHAVE_PLATAFORMA])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, '', false)", [CHAVE_PLATAFORMA])


def trabalho_de_plataforma(motivo=""):
    """Decorador para função que varre contas — tipicamente uma task Celery.

    Equivale a envolver o corpo inteiro em `escopo_da_plataforma()`, e existe
    para que a declaração fique visível na LINHA DE CIMA da função, onde quem
    lê a lista de tasks a vê sem abrir o corpo. Uma task de fundo que não
    carrega esta marca é, por definição, uma task que deveria estar falando em
    nome de uma conta só.
    """
    def decorador(funcao):
        import functools

        @functools.wraps(funcao)
        def embrulho(*args, **kwargs):
            with escopo_da_plataforma(motivo or funcao.__name__):
                return funcao(*args, **kwargs)

        return embrulho

    return decorador


@contextmanager
def descobrindo_o_tenant():
    """A consulta que DESCOBRE a conta não pode ser filtrada por conta.

    É o ovo-e-galinha do RLS, e o primeiro que aparece ao ligar a política:
    para saber em nome de qual conta esta sessão fala, é preciso ler o
    `UserProfile` do usuário — e `accounts_userprofile` está protegida. Sem
    conta na sessão a leitura devolve zero linha, o login responde "usuário sem
    conta vinculada" e ninguém entra no sistema.

    O erro é especialmente cruel porque a mensagem culpa o cadastro do usuário,
    que está perfeito. Foi assim que este caso apareceu: a carga com RLS ligada
    não passou do preparo, com um 401 falando de perfil.

    É um escopo de plataforma como outro qualquer, mas com nome próprio porque
    o motivo é diferente dos demais: não é trabalho que atravessa contas por
    natureza, é a pergunta "qual é a conta?" — que precede a resposta.
    """
    with escopo_da_plataforma("descoberta do tenant"):
        yield
