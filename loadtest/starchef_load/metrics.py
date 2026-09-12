"""Coleta thread-safe das metricas e agregacao por grupo.

Guardar todo `RequestResult` de uma tempestade de 1000/s estouraria a memoria
antes do relatorio sair. Entao: contadores e latencias por grupo (float e
barato), e amostras COMPLETAS apenas dos defeitos — que sao o que alguem vai
querer ler depois.
"""
import threading
from collections import Counter, defaultdict

from . import result as verdicts

MAX_SAMPLES_PER_GROUP = 12
MAX_SUSPECTS_PER_GROUP = 6


def percentile(sorted_values, fraction):
    if not sorted_values:
        return 0.0
    index = int(round(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


class GroupStats:
    """Numeros de um grupo (um modelo, uma rota, um estagio de rampa)."""

    def __init__(self, name):
        self.name = name
        self.total = 0
        self.verdicts = Counter()
        self.statuses = Counter()
        self.cases = Counter()
        self.case_defects = Counter()
        self.latencies = []
        self.samples = []
        self.suspects = []
        self.first_ts = None
        self.last_ts = 0.0

    def add(self, result):
        self.total += 1
        self.verdicts[result.verdict] += 1
        self.statuses[result.status] += 1
        self.cases[result.case] += 1
        self.latencies.append(result.latency_ms)
        if self.first_ts is None:
            self.first_ts = result.started_at
        self.last_ts = max(self.last_ts, result.started_at + result.latency_ms / 1000.0)
        if result.is_defect:
            self.case_defects[result.case] += 1
            if len(self.samples) < MAX_SAMPLES_PER_GROUP:
                self.samples.append(result)
        elif result.verdict == verdicts.VALID_REJECTED and len(self.suspects) < MAX_SUSPECTS_PER_GROUP:
            # Nao e defeito por si so: pode ser regra de negocio legitima. Mas
            # sem a mensagem do servidor ninguem consegue decidir qual dos dois e.
            self.suspects.append(result)

    @property
    def elapsed(self):
        if self.first_ts is None:
            return 0.0
        return max(self.last_ts - self.first_ts, 1e-6)

    @property
    def rps(self):
        return self.total / self.elapsed if self.total else 0.0

    def summary(self):
        ordered = sorted(self.latencies)
        return {
            "grupo": self.name,
            "requisicoes": self.total,
            "rps": round(self.rps, 1),
            "duracao_s": round(self.elapsed, 2),
            "p50_ms": round(percentile(ordered, 0.50), 1),
            "p90_ms": round(percentile(ordered, 0.90), 1),
            "p99_ms": round(percentile(ordered, 0.99), 1),
            "max_ms": round(ordered[-1], 1) if ordered else 0.0,
            "vereditos": dict(self.verdicts),
            "status": {str(k): v for k, v in sorted(self.statuses.items())},
            "casos": dict(self.cases),
            "casos_com_defeito": dict(self.case_defects),
        }


class Recorder:
    """Onde todo resultado cai. Uma instancia por execucao."""

    def __init__(self):
        self._lock = threading.Lock()
        self.groups = {}
        self.suites = defaultdict(lambda: defaultdict(list))
        self.timeline = Counter()
        self.notes = []
        self.checks = []

    def record(self, result):
        key = f"{result.suite}::{result.group}"
        with self._lock:
            stats = self.groups.get(key)
            if stats is None:
                stats = self.groups[key] = GroupStats(result.group)
                stats.suite = result.suite
            stats.add(result)
            self.timeline[(result.suite, int(result.started_at))] += 1

    def note(self, suite, text):
        """Observacao livre (ex.: 'o principal ficou 30s offline')."""
        with self._lock:
            self.notes.append({"suite": suite, "texto": text})

    def check(self, suite, name, passed, detail=""):
        """Verificacao de coerencia pos-carga (ex.: pagamento nao duplicou)."""
        with self._lock:
            self.checks.append(
                {"suite": suite, "nome": name, "ok": bool(passed), "detalhe": detail}
            )

    def defects(self):
        found = []
        for stats in self.groups.values():
            found.extend(stats.samples)
        return found

    def suspects(self):
        encontrados = []
        for stats in self.groups.values():
            encontrados.extend(stats.suspects)
        return encontrados

    def peak_rps(self, suite=None):
        buckets = [n for (s, _), n in self.timeline.items() if suite in (None, s)]
        return max(buckets) if buckets else 0
