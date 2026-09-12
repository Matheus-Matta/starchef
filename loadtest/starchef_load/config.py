"""Parametros da execucao e os perfis prontos de intensidade."""
import os
from dataclasses import dataclass, field

#: Perfis: (workers, taxa alvo por modelo/s, duracao por fase, terminais, garcons)
PROFILES = {
    "fumaca": {"workers": 8, "rate": 30, "duration": 5, "terminals": 2, "waiters": 2, "sales": 3},
    "leve": {"workers": 24, "rate": 150, "duration": 15, "terminals": 3, "waiters": 4, "sales": 8},
    "medio": {"workers": 64, "rate": 500, "duration": 30, "terminals": 6, "waiters": 10, "sales": 20},
    "pesado": {"workers": 128, "rate": 1000, "duration": 60, "terminals": 12, "waiters": 24, "sales": 40},
    "extremo": {"workers": 256, "rate": 3000, "duration": 120, "terminals": 24, "waiters": 60, "sales": 80},
}


@dataclass
class LoadConfig:
    base_url: str = "http://127.0.0.1:8001"
    frontend_url: str = "http://127.0.0.1:5173"
    username: str = "admin"
    password: str = "admin12345"

    profile: str = "medio"
    workers: int = 64
    rate: int = 500
    duration: int = 30
    count: int = 0
    timeout: float = 20.0

    chaos_ratio: float = 0.35
    sloppy_ratio: float = 0.3
    offline_ratio: float = 0.35
    terminals: int = 6
    waiters: int = 10
    sales: int = 20
    seed: int = 20260910

    models: list = field(default_factory=list)
    report_dir: str = "artifacts/loadtest"
    label: str = ""
    cleanup: bool = False
    verbose: bool = False
    skip_bootstrap: bool = False

    @classmethod
    def from_args(cls, args):
        config = cls()
        perfil = PROFILES.get(args.profile or "medio", PROFILES["medio"])
        config.profile = args.profile or "medio"
        for chave, valor in perfil.items():
            setattr(config, chave, valor)
        for campo in (
            "base_url", "frontend_url", "username", "password", "workers", "rate",
            "duration", "count", "timeout", "chaos_ratio", "sloppy_ratio", "offline_ratio",
            "terminals", "waiters", "sales", "seed", "report_dir", "label",
            "cleanup", "verbose", "skip_bootstrap",
        ):
            valor = getattr(args, campo, None)
            if valor is not None:
                setattr(config, campo, valor)
        config.models = list(getattr(args, "models", None) or [])
        config.base_url = os.environ.get("LOADTEST_BASE_URL", config.base_url)
        config.frontend_url = os.environ.get("LOADTEST_FRONTEND_URL", config.frontend_url)
        return config

    def describe(self):
        return {
            "perfil": self.profile,
            "api": self.base_url,
            "frontend": self.frontend_url,
            "workers": self.workers,
            "taxa_alvo_rps": self.rate,
            "duracao_por_fase_s": self.duration,
            "proporcao_caos": self.chaos_ratio,
            "proporcao_desleixo": self.sloppy_ratio,
            "proporcao_offline": self.offline_ratio,
            "terminais_pdv": self.terminals,
            "garcons": self.waiters,
            "vendas_por_terminal": self.sales,
            "semente": self.seed,
        }
