"""Identidade do terminal (PdvTerminal) e as regras de dono de uma sessao de caixa.

Separado de `services.py` porque e a peca que responde a UMA pergunta:
"quem, e de onde, pode mexer nesta sessao?". A abertura, o fechamento, a
sangria, o suprimento e o pagamento fazem todos a mesma pergunta — bloquear so
o botao de abrir nao impediria ninguem de chamar os outros endpoints direto.
"""
from urllib.parse import unquote

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.payments.models import CashRegister, PdvTerminal


class CashSessionConflict(ValidationError):
    """O caixa (ou o operador) ja esta ocupado por outra sessao.

    E um conflito com o estado atual do recurso, nao um erro de digitacao: a
    view devolve 409 e o cliente mostra quem esta com o caixa.
    """

    def __init__(self, message, *, session=None, code="cash_session_conflict"):
        super().__init__(message, code=code)
        self.session = session
        self.error_code = code


class CashSessionForbidden(ValidationError):
    """Quem pediu a operacao nao e o dono da sessao (usuario+terminal)."""

    def __init__(self, message, *, session=None, code="cash_session_forbidden"):
        super().__init__(message, code=code)
        self.session = session
        self.error_code = code


def installation_id_from_request(request):
    """O UUID da instalacao que o cliente enviou, seja como for.

    Tres formas convivem de proposito: o cabecalho `X-Terminal-Id` (que o app e
    a web mandam em TODA requisicao, para nao ser preciso lembrar de incluir o
    campo em cada rota nova), `terminal_installation_id` no corpo (a forma
    explicita) e `device_identifier` (o campo antigo, para um cliente
    desatualizado nao parar de funcionar durante a atualizacao).
    """
    data = request.data if isinstance(request.data, dict) else {}
    return str(
        data.get("terminal_installation_id")
        or data.get("device_identifier")
        or request.headers.get("X-Terminal-Id")
        or request.query_params.get("terminal_installation_id")
        or ""
    ).strip()


def terminal_name_from_request(request):
    """O nome amigavel do terminal que veio no cabecalho, ja desescapado.

    Cabecalho HTTP nao carrega UTF-8: um terminal chamado "Balcao 01" (com
    til) faz o cliente Dart estourar `FormatException` antes de enviar, e o
    navegador manda latin-1 cru. Por isso o PDV percent-encoda o valor quando
    ele tem acento, e aqui desfazemos. Nome ja em ASCII puro atravessa igual
    — `unquote` sem `%` devolve o proprio texto —, entao um cliente antigo
    continua sendo entendido.
    """
    raw = request.headers.get("X-Terminal-Name") or ""
    try:
        return unquote(raw)
    except (UnicodeDecodeError, ValueError):
        # Escape malformado nao pode custar a identificacao do terminal: o
        # nome e so o rotulo, o `installation_id` e quem manda.
        return raw


def terminal_from_request(request, *, restaurant=None):
    """Resolve (cadastrando na primeira vez) o PdvTerminal desta requisicao."""
    data = request.data if isinstance(request.data, dict) else {}
    return resolve_terminal(
        account=getattr(request, "account", None),
        installation_id=installation_id_from_request(request),
        restaurant=restaurant,
        name=data.get("terminal_name") or terminal_name_from_request(request),
        device_type=data.get("terminal_type") or "",
        role=data.get("terminal_role") or "",
    )


def operator_label(user):
    if user is None:
        return "outro operador"
    return user.get_full_name() or user.get_username()


def resolve_terminal(
    *,
    account,
    installation_id,
    restaurant=None,
    name="",
    device_type="",
    role="",
    touch=True,
):
    """Acha (ou cadastra) o terminal desta instalacao e marca que ele apareceu.

    `installation_id` vazio devolve `None`: um cliente antigo que ainda nao
    manda a identidade continua funcionando — ele so nao ganha a protecao por
    maquina. Nada aqui recusa a operacao, porque recusar deixaria o caixa
    parado por causa de um app desatualizado.
    """
    installation_id = str(installation_id or "").strip()[:120]
    if not installation_id or account is None:
        return None

    terminal = PdvTerminal.all_objects.filter(
        account=account, installation_id=installation_id
    ).first()
    if terminal is None:
        terminal = PdvTerminal(
            account=account,
            installation_id=installation_id,
            name=str(name or "").strip()[:120],
            device_type=device_type or PdvTerminal.TYPE_DESKTOP,
            role=role or PdvTerminal.ROLE_SECONDARY,
            restaurant=restaurant,
            last_seen_at=timezone.now(),
        )
        terminal.save()
        return terminal

    changed = []
    # Terminal revogado volta a valer sozinho? Nao: revogar e uma decisao
    # administrativa, e reaparecer nao a desfaz.
    if name and terminal.name != str(name).strip()[:120]:
        terminal.name = str(name).strip()[:120]
        changed.append("name")
    if device_type and terminal.device_type != device_type:
        terminal.device_type = device_type
        changed.append("device_type")
    if role and terminal.role != role:
        terminal.role = role
        changed.append("role")
    if restaurant is not None and terminal.restaurant_id != restaurant.pk:
        terminal.restaurant = restaurant
        changed.append("restaurant")
    if terminal.deleted_at is not None:
        terminal.deleted_at = None
        changed.append("deleted_at")
    if touch:
        terminal.last_seen_at = timezone.now()
        changed.append("last_seen_at")
    if changed:
        terminal.save(update_fields=[*changed, "updated_at"])
    return terminal


def terminal_label_of(session):
    """Nome do terminal que abriu a sessao, preferindo o retrato da abertura.

    Vazio quando a sessao nao tem terminal: e o caso das sessoes abertas antes
    desta regra, e a mensagem de bloqueio precisa saber a diferenca entre "foi
    no Balcao 01" e "nao sabemos de onde".
    """
    return (
        session.opened_terminal_label
        or (session.opened_terminal.label if session.opened_terminal_id else "")
    )


def occupied_message(session):
    """A mensagem que o operador bloqueado precisa ler.

    Diz quem esta com o caixa, de onde e desde quando — e o que fazer a
    respeito. Sem isso o operador so via "ja existe uma sessao aberta" e nao
    tinha como saber a quem recorrer.
    """
    station = session.cash_station.name if session.cash_station_id else session.station
    opened_at = timezone.localtime(session.opened_at).strftime("%d/%m/%Y às %H:%M")
    terminal = terminal_label_of(session)
    where = f" no terminal {terminal}" if terminal else ""
    return (
        f"O {station} já está aberto por {operator_label(session.opened_by)}"
        f"{where} desde {opened_at}. "
        "Finalize a sessão ou solicite uma transferência gerencial."
    )


def session_conflict_payload(session):
    """Dados estruturados do bloqueio, para a tela montar o aviso sozinha."""
    return {
        "code": "cash_session_conflict",
        "message": occupied_message(session),
        "session": {
            "id": str(session.pk),
            "status": session.status,
            "opened_at": session.opened_at,
            "opened_by": str(session.opened_by_id) if session.opened_by_id else None,
            "opened_by_name": operator_label(session.opened_by),
            "opened_terminal": str(session.opened_terminal_id) if session.opened_terminal_id else None,
            "opened_terminal_label": terminal_label_of(session),
            "opened_terminal_known": bool(terminal_label_of(session)),
            "cash_station": str(session.cash_station_id) if session.cash_station_id else None,
            "cash_station_name": session.cash_station.name if session.cash_station_id else session.station,
        },
    }


def session_belongs_to(session, *, user, terminal=None, installation_id=""):
    """A sessao e deste usuario NESTE terminal?

    Terminal ausente nos dois lados (cliente antigo, sessao antiga) cai para a
    checagem por usuario apenas — a regra por maquina so passa a valer quando
    ha uma maquina identificada dos dois lados.
    """
    if session.opened_by_id != getattr(user, "pk", None):
        return False
    expected = session.opened_terminal_id
    if expected is None:
        return True
    if terminal is not None:
        return terminal.pk == expected
    installation_id = str(installation_id or "").strip()
    if not installation_id:
        # A sessao tem dono de maquina mas o cliente nao se identificou:
        # tratamos como outra maquina. Afrouxar aqui anularia a regra 5
        # ("o mesmo usuario em outra maquina tambem sera bloqueado"), porque
        # bastaria omitir o campo para contornar.
        return False
    return session.opened_terminal.installation_id == installation_id


def assert_session_owner(session, *, user, terminal=None, installation_id=""):
    """Barra qualquer operacao de quem nao e o dono da sessao.

    Aplicado na recuperacao, no pagamento, na sangria, no suprimento e no
    fechamento — nao so na abertura.
    """
    if session_belongs_to(session, user=user, terminal=terminal, installation_id=installation_id):
        return session
    if session.opened_by_id != getattr(user, "pk", None):
        raise CashSessionForbidden(occupied_message(session), session=session)
    raise CashSessionForbidden(other_terminal_message(session), session=session, code="cash_session_other_terminal")


def other_terminal_message(session):
    """Mesma pessoa, outra maquina — regra 5."""
    terminal = terminal_label_of(session)
    where = f"no terminal {terminal}" if terminal else "em outro terminal"
    return (
        f"Esta sessão foi aberta por você {where}. "
        "Continue nele, ou solicite uma transferência gerencial para operar daqui."
    )


def active_session_for_station(cash_station, *, for_update=False):
    queryset = CashRegister.objects.filter(cash_station=cash_station)
    if for_update:
        # A sessao possui relacionamentos opcionais carregados abaixo por
        # LEFT OUTER JOIN. No PostgreSQL, um FOR UPDATE sem alvo tenta travar
        # tambem o lado nullable desses joins e falha com NotSupportedError.
        # A exclusividade precisa bloquear somente a linha de CashRegister.
        queryset = queryset.select_for_update(of=("self",))
    return (
        CashRegister.active_sessions(queryset)
        .select_related("opened_by", "opened_terminal", "cash_station")
        .order_by("-opened_at")
        .first()
    )


def active_session_for_user(restaurant, user):
    return (
        CashRegister.active_sessions(
            CashRegister.objects.filter(restaurant=restaurant, opened_by=user)
        )
        .select_related("opened_by", "opened_terminal", "cash_station")
        .order_by("-opened_at")
        .first()
    )
