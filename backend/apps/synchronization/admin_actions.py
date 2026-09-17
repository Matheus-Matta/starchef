"""Os botões do change form do SyncNode (§14.1) e a segurança deles (§14.2).

Todo botão aqui: aceita só POST, exige permissão específica, registra quem
clicou e de que IP, cria um SyncRun antes de enfileirar, enfileira só depois do
commit e volta na hora para o Admin. Nenhum deles faz trabalho pesado dentro
da requisição HTTP.
"""
import logging

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from apps.synchronization.constants import RunType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import bootstrap, guard, provisioning, recovery

logger = logging.getLogger(__name__)

PERMISSAO_CARGA = "synchronization.can_start_full_sync"
PERMISSAO_REVOGAR = "synchronization.can_revoke_node"


class NodeActionsMixin:
    change_form_template = "admin/synchronization/syncnode/change_form.html"

    def get_urls(self):
        proprias = [
            path("<uuid:node_id>/sync-essenciais/", self.admin_site.admin_view(self.acao_essenciais),
                 name="synchronization_syncnode_bootstrap"),
            path("<uuid:node_id>/sync-tudo/", self.admin_site.admin_view(self.acao_tudo),
                 name="synchronization_syncnode_full"),
            path("<uuid:node_id>/reprocessar/", self.admin_site.admin_view(self.acao_reprocessar),
                 name="synchronization_syncnode_retry"),
            path("<uuid:node_id>/descartar-fila/",
                 self.admin_site.admin_view(self.acao_descartar_fila),
                 name="synchronization_syncnode_discard"),
            path("<uuid:node_id>/revogar/", self.admin_site.admin_view(self.acao_revogar),
                 name="synchronization_syncnode_revoke"),
            path("<uuid:node_id>/testar/", self.admin_site.admin_view(self.acao_testar),
                 name="synchronization_syncnode_test"),
        ]
        return proprias + super().get_urls()

    # ── ações ───────────────────────────────────────────────────────────────
    @method_decorator(require_POST)
    def acao_essenciais(self, request, node_id):
        return self._iniciar_carga(request, node_id, RunType.BOOTSTRAP)

    @method_decorator(require_POST)
    def acao_tudo(self, request, node_id):
        return self._iniciar_carga(request, node_id, RunType.FULL)

    @method_decorator(require_POST)
    def acao_reprocessar(self, request, node_id):
        no = self._no(node_id)
        total = recovery.requeue(account_id=no.account_id, apenas_mortos=False)
        self._auditar(request, no, f"reprocessou {total} evento(s)")
        messages.success(request, f"{total} evento(s) devolvidos à fila.")
        return self._voltar(node_id)

    @method_decorator(require_POST)
    def acao_descartar_fila(self, request, node_id):
        """Apaga a fila de SAÍDA deste nó e libera uma carga nova.

        Existe para o caso em que a fila ficou apontando para o lugar errado —
        uma loja que rematriculou e passou a conectar por outro nó, por
        exemplo. Refazer a carga é mais limpo que reaproveitar eventos velhos:
        os novos saem do estado ATUAL do banco.

        Apaga SÓ o que é OUTBOUND. Um evento INBOUND é dado que a loja mandou e
        que esta nuvem ainda não aplicou — apagá-lo perderia venda, e nenhum
        botão de Admin pode fazer isso.
        """
        if not request.user.has_perm(PERMISSAO_CARGA):
            messages.error(request, "Você não tem permissão para descartar a fila.")
            return self._voltar(node_id)

        no = self._no(node_id)
        apagados, cancelados = recovery.discard_outbound(no)
        self._auditar(request, no, f"descartou {apagados} evento(s) de saída")
        messages.warning(
            request,
            f"{apagados} evento(s) de saída descartados e {cancelados} carga(s) "
            "encerrada(s). Nada que veio da loja foi tocado. Use "
            "“Sincronizar tudo” para gerar a fila de novo.",
        )
        return self._voltar(node_id)

    @method_decorator(require_POST)
    def acao_revogar(self, request, node_id):
        if not request.user.has_perm(PERMISSAO_REVOGAR):
            messages.error(request, "Você não tem permissão para revogar um nó.")
            return self._voltar(node_id)

        no = self._no(node_id)
        provisioning.revoke(no, motivo=f"Revogado por {request.user} no Admin.")
        self._auditar(request, no, "revogou o vínculo")
        messages.warning(
            request,
            "Vínculo revogado: a credencial parou de valer e a conexão foi encerrada. "
            "Os eventos pendentes continuam guardados.",
        )
        return self._voltar(node_id)

    @method_decorator(require_POST)
    def acao_testar(self, request, node_id):
        no = self._no(node_id)
        retrato = recovery.snapshot(node=no)
        messages.info(
            request,
            f"Nó {no.name}: status={no.status}, visto em {no.last_seen_at or 'nunca'}, "
            f"{retrato['nao_enviados']} a enviar, {retrato['mortos']} morto(s).",
        )
        return self._voltar(node_id)

    # ── auxiliares ──────────────────────────────────────────────────────────
    def _iniciar_carga(self, request, node_id, run_type):
        if not request.user.has_perm(PERMISSAO_CARGA):
            messages.error(request, "Você não tem permissão para iniciar uma carga.")
            return self._voltar(node_id)

        no = self._no(node_id)
        try:
            guard.ensure_enabled()
            run = bootstrap.start_run(
                target_node=no,
                run_type=run_type,
                user=request.user,
                ip=self._ip(request),
                reason=request.POST.get("reason", ""),
            )
        except bootstrap.BootstrapBusy as erro:
            messages.warning(request, str(erro))
            return self._voltar(node_id)
        except guard.SyncDisabled as erro:
            messages.error(request, str(erro))
            return self._voltar(node_id)

        # Só depois do commit: enfileirar antes deixaria a tarefa procurando um
        # SyncRun que a transação ainda não gravou.
        from apps.synchronization.tasks.bootstrap import run_bootstrap

        transaction.on_commit(lambda: run_bootstrap.delay(str(run.id)))
        self._auditar(request, no, f"iniciou carga {run_type} ({run.id})")
        messages.success(
            request,
            f"Carga {run.get_run_type_display()} enfileirada. Acompanhe o progresso em "
            "Cargas de sincronização.",
        )
        return self._voltar(node_id)

    def _no(self, node_id):
        return SyncNode.objects.select_related("account").get(pk=node_id)

    def _voltar(self, node_id):
        return HttpResponseRedirect(
            reverse("admin:synchronization_syncnode_change", args=[node_id])
        )

    def _ip(self, request):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        return encaminhado.split(",")[0].strip() or request.META.get("REMOTE_ADDR")

    def _auditar(self, request, no, acao):
        logger.info(
            "sync-admin: user=%s ip=%s node=%s account=%s acao=%s",
            request.user, self._ip(request), no.id, no.account_id, acao,
        )
