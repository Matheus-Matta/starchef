"""Primeiro contato: a loja se apresenta à nuvem e pede a carga inicial.

O problema que isto resolve: um backend local recém-instalado tem banco vazio e
nenhuma credencial. Alguém teria de copiar token e chave à mão do Admin da
nuvem para o `.env` da loja — e é exatamente aí que segredo vaza por WhatsApp.

O fluxo aqui troca isso por um *enrollment*: a loja apresenta usuário e senha
de um superusuário da conta, o `account_id` e um segredo de matrícula
combinado; a nuvem autentica, provisiona o nó, devolve o pacote de credenciais
**cifrado com esse segredo** e já enfileira a carga total para aquele nó.

O segredo de matrícula é de uso único por instalação e NÃO é a chave de
sincronização — a chave definitiva nasce na nuvem e vem dentro do pacote
cifrado. Confundir os dois faria o segredo digitado por uma pessoa virar a
chave de todo o tráfego da loja para sempre.
"""
import logging

from django.contrib.auth import authenticate as django_authenticate
from django.db import transaction

from apps.accounts.models import Account
from apps.synchronization.constants import NodeType, RunType
from apps.synchronization.models import SyncNode
from apps.synchronization.services import bootstrap, crypto, guard, provisioning, staleness

logger = logging.getLogger(__name__)

#: Tamanho mínimo do segredo de matrícula. Curto demais é adivinhável, e ele
#: protege o pacote que contém a credencial definitiva.
MIN_SEGREDO = 24


class EnrollmentRefused(PermissionError):
    """Credencial inválida, conta errada ou segredo fraco."""


def enroll(*, username, password, account_id, enrollment_secret, node_name,
           restaurant_id=None, cloud_wss_url="", client_ip=None, existing_node_id=None):
    """Lado NUVEM: autentica, provisiona e devolve o pacote cifrado.

    Devolve `(no, envelope_cifrado, run)`. O pacote em claro nunca sai desta
    função — quem chama só vê o ciphertext.
    """
    guard.ensure_environment()
    _validar_segredo(enrollment_secret)

    usuario = django_authenticate(username=username, password=password)
    if usuario is None or not usuario.is_active:
        logger.warning("sync-enroll: credencial inválida user=%s ip=%s", username, client_ip)
        raise EnrollmentRefused("Usuário ou senha inválidos.")

    conta = _conta_autorizada(usuario, account_id, client_ip)

    with transaction.atomic():
        # Um bilhete, se for o caso, é gasto AQUI — dentro da mesma transação
        # que provisiona. Gastá-lo antes deixaria um bilhete queimado por uma
        # matrícula que falhou depois; gastá-lo depois abriria a janela para a
        # segunda tentativa simultânea passar.
        bilhete = _consumir_bilhete(enrollment_secret, conta, client_ip)
        no, pacote = _provisionar(
            conta, restaurant_id, node_name, cloud_wss_url, existing_node_id
        )
        # Rematrícula supera a carga anterior: a loja está recomeçando e
        # ninguém mais vai receber aquela. Sem isto, uma instalação que caiu no
        # meio do primeiro bootstrap ficaria travada em "já existe uma carga".
        bootstrap.cancel_running(no, motivo=f"Substituída pela matrícula de {node_name}.")
        # E supera também as fichas ANTIGAS da mesma loja. Sem isto, uma loja
        # que rematricula deixa para trás um nó com a carga inteira endereçada
        # a ele e passa a conectar por outro, que não tem nada — a nuvem
        # responde "0 pendentes" e nada acontece, para sempre.
        staleness.superar_nos_irmaos(
            no, motivo=f"Superado pela matrícula de {node_name}."
        )
        run = bootstrap.start_run(
            target_node=no,
            run_type=RunType.FULL,
            user=usuario,
            ip=client_ip,
            reason=f"Matrícula automática do nó {node_name}",
        )
        if bilhete is not None:
            bilhete.used_by_node = no
            bilhete.save(update_fields=["used_by_node"])

    pacote["SYNC_INITIAL_RUN_ID"] = str(run.id)
    envelope = _cifrar(pacote, enrollment_secret)
    logger.info(
        "sync-enroll: nó %s matriculado para conta %s por %s (carga %s)",
        no.id, conta.id, usuario, run.id,
    )
    return no, envelope, run


def emitir_bilhete(*, conta, criado_por=None, restaurante=None, label="",
                   validade_minutos=None):
    """Lado NUVEM: cria um bilhete e devolve `(bilhete, codigo_em_claro)`.

    O código em claro só existe aqui e na resposta. Depois disto, nem o Admin
    consegue lê-lo de volta — o que fica gravado é o hash, pela mesma razão que
    o token do nó fica: um banco lido por quem não devia não pode virar um
    banco de credenciais utilizáveis.
    """
    from apps.synchronization.models import SyncEnrollmentTicket
    from django.utils import timezone

    minutos = validade_minutos or SyncEnrollmentTicket.VALIDADE_PADRAO_MINUTOS
    codigo = SyncEnrollmentTicket.novo_codigo()
    bilhete = SyncEnrollmentTicket.objects.create(
        account=conta,
        restaurant=restaurante,
        code_hash=crypto.hash_token(codigo),
        label=label[:120],
        created_by=criado_por,
        expires_at=timezone.now() + timezone.timedelta(minutes=minutos),
    )
    logger.info(
        "sync-enroll: bilhete %s emitido para a conta %s por %s (validade %smin)",
        bilhete.id, conta.id, criado_por, minutos,
    )
    return bilhete, codigo


def _consumir_bilhete(segredo, conta, client_ip):
    """Gasta o bilhete correspondente ao segredo, se houver um.

    Devolve o bilhete ou `None`. `None` NÃO é recusa: significa que o segredo
    apresentado não é um bilhete, e o fluxo segue pelo `SYNC_ENROLL_SECRET`
    combinado — que continua valendo para não quebrar instalação existente.

    O `select_for_update` existe porque "uso único" é uma promessa sobre
    concorrência: duas matrículas simultâneas com o mesmo código precisam
    resultar em uma aceita e uma recusada, não em duas aceitas porque as duas
    leram `used_at = None` antes de qualquer uma gravar.
    """
    from apps.synchronization.models import SyncEnrollmentTicket
    from django.utils import timezone

    hash_do_codigo = crypto.hash_token(segredo)
    bilhete = SyncEnrollmentTicket.objects.filter(code_hash=hash_do_codigo).first()
    if bilhete is None:
        return None

    bloqueado = (
        SyncEnrollmentTicket.objects.select_for_update()
        .filter(pk=bilhete.pk)
        .first()
    )
    if bloqueado.used_at is not None:
        logger.error(
            "sync-enroll: bilhete %s reapresentado (já usado em %s) ip=%s",
            bloqueado.id, bloqueado.used_at, client_ip,
        )
        raise EnrollmentRefused("Este bilhete de matrícula já foi usado.")
    if bloqueado.vencido:
        logger.warning("sync-enroll: bilhete %s vencido ip=%s", bloqueado.id, client_ip)
        raise EnrollmentRefused("Este bilhete de matrícula venceu. Peça um novo.")
    if str(bloqueado.account_id) != str(conta.id):
        # Conta diferente da do bilhete: não é engano de digitação, é uso do
        # bilhete de uma conta para matricular nó em outra.
        logger.error(
            "sync-enroll: bilhete %s da conta %s usado para a conta %s ip=%s",
            bloqueado.id, bloqueado.account_id, conta.id, client_ip,
        )
        raise EnrollmentRefused("Este bilhete não pertence à conta informada.")

    bloqueado.used_at = timezone.now()
    bloqueado.used_from_ip = client_ip or None
    bloqueado.save(update_fields=["used_at", "used_from_ip"])
    return bloqueado


def _validar_segredo(segredo):
    if not segredo or len(segredo) < MIN_SEGREDO:
        raise EnrollmentRefused(
            f"O segredo de matrícula precisa de pelo menos {MIN_SEGREDO} caracteres."
        )


def _conta_autorizada(usuario, account_id, client_ip):
    """Só superusuário ou admin DA CONTA pedida. Nunca de outra."""
    conta = Account.objects.filter(pk=account_id).first()
    if conta is None:
        raise EnrollmentRefused("Conta não encontrada.")

    if usuario.is_superuser:
        return conta

    perfil = getattr(usuario, "profile", None)
    da_conta = perfil is not None and str(perfil.account_id) == str(conta.id)
    e_admin = perfil is not None and getattr(perfil.role, "is_account_admin", False)
    if not (da_conta and e_admin):
        logger.error(
            "sync-enroll: %s tentou matricular nó na conta %s ip=%s",
            usuario, conta.id, client_ip,
        )
        raise EnrollmentRefused("Usuário sem permissão para matricular nó nesta conta.")
    return conta


def _provisionar(conta, restaurant_id, node_name, cloud_wss_url, existing_node_id):
    """Rematrícula reaproveita o nó: o vínculo é o mesmo, a credencial é nova.

    Reprovisionar do zero criaria um segundo nó para a mesma loja, e a nuvem
    passaria a mandar tudo em duplicidade para um destino que não existe mais.
    """
    if existing_node_id:
        no = SyncNode.objects.filter(
            pk=existing_node_id, account=conta, node_type=NodeType.LOCAL
        ).first()
        if no is not None:
            # O nome acompanha o `.env` da loja. Sem isto, trocar
            # `SYNC_NODE_NAME` de "Loja Centro" para "Loja Cobogó" e
            # rematricular não mudava nada: a nuvem continuava listando o nome
            # antigo, e quem fosse procurar a loja no Admin procuraria por um
            # nome que só existe no arquivo de configuração dela.
            if node_name and no.name != node_name:
                logger.info(
                    "sync-enroll: nó %s renomeado de %r para %r",
                    no.id, no.name, node_name,
                )
                no.name = node_name
                no.save(update_fields=["name", "updated_at"])
            segredos = provisioning.rotate_credentials(no)
            return no, _pacote(no, conta, cloud_wss_url, segredos)

    from apps.restaurants.models import Restaurant

    restaurante = (
        Restaurant.all_objects.filter(pk=restaurant_id, account=conta).first()
        if restaurant_id else None
    )
    return provisioning.provision_local_node(
        account=conta,
        restaurant=restaurante,
        name=node_name,
        endpoint=cloud_wss_url,
        cloud_endpoint=cloud_wss_url,
    )


def _pacote(no, conta, cloud_wss_url, segredos):
    return {
        "SYNC_ENABLED": "true",
        "SYNC_ENVIRONMENT": no.environment,
        "SYNC_NODE_TYPE": "local",
        "SYNC_NODE_ID": str(no.id),
        "SYNC_PAIR_ID": str(no.pair_id),
        "SYNC_ACCOUNT_ID": str(conta.id),
        "SYNC_STORE_ID": str(no.restaurant_id or ""),
        # O nome volta no pacote para a ficha que a LOJA grava de si mesma ter
        # o mesmo nome que a da nuvem. Sem isto, o lado de cá caía no padrão
        # "Servidor da loja" — o Admin da nuvem dizia "Loja Cobogó" e o da loja
        # dizia outra coisa, para o mesmo nó. Quem fosse diagnosticar com os
        # dois abertos não teria como cruzar um com o outro.
        "SYNC_NODE_NAME": no.name,
        "SYNC_CLOUD_WSS_URL": cloud_wss_url or no.endpoint,
        "SYNC_PEER_NODE_ID": str(no.peer_id or ""),
        **segredos,
    }


def _cifrar(pacote, segredo):
    """AES-256-GCM com chave derivada do segredo de matrícula."""
    chave = derive_key(segredo)
    nonce, ciphertext = crypto.encrypt(pacote, chave)
    return {"nonce": nonce, "ciphertext": ciphertext, "checksum": crypto.checksum(pacote)}


def decifrar(envelope, segredo):
    """Lado LOJA: abre o pacote e confere o checksum antes de instalar."""
    pacote = crypto.decrypt(envelope["nonce"], envelope["ciphertext"], derive_key(segredo))
    if envelope.get("checksum") and crypto.checksum(pacote) != envelope["checksum"]:
        raise EnrollmentRefused("Checksum do pacote de matrícula não confere.")
    return pacote


def derive_key(segredo):
    """SHA-256 do segredo -> 32 bytes. Determinístico nos dois lados."""
    import base64
    import hashlib

    return base64.b64encode(hashlib.sha256(segredo.encode("utf-8")).digest()).decode("ascii")
