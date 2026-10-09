"""Captura automática das gravações que passam pelo ORM.

Signals **não pegam tudo** — `QuerySet.update`, `bulk_create`, `bulk_update` e
SQL direto passam por fora, e o plano diz isso com todas as letras (§11.2). O
desenho aqui assume esse limite em vez de fingir que ele não existe:

- o caminho normal (`.save()` / `.delete()` de um service) é capturado aqui;
- o caminho em massa é responsabilidade de quem escreve o service, chamando
  `outbox.record()` dentro da mesma transação;
- e a rede de segurança é a carga total do Admin, que reconstrói o destino a
  partir do estado real do banco quando alguma coisa escapou.

Uma falha na captura NUNCA derruba a gravação do dado de negócio. A venda
acontece; o evento, se falhar, vira log e a carga total conserta depois.
"""
import logging

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.synchronization.constants import Operation
from apps.synchronization.services import guard, outbox
from apps.synchronization.services.registry import registry

logger = logging.getLogger(__name__)


@receiver(post_save)
def capturar_gravacao(sender, instance, created, **kwargs):
    if not _sincronizavel(sender):
        return
    _registrar(instance, Operation.CREATE if created else Operation.UPDATE)


@receiver(m2m_changed)
def capturar_vinculo(sender, instance, action, reverse, model, pk_set, **kwargs):
    """Mudou só o VÍNCULO: o pai vira evento, com a versão adiantada.

    O vínculo viaja dentro do evento do pai (`m2m_fields`), e `.set()`/`.add()`
    não salvam o pai — a estação ganhava o operador na nuvem e a loja recusava
    abrir o caixa ("O operador não está vinculado"). A versão sobe junto
    porque, com a mesma versão, o outro lado ignora o evento.
    """
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not guard.is_enabled() or outbox.is_applying():
        return
    pais = [instance] if not reverse else list(model._base_manager.filter(pk__in=pk_set or []))
    for pai in pais:
        entrada = registry.for_model(type(pai))
        if entrada is not None and _vinculo_declarado(entrada, type(pai), sender):
            _adiantar_versao(pai)
            _registrar(pai, Operation.UPDATE)


def _vinculo_declarado(entrada, modelo, tabela_de_ligacao):
    return any(
        modelo._meta.get_field(nome).remote_field.through is tabela_de_ligacao
        for nome in entrada.m2m_fields
    )


def _adiantar_versao(pai):
    from django.utils import timezone

    if hasattr(pai, "updated_at"):
        agora = timezone.now()
        type(pai)._base_manager.filter(pk=pai.pk).update(updated_at=agora)
        pai.updated_at = agora


@receiver(post_delete)
def capturar_exclusao(sender, instance, **kwargs):
    if not _sincronizavel(sender):
        return
    _registrar(instance, Operation.DELETE)


def _sincronizavel(sender):
    if not guard.is_enabled() or outbox.is_applying():
        return False

    entrada = registry.for_model(sender)
    if entrada is None:
        return False

    # Durante o `migrate`, o Django entrega models HISTÓRICOS (do módulo
    # `__fake__`), reconstruídos a partir do estado das migrations. Eles têm o
    # mesmo app_label e o mesmo nome do model real, então casam com o catálogo
    # — e uma migration que popula permissões dispararia a captura de outbox.
    #
    # Isso quebrava o deploy do zero no PostgreSQL: a captura consulta a tabela
    # `SyncNode`, que naquele ponto do `migrate` ainda não existe. A consulta
    # falha, e no PostgreSQL uma consulta falha aborta a TRANSAÇÃO INTEIRA —
    # a migration seguinte morre com "current transaction is aborted".
    # (No SQLite isso passava batido: lá o erro não contamina a transação.)
    #
    # Comparar com a classe real resolve: model histórico nunca é ela.
    return entrada.model is sender


def _registrar(instance, operation):
    try:
        if operation != Operation.DELETE:
            _usuario_antes_do_perfil(instance)
        outbox.record(instance, operation=operation)
    except Exception:  # noqa: BLE001 — ver o docstring do módulo
        logger.exception(
            "sync: falha ao registrar evento de %s %s", type(instance).__name__, instance.pk
        )


def _usuario_antes_do_perfil(instance):
    """Gravou o PERFIL? O usuário dele vira evento junto — e antes dele.

    `auth.User` não tem conta: a outbox a descobre pelo perfil. Só que o
    usuário é gravado ANTES do perfil (cadastro do painel, `create_user`
    seguido do perfil), quando ainda não há conta nenhuma, e o evento dele era
    descartado em silêncio. O perfil chegava sozinho do outro lado, apontando
    para um usuário que não existia — e o garçom novo não entrava na loja.

    Antes do perfil porque é a ordem que o destino aplica: o perfil depende do
    usuário.
    """
    if type(instance).__name__ != "UserProfile" or not getattr(instance, "user_id", None):
        return
    usuario = getattr(instance, "user", None)
    if usuario is not None:
        outbox.record(usuario, operation=Operation.UPSERT)
