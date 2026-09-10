"""
Resolução do ambiente e do módulo de settings.

Uma variável decide tudo: **`DJANGO_ENV`**. Com ela valendo `development`, o
projeto usa `config.settings.development`, `DEBUG` é ligado, o banco é o SQLite
local e os cookies não exigem HTTPS — sem que ninguém precise manter
`DJANGO_DEBUG` e `DJANGO_SETTINGS_MODULE` em sincronia com ela. Três variáveis
dizendo a mesma coisa é uma a mais do que o necessário e duas a mais para
esquecer de trocar: o sintoma clássico era subir em "desenvolvimento" com
cookies `Secure`, e o login parar de funcionar em HTTP sem nenhuma mensagem.

Ordem de precedência (a primeira que existir decide):

1. `DJANGO_SETTINGS_MODULE` **exportado no ambiente** — é o override explícito
   de quem sabe o que está fazendo (docker-compose, CI, `--settings`);
2. `DJANGO_ENV` — o caminho normal;
3. `DJANGO_DEBUG` — compatibilidade com quem ainda a usa sozinha;
4. sem nenhuma delas: desenvolvimento (o padrão seguro para a máquina de quem
   acabou de clonar o projeto).

`DJANGO_SETTINGS_MODULE` escrito no arquivo `.env` é ignorado de propósito: ele
precisa existir no ambiente ANTES de o Django subir, e um `.env` só é lido
depois. Deixá-lo lá dá a falsa impressão de estar no controle.
"""
import os
from pathlib import Path

TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}

DEVELOPMENT = "development"
PRODUCTION = "production"

# Apelidos aceitos em `DJANGO_ENV`. Um nome fora destas listas é tratado como
# produção: se alguém escreveu "qa" e nós escolhêssemos desenvolvimento, o
# resultado seria um ambiente exposto com DEBUG ligado.
DEVELOPMENT_ENV_NAMES = {"dev", "develop", "development", "local"}
PRODUCTION_ENV_NAMES = {"prod", "production", "staging", "homolog", "homologacao", "homologação"}

SETTINGS_BY_ENVIRONMENT = {
    DEVELOPMENT: "config.settings.development",
    PRODUCTION: "config.settings.production",
}

_env_file_cache = None


def configure_django_settings():
    """Define `DJANGO_SETTINGS_MODULE` quando ele ainda não veio do ambiente."""
    if os.getenv("DJANGO_SETTINGS_MODULE"):
        os.environ.pop("STARCHEF_SETTINGS_AUTO", None)
        return os.environ["DJANGO_SETTINGS_MODULE"]

    settings_module = SETTINGS_BY_ENVIRONMENT[resolve_environment()]
    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    os.environ["STARCHEF_SETTINGS_AUTO"] = "1"
    return settings_module


def resolve_environment():
    """`"development"` ou `"production"` — ver a ordem de precedência no topo."""
    return _decide()[0]


def environment_is_explicit():
    """`DJANGO_ENV` foi quem decidiu o ambiente?

    Quando foi, ela define o `DEBUG` sozinha e um `DJANGO_DEBUG` divergente é
    ignorado — é isso que dispensa manter as duas em sincronia.
    """
    return _decide()[1] == "DJANGO_ENV"


def is_development():
    return resolve_environment() == DEVELOPMENT


def _decide():
    """`(ambiente, variável_que_decidiu)`.

    O ambiente EXPORTADO no processo vence o arquivo `.env` por inteiro — os
    dois níveis são consultados na mesma ordem interna (`DJANGO_ENV` antes de
    `DJANGO_DEBUG`), mas nenhuma linha de arquivo derruba uma variável que o
    deploy definiu de propósito. Sem essa separação, um `.env` esquecido com
    `DJANGO_ENV=development` sobreviveria a um `DJANGO_DEBUG=False` exportado
    no servidor — e o ambiente subiria com DEBUG ligado.
    """
    module = os.getenv("DJANGO_SETTINGS_MODULE", "")
    if module:
        # Um módulo escolhido à mão manda, inclusive o de teste (que não é
        # desenvolvimento: ele desliga DEBUG de propósito).
        environment = DEVELOPMENT if module.endswith(".development") else PRODUCTION
        return environment, "DJANGO_SETTINGS_MODULE"

    for source in (os.environ, read_env_files()):
        env_name = str(source.get("DJANGO_ENV") or "").strip().lower()
        if env_name:
            environment = DEVELOPMENT if env_name in DEVELOPMENT_ENV_NAMES else PRODUCTION
            return environment, "DJANGO_ENV"

        debug_value = source.get("DJANGO_DEBUG")
        if debug_value is not None and str(debug_value).strip():
            environment = DEVELOPMENT if parse_bool(debug_value, default=True) else PRODUCTION
            return environment, "DJANGO_DEBUG"

    # Nada informado: a máquina de quem acabou de clonar o projeto.
    return DEVELOPMENT, "default"


def read_env_files():
    global _env_file_cache
    if _env_file_cache is not None:
        return _env_file_cache

    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    values = {}

    # O `.env` do backend vem depois e vence: é o arquivo local da máquina de
    # quem desenvolve, sobrepondo o compartilhado da raiz.
    for env_file in (project_dir / ".env", backend_dir / ".env"):
        if not env_file.exists():
            continue
        values.update(parse_env_file(env_file))

    _env_file_cache = values
    return values


def parse_env_file(path):
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_bool(value, default=False):
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default
