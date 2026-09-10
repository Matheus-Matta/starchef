"""
Cache do storefront e sua invalidação.

O endpoint público é o mais quente do sistema: todo cliente que abre o
cardápio no celular cai nele, e cada resposta é uma dúzia de queries com
produtos, categorias, horários e formas de pagamento. Ele é cacheado.

A invalidação usa um **contador de versão por restaurante** em vez de apagar
chave por chave. Duas razões concretas:

- o payload é cacheado em várias variantes (página X, página Y, hostname A) e
  nenhum backend de cache do Django oferece "apague tudo que casa com este
  prefixo" de forma portátil — no LocMem usado em teste/dev isso simplesmente
  não existe;
- incrementar um inteiro é atômico no Redis, então duas publicações
  simultâneas não deixam uma versão velha no ar.

Ao publicar uma página (ou mexer em produto, preço, categoria, horário,
domínio…) o contador sobe e **todas** as chaves antigas daquele restaurante
ficam inalcançáveis de uma vez, expirando sozinhas depois.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger("storefront.cache")

# Tempo de vida do payload público. Curto de propósito: a invalidação por
# versão cobre o caminho normal, e o TTL é só a rede de segurança para o caso
# de um sinal não disparar (ex.: alteração feita direto no banco).
PAYLOAD_TIMEOUT = getattr(settings, "STOREFRONT_CACHE_TIMEOUT", 300)
DOMAIN_TIMEOUT = getattr(settings, "STOREFRONT_DOMAIN_CACHE_TIMEOUT", 900)
VERSION_TIMEOUT = None  # o contador de versão não expira


def version_key(restaurant_id):
    return f"storefront:v:{restaurant_id}"


def storefront_version(restaurant_id):
    """Versão atual do cache daquele restaurante (cria em 1 se não existir)."""
    key = version_key(restaurant_id)
    version = cache.get(key)
    if version is None:
        cache.set(key, 1, VERSION_TIMEOUT)
        return 1
    return version


def payload_key(restaurant_id, variant=""):
    """`storefront:{restaurant}:{versão}:{variante}` — a versão está na chave."""
    return f"storefront:{restaurant_id}:{storefront_version(restaurant_id)}:{variant or 'default'}"


def domain_key(hostname):
    return f"storefront:domain:{str(hostname).strip().lower()}"


def get_payload(restaurant_id, variant=""):
    return cache.get(payload_key(restaurant_id, variant))


def set_payload(restaurant_id, variant, payload):
    cache.set(payload_key(restaurant_id, variant), payload, PAYLOAD_TIMEOUT)
    return payload


def get_domain(hostname):
    return cache.get(domain_key(hostname))


def set_domain(hostname, value):
    cache.set(domain_key(hostname), value, DOMAIN_TIMEOUT)
    return value


def invalidate_domain(hostname):
    if hostname:
        cache.delete(domain_key(hostname))


def invalidate_storefront(restaurant_id, reason=""):
    """Derruba todo o cache público de um restaurante.

    Chamada pelos sinais (``apps.storefront.signals``) sempre que muda algo que
    o cardápio público mostra: página publicada, produto, preço, categoria,
    disponibilidade, horário, tema, domínio.
    """
    if not restaurant_id:
        return None
    key = version_key(restaurant_id)
    try:
        version = cache.incr(key)
    except ValueError:
        # Chave ainda não existia: começar em 2 evita reaproveitar a versão 1,
        # que pode estar guardada em algum payload já servido.
        version = 2
        cache.set(key, version, VERSION_TIMEOUT)
    logger.debug("storefront cache invalidado", extra={"restaurant": str(restaurant_id), "reason": reason, "version": version})
    return version


def schedule_invalidation(restaurant_id, reason=""):
    """Invalida DEPOIS do commit.

    Invalidar no meio da transação abre uma janela ruim: a versão do cache sobe,
    uma leitura concorrente ainda enxerga os dados antigos (a transação não
    commitou) e grava esse conteúdo velho já sob a versão nova — a página fica
    desatualizada até o TTL, que é exatamente o que a invalidação existe para
    evitar. Fora de transação, `on_commit` executa na hora.
    """
    if not restaurant_id:
        return
    transaction.on_commit(lambda: invalidate_storefront(restaurant_id, reason=reason))


def invalidate_for_instance(instance, reason=""):
    """Invalida a partir de um objeto qualquer que tenha `restaurant_id`.

    Objetos compartilhados pela conta inteira (categoria/adicional com
    `restaurant = NULL`) não têm um restaurante só: nesse caso invalida todos
    os sites da conta, que é justamente quem pode estar exibindo o registro.
    """
    restaurant_id = getattr(instance, "restaurant_id", None)
    if restaurant_id:
        return schedule_invalidation(restaurant_id, reason=reason)

    account_id = getattr(instance, "account_id", None)
    if not account_id:
        return None
    from apps.storefront.models import MenuSite

    for site_restaurant_id in MenuSite.all_objects.filter(account_id=account_id).values_list("restaurant_id", flat=True):
        schedule_invalidation(site_restaurant_id, reason=reason)
    return None
