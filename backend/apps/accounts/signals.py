"""Sinais de inicialização do catálogo global de permissões."""

from apps.accounts.management.commands.sync_permissions import sync_permissions


def sync_permission_catalog(**_kwargs):
    """Mantém o catálogo disponível depois de toda execução de ``migrate``.

    O deploy de produção executa migrations ao iniciar o backend. Usar o sinal
    ``post_migrate`` garante que bancos novos e bancos já existentes recebam o
    catálogo sem depender de um comando operacional separado.
    """

    sync_permissions()
