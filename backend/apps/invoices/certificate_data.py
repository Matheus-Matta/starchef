import base64
import logging

logger = logging.getLogger(__name__)


def read_certificate_bytes(config):
    """Lê o A1 canônico, seja pelo storage atual ou pela referência legada.

    Arquivo cadastrado mas AUSENTE neste servidor (enviado em outro, volume de
    mídia recriado, container sem a pasta) conta como "sem certificado aqui":
    quem chama segue para o empréstimo da nuvem (`emission_secrets.py`). Antes
    a leitura estourava "No such file or directory" e a nota parava em
    "aguardando SEFAZ" sem nunca chegar a ele.
    """
    if config.certificate_file:
        try:
            config.certificate_file.open("rb")
        except FileNotFoundError:
            logger.warning(
                "Certificado A1 cadastrado (%s) mas ausente neste servidor; "
                "segue para o emprestado da nuvem, se houver.",
                getattr(config.certificate_file, "name", ""),
            )
        else:
            try:
                return config.certificate_file.read()
            finally:
                config.certificate_file.close()
    if config.certificate_ref:
        try:
            with open(config.certificate_ref, "rb") as certificate:
                return certificate.read()
        except FileNotFoundError:
            logger.warning("Certificado A1 legado %s ausente neste servidor.", config.certificate_ref)
    return b""


def certificate_base64(config):
    content = read_certificate_bytes(config)
    return base64.b64encode(content).decode() if content else ""
