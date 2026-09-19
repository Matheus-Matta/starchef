"""RLS de verdade, contra um PostgreSQL de verdade.

Este arquivo INTEIRO é pulado no SQLite — testar política de linha em qualquer
outro banco seria testar o `skip`.

Para rodar:

    docker run -d --rm --name pg -e POSTGRES_PASSWORD=synctest \
      -e POSTGRES_USER=starchef -e POSTGRES_DB=starchef_sync \
      -p 55432:5432 postgres:16-alpine

    POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_PASSWORD=synctest \
      POSTGRES_DB=starchef_sync POSTGRES_USER=starchef \
      pytest --ds=config.settings.test_postgres apps/core/tests/test_rls_postgres.py

O que estes testes provam é o ponto inteiro do RLS: a consulta que ESQUECEU o
filtro de conta. Por isso todos usam `Restaurant.all_objects` — o manager que
NÃO passa pelo `TenantQuerySetMixin`. Se o isolamento dependesse do ORM, cada
um deles traria a linha da outra conta.
"""
import pytest
from django.db import connection

from apps.accounts.models import Account
from apps.core import rls
from apps.core.tenant import tenant_context
from apps.restaurants.models import Restaurant

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="Política de linha só existe no PostgreSQL.",
    ),
]


PAPEL_APP = "starchef_app_rls"


@pytest.fixture
def com_rls(settings):
    """Instala as políticas, ligA a proteção e assume um papel SEM superusuário.

    O `SET ROLE` não é detalhe de arrumação: o usuário que o pytest usa para
    criar o banco é o superusuário do contêiner, e **superusuário ignora toda
    política de linha** — `FORCE ROW LEVEL SECURITY` estende a política ao dono
    da tabela, não ao superusuário.

    Sem trocar de papel, todos os testes abaixo passariam a enxergar as duas
    contas e acusariam um defeito que não existe; pior, se a política estivesse
    de fato quebrada, eles não teriam como perceber. É o mesmo alçapão que
    `rls.papel_burla_rls()` denuncia na instalação.

    A ordem de desmontagem importa: soltar o papel e desligar a flag ANTES de
    remover as políticas, senão o próprio `uninstall` roda sob uma política que
    está tentando remover.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '" + PAPEL_APP + "') THEN "
            "CREATE ROLE " + PAPEL_APP + " NOSUPERUSER NOBYPASSRLS; END IF; END $$;"
        )
        cursor.execute("GRANT USAGE ON SCHEMA public TO " + PAPEL_APP)
        cursor.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO " + PAPEL_APP
        )
        cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO " + PAPEL_APP)

    settings.RLS_ENABLED = True
    rls.install(log=lambda _m: None)

    with connection.cursor() as cursor:
        cursor.execute("SET ROLE " + PAPEL_APP)
    yield
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    settings.RLS_ENABLED = False
    rls.uninstall(log=lambda _m: None)


def test_superusuario_e_denunciado(db):
    """O alçapão precisa ser DETECTÁVEL, não só documentado.

    Este teste roda como o superusuário do contêiner de propósito — é o caso em
    que instalar RLS não protege nada e tudo parece verde.
    """
    burla = rls.papel_burla_rls()
    assert burla is not None
    assert "SUPERUSER" in burla[1] or "BYPASSRLS" in burla[1]


@pytest.fixture
def duas_contas(db):
    """A montagem do cenário é trabalho de plataforma, e é declarada como tal.

    Precisa ser: esta fixture roda DEPOIS de `com_rls` (ordem dos argumentos do
    teste), então a política já está de pé e o papel já é o de aplicação. Criar
    a conta sem declarar o escopo esbarra no `WITH CHECK` da própria tabela
    `accounts_account` — que é o comportamento certo, e por isso a montagem
    abre o escopo em vez de o teste afrouxar a política.
    """
    with rls.escopo_da_plataforma("montagem do teste"):
        a = Account.objects.create(name="Conta A", slug="conta-a-rls", is_active=True)
        b = Account.objects.create(name="Conta B", slug="conta-b-rls", is_active=True)
        Restaurant.objects.create(account=a, legal_name="A LTDA", trade_name="A")
        Restaurant.objects.create(account=b, legal_name="B LTDA", trade_name="B")
    return a, b


def test_consulta_sem_filtro_so_ve_a_propria_conta(com_rls, duas_contas):
    """O teste que justifica o recurso inteiro."""
    conta_a, _conta_b = duas_contas

    with tenant_context(conta_a):
        # `all_objects` NÃO passa pelo mixin de tenant: é o "endpoint escrito
        # com pressa" que o RLS existe para cobrir.
        nomes = set(Restaurant.all_objects.values_list("trade_name", flat=True))

    assert nomes == {"A"}, "a consulta sem filtro alcançou a outra conta"


def test_sem_conta_na_sessao_nao_ve_nada(com_rls, duas_contas):
    """Fail-closed: quem não se identificou não recebe dado, e não recebe erro.

    Zero linha é o modo de falhar CERTO. Alguém percebe uma lista vazia no
    mesmo dia; ninguém percebe a linha da conta errada no meio de outras mil.
    """
    assert Restaurant.all_objects.count() == 0


def test_escopo_da_plataforma_atravessa_contas(com_rls, duas_contas):
    """O trabalho de fundo continua enxergando tudo — declaradamente."""
    with rls.escopo_da_plataforma("teste"):
        nomes = set(Restaurant.all_objects.values_list("trade_name", flat=True))
    assert nomes == {"A", "B"}

    # E o escopo FECHA ao sair do bloco: se vazasse, toda consulta seguinte na
    # mesma conexão continuaria vendo todas as contas — o pior dos dois mundos,
    # porque a política ficaria de pé sem proteger nada.
    assert Restaurant.all_objects.count() == 0


def test_gravar_para_outra_conta_e_recusado(com_rls, duas_contas):
    """`WITH CHECK`: a política também vale para escrita, não só para leitura."""
    from django.db import InternalError, ProgrammingError

    conta_a, conta_b = duas_contas
    with tenant_context(conta_a):
        with pytest.raises((InternalError, ProgrammingError)):
            Restaurant.all_objects.create(
                account=conta_b, legal_name="Intruso LTDA", trade_name="Intruso"
            )


def test_contexto_aninhado_devolve_a_conta_de_fora(com_rls, duas_contas):
    """Sair de um bloco aninhado restaura a conta no BANCO, não só no Python.

    Sem isso, o `ContextVar` voltaria para a conta de fora enquanto a sessão do
    PostgreSQL continuaria falando pela de dentro — e as duas discordando é
    pior que qualquer uma das duas sozinha.
    """
    conta_a, conta_b = duas_contas
    with tenant_context(conta_a):
        with tenant_context(conta_b):
            assert set(Restaurant.all_objects.values_list("trade_name", flat=True)) == {"B"}
        assert set(Restaurant.all_objects.values_list("trade_name", flat=True)) == {"A"}


def test_toda_tabela_de_conta_recebe_politica(com_rls):
    """Nenhuma tabela com `account` pode ficar de fora — nem a criada amanhã."""
    assert rls.faltando() == []
    assert len(rls.tabelas_multitenant()) >= 20


# ── o ovo-e-galinha: descobrir de quem é a sessão ───────────────────────────

def test_descobrir_o_tenant_precisa_de_escopo_proprio(com_rls, duas_contas):
    """A consulta que DESCOBRE a conta não pode estar filtrada pela conta.

    Este é o primeiro defeito que aparece ao ligar RLS, e foi o teste de carga
    que o encontrou: a execução não passou do preparo, com um 401 dizendo
    "usuário sem conta vinculada" — mensagem que culpa o cadastro do usuário,
    que estava perfeito.

    A mecânica é esta: para saber em nome de qual conta a sessão fala é preciso
    ler o `UserProfile`, e `accounts_userprofile` está protegida. Com a sessão
    ainda sem conta, a leitura devolve zero linha e o login conclui que o
    usuário não tem conta. Sem `rls.descobrindo_o_tenant()`, nem o login nem
    NENHUMA requisição passam.
    """
    from django.contrib.auth import get_user_model

    from apps.accounts.models import UserProfile
    from apps.accounts.role_catalog import ensure_system_roles

    User = get_user_model()
    conta_a, _conta_b = duas_contas

    with rls.escopo_da_plataforma("montagem do teste"):
        usuario = User.objects.create_user("operador-rls", "op@starchef.test", "senha-forte-123")
        UserProfile.objects.create(
            account=conta_a, user=usuario, role=ensure_system_roles(conta_a)["admin"]
        )

    # `all_objects` e não `objects`: o caminho real do login é
    # `getattr(user, "profile")`, um descritor reverso que NÃO passa pelo
    # manager de tenant. Usar `objects` aqui mediria o filtro do ORM (que
    # devolve vazio sem conta no ContextVar) em vez da política do banco — o
    # teste passaria pelo motivo errado, que é exatamente o que ele existe
    # para não fazer.
    assert UserProfile.all_objects.filter(user=usuario).count() == 0, (
        "se isto passar a devolver linha, a política deixou de valer"
    )

    # Com o escopo de descoberta, ele aparece — e é assim que o login resolve
    # a conta antes de ter uma para declarar.
    with rls.descobrindo_o_tenant():
        perfil = UserProfile.all_objects.filter(user=usuario).first()
        assert perfil is not None
        assert perfil.account_id == conta_a.id

    # E o escopo FECHA: a descoberta não pode deixar a sessão aberta para tudo.
    assert UserProfile.all_objects.filter(user=usuario).count() == 0
