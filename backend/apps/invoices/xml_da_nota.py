"""O XML de uma nota, venha ele de onde vier.

A ACBrLib devolve o XML assinado e ele fica inteiro em `xml_content`. A Focus
devolve só o CAMINHO do arquivo no servidor dela (`caminho_xml_nota_fiscal`) e
é isso que `apply_response` grava no mesmo campo. Quem baixa não precisa saber
a diferença: este módulo resolve as duas.
"""
import requests


class XmlIndisponivel(Exception):
    """A nota não tem XML para entregar, com o motivo pronto para a tela.

    `status`: 404 quando o XML não existe; 502 quando a Focus, que o guarda,
    não o entregou — a nota tem XML, quem falhou foi a busca.
    """

    def __init__(self, mensagem, status=404):
        super().__init__(mensagem)
        self.status = status


def xml_da_nota(invoice):
    conteudo = (invoice.xml_content or "").strip()
    if not conteudo:
        raise XmlIndisponivel(
            "Esta nota ainda não tem XML: ele só existe depois que a nota é assinada ou autorizada."
        )
    if conteudo.startswith("<"):
        return conteudo
    return _baixar_da_focus(invoice, conteudo)


def nome_do_arquivo(invoice):
    if invoice.access_key:
        return f"{invoice.access_key}.xml"
    return f"nota-serie{invoice.series or 0}-{invoice.number or invoice.pk}.xml"


def _baixar_da_focus(invoice, caminho):
    from apps.invoices.providers import FiscalProviderError, FocusNfeProvider

    provedor = FocusNfeProvider()
    try:
        config = provedor._config_for(invoice)
        url = caminho if caminho.startswith("http") else f"{provedor._base_url(config)}/{caminho.lstrip('/')}"
        resposta = requests.get(url, auth=(provedor._token(config), ""), timeout=provedor._timeout(config))
    except FiscalProviderError as exc:
        raise XmlIndisponivel(f"Não foi possível localizar o XML na Focus: {exc}", 502) from exc
    except requests.RequestException as exc:
        raise XmlIndisponivel(f"A Focus não respondeu ao pedido do XML: {exc}", 502) from exc
    if resposta.status_code != 200 or not resposta.text.lstrip().startswith("<"):
        raise XmlIndisponivel(
            f"A Focus não entregou o XML da nota {invoice.number} (HTTP {resposta.status_code}).", 502
        )
    return resposta.text
