"""
Armazenamento de mídia: um lugar só decide onde o arquivo é gravado.

Foto de produto, logo do restaurante, imagem do storefront — todas passam pelo
mesmo `default_storage`, e é este módulo que responde por ele. Sem essa
centralização, cada campo `FileField` acabaria com a própria configuração e a
migração para o S3 viraria uma caça a `upload_to` espalhados.

**A regra que este módulo existe para cumprir:** falta de credencial de S3
NUNCA derruba o processo. O servidor sobe, o admin abre, a API responde
leitura, o healthcheck passa. O erro aparece só quando alguém tenta *gravar*
uma imagem — e aparece como resposta HTTP, com o nome das variáveis que estão
faltando, não como um traceback de `NoCredentialsError` vindo do boto3.

O motivo é operacional: um deploy com uma variável esquecida deve degradar o
upload de imagem, não tirar o sistema inteiro do ar. Restaurante que não
consegue vender porque faltou a chave do bucket é um estrago muito maior do que
restaurante que não consegue trocar a foto do prato.

Como escolhe o destino:

- `AWS_STORAGE_BUCKET_NAME` vazio → disco local (`MEDIA_ROOT`), servido em
  `MEDIA_URL`. É o modo de desenvolvimento e o padrão de quem ainda não
  contratou storage de objetos;
- `AWS_STORAGE_BUCKET_NAME` preenchido → S3/R2, via `django-storages`.

A decisão acontece na PRIMEIRA operação de arquivo, não no import: em produção
sem credencial o processo precisa subir do mesmo jeito.
"""
import logging
import threading

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.functional import LazyObject

from apps.core.exceptions import MediaStorageUnavailable

logger = logging.getLogger("core.storage")

MODE_LOCAL = "local"
MODE_S3 = "s3"

# Sem estas o upload não sai do lugar. Região e endpoint têm padrão utilizável
# (a AWS assume `us-east-1`; o R2 exige endpoint, mas isso é erro de conexão e
# vem com mensagem própria do boto3).
REQUIRED_S3_SETTINGS = ("AWS_STORAGE_BUCKET_NAME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")


class MediaStorageService:
    """Fonte única de verdade sobre onde e se é possível gravar mídia.

    Instanciado uma vez (`media_storage`, no fim do módulo). Não guarda estado
    além do backend já construído — as settings são lidas a cada consulta, para
    que `override_settings` nos testes tenha efeito.
    """

    def __init__(self):
        self._backend = None
        self._lock = threading.Lock()

    # ── Diagnóstico ──────────────────────────────────────────────────────────

    @property
    def mode(self):
        """`"s3"` quando há bucket configurado; `"local"` caso contrário."""
        return MODE_S3 if self._setting("AWS_STORAGE_BUCKET_NAME") else MODE_LOCAL

    @property
    def missing_settings(self):
        """Variáveis obrigatórias que estão vazias (só faz sentido no modo S3)."""
        if self.mode == MODE_LOCAL:
            return []
        return [name for name in REQUIRED_S3_SETTINGS if not self._setting(name)]

    @property
    def is_ready(self):
        """Dá para gravar agora?"""
        if self.mode == MODE_LOCAL:
            return True
        return not self.missing_settings and _storages_installed()

    @property
    def unavailable_reason(self):
        """Frase pronta para o usuário — vazia quando está tudo certo."""
        if self.is_ready:
            return ""
        if self.missing_settings:
            return (
                "O armazenamento de imagens não está configurado: falta definir "
                + ", ".join(self.missing_settings)
                + "."
            )
        return (
            "O armazenamento de imagens está configurado para S3, mas a biblioteca "
            "django-storages não está instalada neste servidor."
        )

    def describe(self):
        """Resumo para logs, `manage.py check` e telas de diagnóstico."""
        return {
            "mode": self.mode,
            "ready": self.is_ready,
            "bucket": self._setting("AWS_STORAGE_BUCKET_NAME") or None,
            "endpoint": self._setting("AWS_S3_ENDPOINT_URL") or None,
            "custom_domain": self._setting("AWS_S3_CUSTOM_DOMAIN") or None,
            "media_url": self._setting("MEDIA_URL"),
            "missing_settings": self.missing_settings,
            "reason": self.unavailable_reason,
        }

    # ── Gravação ─────────────────────────────────────────────────────────────

    def ensure_writable(self):
        """Levanta `MediaStorageUnavailable` (503) se não dá para gravar.

        Chamada ANTES de tocar no boto3, para o cliente receber uma mensagem
        que diz o que fazer em vez de um erro de credencial da AWS.
        """
        if self.is_ready:
            return
        raise MediaStorageUnavailable(self.unavailable_reason)

    # ── Backend ──────────────────────────────────────────────────────────────

    def get_backend(self):
        """O `Storage` concreto, construído uma vez por processo."""
        if self._backend is None:
            with self._lock:
                if self._backend is None:
                    self._backend = self.build_backend()
        return self._backend

    def build_backend(self):
        if self.mode == MODE_LOCAL:
            return FileSystemStorage()

        if not self.is_ready:
            # Configurado para S3 mas sem como usá-lo. Devolver o disco local
            # aqui seria pior do que falhar: em produção o container é efêmero,
            # o upload "daria certo" e o arquivo sumiria no próximo deploy.
            logger.warning("Armazenamento de mídia indisponível: %s", self.unavailable_reason)
            return UnavailableMediaStorage()

        return GuardedS3Storage()

    def reset(self):
        """Esquece o backend construído — usado nos testes ao trocar settings."""
        with self._lock:
            self._backend = None

    @staticmethod
    def _setting(name):
        return getattr(settings, name, "") or ""


def _storages_installed():
    try:
        import storages.backends.s3  # noqa: F401
    except ImportError:
        return False
    return True


class UnavailableMediaStorage(Storage):
    """Destino de mídia que existe só para recusar gravações com clareza.

    Leitura e `url()` degradam em silêncio (string vazia, `False`) porque uma
    imagem faltando não pode derrubar a listagem de produtos inteira; a
    gravação, essa sim, falha alto.
    """

    def _open(self, name, mode="rb"):
        raise MediaStorageUnavailable(media_storage.unavailable_reason)

    def _save(self, name, content):
        raise MediaStorageUnavailable(media_storage.unavailable_reason)

    def delete(self, name):
        return None

    def exists(self, name):
        return False

    def size(self, name):
        return 0

    def url(self, name):
        return ""

    def listdir(self, path):
        return [], []


def _build_guarded_s3_storage():
    """Cria a classe do S3 só quando `django-storages` existe.

    A classe precisa herdar de `S3Storage`, e o import dele quebra quando a
    biblioteca não está instalada — o que aconteceria no import deste módulo,
    justamente o momento em que nada pode quebrar.
    """
    from storages.backends.s3 import S3Storage

    class _GuardedS3Storage(S3Storage):
        """S3 com as falhas traduzidas para uma resposta HTTP legível."""

        def _save(self, name, content):
            media_storage.ensure_writable()
            try:
                return super()._save(name, content)
            except MediaStorageUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - boto3 tem uma árvore de erros enorme
                # Credencial inválida, bucket inexistente, rede fora: tudo isso
                # vira 500 com traceback se deixar passar. O upload de uma foto
                # não merece isso — vira 503 com a causa no texto.
                logger.exception("Falha ao gravar mídia no S3", extra={"name": name})
                raise MediaStorageUnavailable(
                    f"Não foi possível enviar a imagem para o armazenamento: {exc}"
                ) from exc

    return _GuardedS3Storage


class GuardedS3Storage(LazyObject):
    """Fachada para o S3 real, montada na primeira utilização."""

    def _setup(self):
        self._wrapped = _build_guarded_s3_storage()()


class MediaStorage(Storage):
    """O `STORAGES["default"]` do projeto — uma fachada sobre o backend real.

    Delega cada chamada ao backend que o serviço decidir NO MOMENTO da chamada.
    Isso cumpre as duas promessas do módulo de uma vez:

    - o backend concreto só é construído na primeira operação de arquivo, então
      importar as settings ou subir o processo nunca depende de credencial;
    - trocar a configuração em runtime passa a valer (é o que os testes fazem,
      e o que `manage.py` faria num comando que ajusta o destino).

    A delegação é escrita à mão, método a método, porque `FileField` exige uma
    instância de `Storage` de verdade (`isinstance`) — um proxy genérico com
    `__getattr__` seria recusado na definição do próprio campo.
    """

    @property
    def _backend(self):
        return media_storage.get_backend()

    # ── Escrita ──────────────────────────────────────────────────────────────
    def save(self, name, content, max_length=None):
        return self._backend.save(name, content, max_length=max_length)

    def delete(self, name):
        return self._backend.delete(name)

    # ── Leitura ──────────────────────────────────────────────────────────────
    def open(self, name, mode="rb"):
        return self._backend.open(name, mode)

    def exists(self, name):
        return self._backend.exists(name)

    def listdir(self, path):
        return self._backend.listdir(path)

    def size(self, name):
        return self._backend.size(name)

    def url(self, name):
        return self._backend.url(name)

    def path(self, name):
        return self._backend.path(name)

    # ── Nomes ────────────────────────────────────────────────────────────────
    def generate_filename(self, filename):
        return self._backend.generate_filename(filename)

    def get_valid_name(self, name):
        return self._backend.get_valid_name(name)

    def get_alternative_name(self, file_root, file_ext):
        return self._backend.get_alternative_name(file_root, file_ext)

    def get_available_name(self, name, max_length=None):
        return self._backend.get_available_name(name, max_length=max_length)

    # ── Datas ────────────────────────────────────────────────────────────────
    def get_accessed_time(self, name):
        return self._backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self._backend.get_created_time(name)

    def get_modified_time(self, name):
        return self._backend.get_modified_time(name)


media_storage = MediaStorageService()
