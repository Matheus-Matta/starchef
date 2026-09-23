"""Toda rota que autentica por NÓ precisa ser isenta da middleware de tenant.

A middleware resolve conta a partir de JWT, e roda ANTES da view. Um token de
nó não é JWT: ela o apresenta ao `CookieJWTAuthentication`, ele é recusado, e
a resposta sai `401 Credencial inválida ou expirada` sem a view rodar nunca.

Foi o que aconteceu com `/api/v1/sync/fiscal/`. O sintoma enganava de duas
formas ao mesmo tempo:

* o código era `not_authenticated`, que parece "não mandei credencial" — mas o
  token estava lá e era válido;
* `/api/v1/sync/credentials/`, com o MESMO token e os MESMOS cabeçalhos,
  respondia 200. A diferença não estava na chamada: estava nesta lista.

Passei horas procurando no proxy, no cabeçalho e na imagem da nuvem. Este
teste existe para que a próxima rota de nó não repita isso: ele varre as rotas
de sincronização e cobra a isenção de todas as que usam autenticação de nó.
"""
import pytest

from apps.core.middleware import PUBLIC_URL_NAMES
from apps.synchronization.node_auth import NodeTokenAuthentication


def _rotas_de_no():
    """As rotas de sincronização que autenticam por nó, com o nome de cada uma."""
    from apps.synchronization import urls as sync_urls

    encontradas = []
    for padrao in sync_urls.urlpatterns:
        view = getattr(padrao, "callback", None)
        cls = getattr(view, "cls", None) or getattr(view, "view_class", None)
        if cls is None:
            continue
        if NodeTokenAuthentication in getattr(cls, "authentication_classes", []):
            encontradas.append((padrao.name, cls.__name__))
    return encontradas


def test_existe_rota_de_no_para_conferir():
    """Sem isto, o teste abaixo passaria vazio e não protegeria nada."""
    assert _rotas_de_no(), "nenhuma rota de nó encontrada — o varredor quebrou"


@pytest.mark.parametrize("nome,classe", _rotas_de_no())
def test_a_rota_de_no_e_isenta_da_middleware_de_tenant(nome, classe):
    assert nome in PUBLIC_URL_NAMES, (
        f"{classe} autentica por nó mas '{nome}' não está em PUBLIC_URL_NAMES: "
        "a middleware vai recusar com 401 antes de a view rodar, e o token de "
        "nó nunca será lido."
    )


def test_a_rota_do_rele_fiscal_esta_na_lista():
    """A que custou caro. Nomeada à parte para o motivo não se perder."""
    assert "sync-fiscal" in PUBLIC_URL_NAMES
