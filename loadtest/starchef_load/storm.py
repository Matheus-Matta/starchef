"""O disparo unitario da tempestade: monta, suja e manda um payload.

Isolado do orquestrador porque as quatro suites usam a mesma mecanica — muda
so quem chama e com que ritmo.
"""
import json
import threading
import time

from . import chaos
from . import result as verdicts

DENY = (
    "/auth/", "/accounts/", "/plans/", "/subscriptions/", "/system-config/",
    "/permissions/", "/roles/", "/webhook/", "/invoices/emit/", "/data-exchange/",
    "/bulk/", "/bulk-create/", "/bulk-delete/", "/bulk-update/", "/codes-batch/",
    "/schema/", "/notifications/",
)

MAX_TRACKED_IDS = 400


def selectable_models(schema, apenas=None):
    """Rotas POST de colecao que valem uma tempestade de criacao."""
    escolhidas = []
    for path in schema.creatable_paths():
        if any(bloqueado in path for bloqueado in DENY):
            continue
        nome = path.strip("/").replace("api/v1/", "").rstrip("/")
        if apenas and not any(filtro in nome for filtro in apenas):
            continue
        escolhidas.append((nome, path))
    return escolhidas


def is_action_path(path, colecoes):
    """`/orders/open-command/` e uma ACTION, nao uma colecao.

    O OpenAPI publica ali o serializer do recurso, mas a view le so um punhado
    de campos do corpo — ignorar os outros e o comportamento certo. Cobrar uma
    recusa nesses casos transformava acerto em "lixo aceito" no relatorio.
    """
    pai = path.rstrip("/").rsplit("/", 1)[0] + "/"
    return pai in colecoes and pai != path


class ModelStorm:
    """Estado de um modelo sob carga: schema, IDs criados e contadores."""

    def __init__(self, name, path, schema, action=False):
        self.name = name
        self.path = path
        self.schema = schema
        self.action = action
        self.created_ids = []
        self._lock = threading.Lock()

    def track(self, identifier):
        if not identifier:
            return
        with self._lock:
            if len(self.created_ids) < MAX_TRACKED_IDS:
                self.created_ids.append(str(identifier))

    def any_id(self, r):
        with self._lock:
            return r.choice(self.created_ids) if self.created_ids else None

    def forget(self, identifier):
        """ID apagado sai do pool: um PATCH nele depois devolveria 404 e o
        relatorio marcaria como recusa indevida uma resposta certa."""
        with self._lock:
            if identifier in self.created_ids:
                self.created_ids.remove(identifier)


def fire_create(ctx, suite, storm, r, chaos_ratio, sloppy_ratio=0.3):
    """Uma criacao: limpa, desleixada ou estragada — sempre com veredito."""
    payload, desleixado = ctx.builder.build(storm.schema, r, sloppy_ratio=sloppy_ratio)
    case = "desleixado" if desleixado else "valido"
    expectation = verdicts.ANY if desleixado else verdicts.ACCEPT
    if r.random() < chaos_ratio:
        case, expectation = chaos.apply_mutation(payload, storm.schema, r)
        if storm.action and expectation == verdicts.REJECT:
            # A action so le os campos que lhe interessam; ignorar o resto e correto.
            expectation = verdicts.ANY
    started = time.time()
    response = ctx.session.post(storm.path, payload)
    resultado = ctx.record(
        suite, storm.name, "POST", storm.path, response,
        expectation=expectation, case=case,
        payload=json.dumps(payload, ensure_ascii=False, default=str)[:600], started=started,
    )
    if response.status in (200, 201):
        corpo = response.json()
        if isinstance(corpo, dict):
            storm.track(corpo.get("id"))
    return resultado


def fire_raw(ctx, suite, storm, r):
    """Corpo cru e malformado — o que um cliente quebrado manda de verdade."""
    case, corpo, content_type, expectation = r.choice(chaos.RAW_CASES)
    # `{}` e `{"name": <2 MB>}` sao objetos JSON validos: num modelo em que
    # nada e obrigatorio (comanda: numero e codigo automaticos) criar e correto.
    if case in ("corpo_vazio", "corpo_gigante") and not storm.schema.required:
        expectation = verdicts.ANY
    started = time.time()
    response = ctx.api.request(
        "POST", storm.path, raw=corpo, content_type=content_type, headers=ctx.session.headers()
    )
    return ctx.record(
        suite, f"{storm.name} (cru)", "POST", storm.path, response,
        expectation=expectation, case=case, payload=f"<{len(corpo)} bytes {content_type}>", started=started,
    )


#: (caso, query, expectativa). ANY = as duas respostas sao defensaveis; o que
#: nao pode, em nenhum caso, e 5xx ou conexao derrubada.
READ_VARIANTS = [
    ("listagem", "?page_size=25", verdicts.ACCEPT),
    ("pagina_alta", "?page=999&page_size=100", verdicts.ANY),
    ("pagina_invalida", "?page=abc&page_size=-5", verdicts.ANY),
    ("busca", "?search=LT", verdicts.ACCEPT),
    ("busca_hostil", "?search=%27%20OR%201%3D1--", verdicts.ACCEPT),
    ("ordenacao_invalida", "?ordering=campo_que_nao_existe", verdicts.ANY),
    ("delta_sync", "?updated_after=2020-01-01T00:00:00Z&include_deleted=1", verdicts.ACCEPT),
    ("page_size_absurdo", "?page_size=100000", verdicts.ANY),
    ("filtro_desconhecido", "?zzz=1&is_active=talvez", verdicts.ANY),
]


def fire_read(ctx, suite, storm, r):
    case, query, expectation = r.choice(READ_VARIANTS)
    started = time.time()
    response = ctx.session.get(f"{storm.path}{query}")
    return ctx.record(
        suite, f"{storm.name} (leitura)", "GET", f"{storm.path}{query}", response,
        expectation=expectation, case=case, started=started,
    )


#: No PATCH, campo ausente e corpo vazio sao ATUALIZACAO PARCIAL — aceitar e o
#: comportamento certo. So `null` explicito em campo obrigatorio segue proibido.
PATCH_TOLERADO = ("faltando_obrigatorio", "payload_vazio")


def fire_mutate(ctx, suite, storm, r, chaos_ratio):
    """PATCH/DELETE sobre o que foi criado — e sobre o que nunca existiu."""
    identifier = storm.any_id(r)
    inexistente = identifier is None or r.random() < 0.25
    alvo = "00000000-0000-0000-0000-000000000000" if inexistente else identifier
    path = f"{storm.path}{alvo}/"
    if r.random() < 0.35:
        started = time.time()
        response = ctx.session.delete(path)
        expectation = verdicts.REJECT if inexistente else verdicts.ANY
        if not inexistente and response.status in (200, 202, 204):
            storm.forget(alvo)
        return ctx.record(
            suite, f"{storm.name} (delete)", "DELETE", path, response,
            expectation=expectation, case="id_inexistente" if inexistente else "delete_valido", started=started,
        )
    payload, desleixado = ctx.builder.build(storm.schema, r, sloppy_ratio=0.2)
    case = "patch_desleixado" if desleixado else "patch_valido"
    expectation = verdicts.REJECT if inexistente else (verdicts.ANY if desleixado else verdicts.ACCEPT)
    if r.random() < chaos_ratio:
        case, mutado = chaos.apply_mutation(payload, storm.schema, r)
        if case in PATCH_TOLERADO:
            mutado = verdicts.ANY
        expectation = verdicts.REJECT if inexistente else mutado
    started = time.time()
    response = ctx.session.patch(path, payload)
    return ctx.record(
        suite, f"{storm.name} (patch)", "PATCH", path, response,
        expectation=expectation, case=case if not inexistente else "id_inexistente",
        payload=json.dumps(payload, ensure_ascii=False, default=str)[:400], started=started,
    )
