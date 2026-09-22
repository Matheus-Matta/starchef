"""O segredo de emissão desta loja: o que ela tem, ou o que a nuvem empresta.

A loja precisa de três coisas para emitir, e nenhuma delas viaja no payload de
sincronização (`catalog.py` as mantém em `exclude_fields`):

* o **token do provedor**, para a Focus aceitar a transmissão;
* o **CSC**, para montar o QR Code da NFC-e no terminal;
* o **certificado A1** e a senha, para a assinatura local quando o Comunicador
  estiver em uso.

O motivo de não viajarem está em `services/credentials.py`: o tráfego é cifrado,
mas o evento é gravado em `SyncEvent.payload`, um JSONField em texto puro, nos
dois bancos e em todo backup dos dois — para sempre, porque evento não se apaga.
A cifra protege o cabo, não o disco.

O canal certo já existia inteiro — endpoint na nuvem, cliente na loja, envelope
AES-GCM amarrado ao id do nó, cache só em memória com prazo. **Só ninguém o
chamava.** Este módulo é o fio que faltava.

**Hash não serve, e não é questão de rigor.** Hash é de mão única: o CSC precisa
ser o valor original para entrar no cálculo do QR, e o token do provedor vai
como credencial no cabeçalho HTTP. Guardar o resumo deles seria guardar algo
que não emite nada.

**Guardar cifrado no disco da loja também não.** Resolveria a leitura casual e
não o que importa: o segredo passaria a morar num computador dentro do
restaurante, e revogar o acesso não o apagaria de lá. Emprestado, ele morre
junto com o token do nó — que é o que revogação precisa significar.
"""
import logging

logger = logging.getLogger(__name__)


class SegredosDeEmissao:
    """O que vale AGORA para esta configuração: local primeiro, nuvem depois.

    O valor gravado na própria loja tem precedência sempre. Uma instalação que
    já foi provisionada à mão continua funcionando igual, e a nuvem só é
    consultada para o que está faltando.
    """

    def __init__(self, config, emprestado=None):
        self._config = config
        self._emprestado = emprestado or {}

    def _valor(self, campo):
        proprio = (getattr(self._config, campo, "") or "").strip()
        if proprio:
            return proprio
        return (self._emprestado.get(campo) or "").strip()

    @property
    def csc_id(self):
        return self._valor("csc_id")

    @property
    def csc_token(self):
        return self._valor("csc_token")

    @property
    def certificate_password(self):
        return self._valor("certificate_password")

    @property
    def certificate_base64(self):
        """O A1 em base64 — do arquivo local, ou emprestado da nuvem."""
        from apps.invoices.certificate_data import certificate_base64

        proprio = certificate_base64(self._config)
        if proprio:
            return proprio
        return (self._emprestado.get("certificate_base64") or "").strip()

    def token_do_provedor(self, environment):
        """O token da Focus para ESTE ambiente.

        Homologação e produção têm tokens diferentes, e usar o da produção em
        homologação não devolve erro de credencial: devolve nota de verdade.
        """
        from apps.invoices.models import FiscalConfig

        campo = (
            "focus_token_production"
            if environment == FiscalConfig.ENV_PRODUCTION
            else "focus_token_homologation"
        )
        return self._valor(campo) or self._valor("provider_token")


def segredos_de(config, *, pedir_a_nuvem=True):
    """Os segredos desta configuração, emprestando da nuvem o que faltar.

    Nunca levanta: quem chama está no caminho de uma venda. Sem o empréstimo,
    devolve só o que a loja tem — e a recusa que vem depois é a mesma de
    sempre, dita pelo provedor, com o motivo certo.
    """
    if not pedir_a_nuvem or not _falta_alguma_coisa(config):
        return SegredosDeEmissao(config)

    from apps.synchronization.services import credentials_client

    pacote = credentials_client.obter()
    if pacote is None:
        logger.info(
            "fiscal: a nuvem não devolveu credencial de emissão; seguindo com o "
            "que a loja tem gravado."
        )
        return SegredosDeEmissao(config)

    # O pacote é da loja DESTE nó. Entregar o de outra configuração seria
    # assinar a nota com o certificado do cliente errado.
    if str(pacote.get("fiscal_config_id") or "") not in ("", str(config.id)):
        logger.warning(
            "fiscal: a nuvem devolveu credencial de outra configuração (%s); "
            "ignorando.", pacote.get("fiscal_config_id"),
        )
        return SegredosDeEmissao(config)
    return SegredosDeEmissao(config, pacote)


def _falta_alguma_coisa(config):
    """Vale a pena ir à nuvem?

    Só quando algo realmente falta. Uma loja com tudo gravado não faz uma
    chamada de rede por venda.
    """
    tem_token = bool(
        (config.focus_token_production or "").strip()
        or (config.focus_token_homologation or "").strip()
        or (config.provider_token or "").strip()
    )
    tem_csc = bool((config.csc_id or "").strip() and (config.csc_token or "").strip())
    return not (tem_token and tem_csc)
