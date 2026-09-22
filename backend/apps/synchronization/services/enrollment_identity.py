"""A IDENTIDADE que a matrícula grava: a conta, o nó próprio e o par.

Fica separado do cliente de matrícula porque é o assunto mais delicado dela —
e o que já custou caro: a unicidade de `SyncNode` é `(pair_id, node_type)`, e
uma gravação que busque por `pk` quebra exatamente no caso para o qual a
rematrícula existe, que é o outro lado ter trocado de id.
"""
import logging
import uuid

from apps.synchronization.constants import NodeStatus
from apps.synchronization.models import SyncNode
from apps.synchronization.services import guard

logger = logging.getLogger(__name__)


def _garantir_conta(conta_id):
    """Cria um esqueleto da conta quando ela ainda não existe aqui.

    O ovo e a galinha da primeira instalação: o SyncNode aponta para a conta,
    mas a conta só chega como PRIMEIRO evento da carga — que por sua vez
    precisa do nó para ter destino. Sem este esqueleto, a matrícula falha com
    `FOREIGN KEY constraint failed` num banco vazio, que é justamente o único
    estado em que ela roda.

    O registro nasce inativo e sem nome real: o evento `account` da carga
    sobrescreve tudo em seguida, com os dados verdadeiros. Inativo de propósito
    — se a carga não vier, ninguém opera em cima de uma conta fantasma.
    """
    from apps.accounts.models import Account

    if Account.objects.filter(pk=conta_id).exists():
        return
    Account.objects.create(
        pk=conta_id,
        name="(aguardando sincronização)",
        slug=f"sync-{str(conta_id)[:8]}",
        is_active=False,
    )
    logger.info("sync-enroll: conta %s criada como esqueleto até a carga chegar", conta_id)


def _reconciliar_identidade(node_id, pair_id, node_type):
    """O outro lado trocou de id? Então o registro antigo tem de sair da frente.

    A unicidade é `(pair_id, node_type)`, e a busca do `update_or_create` é
    por `pk`. Quando o id do par muda — que é EXATAMENTE o caso para o qual a
    rematrícula existe — ele não encontra nada pelo pk, tenta inserir, e bate
    na chave única do registro velho. A matrícula morre com `IntegrityError`
    DEPOIS de a nuvem já ter consumido o bilhete: o comando falha e o bilhete
    se perde, a cada tentativa.

    Foi o que aconteceu com uma loja cujo nó da nuvem tinha sido apagado por
    uma migração de limpeza do outro lado. Ela ficou sem conseguir
    rematricular, endereçando eventos para um nó que não existia mais.

    Aqui o velho é FUNDIDO no novo: eventos, cargas e conflitos passam a
    apontar para a identidade nova e o registro morto é removido. Nada de
    histórico se perde — é a mesma instalação, com outro nome.
    """

    novo_id = uuid.UUID(str(node_id))
    velho = (
        SyncNode.objects.filter(pair_id=uuid.UUID(str(pair_id)), node_type=node_type)
        .exclude(pk=novo_id)
        .first()
    )
    if velho is None:
        return None

    logger.warning(
        "sync-enroll: %s trocou de identidade (%s -> %s); fundindo o registro antigo",
        node_type, velho.id, novo_id,
    )
    # Libera a chave única ANTES de o novo nascer. O par provisório dura o
    # tempo da fusão, que apaga o velho logo em seguida.
    SyncNode.objects.filter(pk=velho.pk).update(pair_id=uuid.uuid4())
    return velho


def _gravar_no(node_id, pair_id, conta_id, node_type, nome, *, is_self):
    """O nó é criado antes da carga; a conta já foi garantida acima."""
    from apps.synchronization.services import merge_nodes

    velho = _reconciliar_identidade(node_id, pair_id, node_type)
    no, _criado = SyncNode.objects.update_or_create(
        pk=uuid.UUID(str(node_id)),
        defaults={
            "pair_id": uuid.UUID(str(pair_id)),
            "account_id": conta_id,
            "node_type": node_type,
            "environment": guard.current_environment(),
            "name": nome,
            "status": NodeStatus.ACTIVE if is_self else NodeStatus.PENDING,
            "is_self": is_self,
            "is_active": True,
        },
    )
    if velho is not None:
        # Relidos do banco: `update_or_create` deixa `account_id` como veio do
        # pacote (texto), e a validação da fusão compara com o UUID do antigo.
        # Sem reler, ela recusa por "contas diferentes" — comparando `str` com
        # `UUID` da MESMA conta.
        merge_nodes.merge(
            SyncNode.objects.get(pk=velho.pk), SyncNode.objects.get(pk=no.pk)
        )
        no.refresh_from_db()
    return no
