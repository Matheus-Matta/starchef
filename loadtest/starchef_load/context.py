"""O que toda suite recebe pronto: conexao, sessao, schema e catalogo de IDs."""
import random
import time

from . import auth
from .builder import PayloadBuilder
from .http_client import HttpClient
from .metrics import Recorder
from .refs import RefPool
from .result import RequestResult
from .schema import ApiSchema


class Context:
    def __init__(self, config, log=print):
        self.config = config
        self.log = log
        self.recorder = Recorder()
        self.api = HttpClient(config.base_url, timeout=config.timeout)
        self.web = HttpClient(config.frontend_url, timeout=config.timeout)
        self.session = None
        self.schema = None
        self.refs = None
        self.builder = None
        self.started = time.time()

    def rng(self, offset=0):
        return random.Random(self.config.seed + offset)

    def prepare(self, *, need_schema=True, need_refs=True):
        self.session = auth.login(
            self.api, self.config.username, self.config.password, terminal_name="LT-orquestrador"
        )
        self.log(f"[auth] sessao ativa como {self.session.user.get('username', self.config.username)}")
        if need_schema:
            self.schema = ApiSchema.fetch(self.api, headers=self.session.headers())
            self.log(f"[schema] {len(self.schema.endpoints)} rotas de escrita descritas pelo OpenAPI")
        if need_refs:
            self.refs = RefPool(self.session).load()
            if not self.config.skip_bootstrap:
                self.refs.ensure_scenario(log=self.log)
            self.builder = PayloadBuilder(self.refs)
            self.log(
                f"[cenario] restaurante={(self.refs.restaurant or {}).get('trade_name', '?')} "
                f"produtos={len(self.refs.ids['products'])} comandas={len(self.refs.command_codes)} "
                f"formas={len(self.refs.ids['payment_methods'])}"
            )
        return self

    def record(self, suite, group, method, path, response, *, expectation, case="valido", payload="", started=None):
        resultado = RequestResult(
            suite=suite,
            group=group,
            method=method,
            path=path,
            status=response.status,
            latency_ms=response.elapsed_ms,
            expectation=expectation,
            case=case,
            error=response.error,
            detail=response.excerpt(),
            payload=payload,
            started_at=started if started is not None else time.time(),
        )
        self.recorder.record(resultado)
        return resultado

    def note(self, suite, texto):
        self.recorder.note(suite, texto)
        if self.config.verbose:
            self.log(f"[{suite}] {texto}")

    def check(self, suite, nome, passou, detalhe=""):
        self.recorder.check(suite, nome, passou, detalhe)
        marca = "ok" if passou else "FALHOU"
        self.log(f"[{suite}] verificacao {nome}: {marca} {detalhe}".rstrip())
