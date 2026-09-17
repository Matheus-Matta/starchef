"""Entrar no /admin da LOJA antes de a carga trazer os usuários.

O ovo e a galinha que isto resolve: um backend de loja recém-instalado tem
banco vazio — zero usuários. Os usuários vêm da nuvem, na carga. Se algo der
errado na sincronização, não há ninguém para entrar no /admin e olhar o que
aconteceu, e a única saída é `createsuperuser` por dentro do container.

A credencial usada é a MESMA da matrícula (`SYNC_ENROLL_*`), que já está no
`.env` daquela máquina — não se cria segredo novo.

As quatro travas, e nenhuma delas é opcional:

1. **Só no nó LOCAL.** Na nuvem este backend devolve None sempre. É lá que
   moram os dados de todas as contas.
2. **Só em DEVELOPMENT.** A mesma regra do módulo inteiro (§3.2).
3. **Só com a sincronização ligada.** Sem ela, a loja não é uma loja
   sincronizada e não há por que abrir esta porta.
4. **Só se as duas variáveis existirem.** Sem credencial configurada não há
   comparação a fazer.

Falhando qualquer uma, o backend se comporta como se não existisse — quem
decide é o `ModelBackend` normal, com os usuários que vieram da nuvem.
"""
import hmac
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from apps.synchronization.constants import NodeType
from apps.synchronization.services import guard

logger = logging.getLogger(__name__)


class LocalConsoleBackend(BaseBackend):
    """Autentica no /admin da loja com a credencial de matrícula."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password or not self._liberado():
            return None

        esperado_usuario = getattr(settings, "SYNC_ENROLL_USERNAME", "") or ""
        esperada_senha = getattr(settings, "SYNC_ENROLL_PASSWORD", "") or ""
        if not esperado_usuario or not esperada_senha:
            return None

        # Comparação em tempo constante nas duas: um `==` aqui vaza a senha
        # caractere a caractere para quem medir o tempo de resposta.
        confere_usuario = hmac.compare_digest(str(username), esperado_usuario)
        confere_senha = hmac.compare_digest(str(password), esperada_senha)
        if not (confere_usuario and confere_senha):
            return None

        usuario = self._garantir_usuario(esperado_usuario)
        logger.warning(
            "sync: entrada no /admin da loja pela credencial de MATRICULA (%s). "
            "Este caminho só existe no nó local, em development.",
            esperado_usuario,
        )
        return usuario

    def get_user(self, user_id):
        Usuario = get_user_model()
        try:
            usuario = Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
        # A sessão só continua valendo enquanto as travas continuarem valendo.
        # Desligar a sincronização derruba quem entrou por aqui na próxima
        # requisição, em vez de deixar a sessão sobreviver à mudança.
        return usuario if self._liberado() else None

    # ── travas ───────────────────────────────────────────────────────────────
    def _liberado(self):
        if not guard.is_enabled() or not guard.environment_is_allowed():
            return False
        return guard.node_type() == NodeType.LOCAL

    def _garantir_usuario(self, nome):
        """O usuário local que representa esse acesso.

        Nasce com senha INUTILIZÁVEL de propósito: assim ele não vira uma
        segunda porta pelo `ModelBackend` — quem entra por este caminho entra
        sempre por aqui, sujeito às travas acima, e a senha real continua
        existindo só na env.
        """
        Usuario = get_user_model()
        usuario, criado = Usuario.objects.get_or_create(
            username=nome,
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if criado:
            usuario.set_unusable_password()
            usuario.save(update_fields=["password"])
            logger.warning("sync: usuário local '%s' criado para o /admin da loja", nome)
        elif not (usuario.is_staff and usuario.is_superuser and usuario.is_active):
            # Um usuário com o mesmo nome pode ter chegado da nuvem sem ser
            # staff. Não rebaixamos nem promovemos silenciosamente: quem veio
            # da sincronização manda, e o acesso é recusado.
            logger.warning(
                "sync: '%s' existe mas não é staff/superuser ativo — acesso recusado", nome
            )
            return None
        return usuario
