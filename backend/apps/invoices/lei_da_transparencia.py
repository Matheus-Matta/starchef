"""Lei 12.741/2012 (Decreto 8.264/2014): os tributos aproximados no cupom.

O documento entregue ao consumidor tem de informar o valor aproximado dos
tributos da venda. O valor nasce do percentual do perfil fiscal de cada
produto (`approx_tax_rate`, em geral tirado da tabela do IBPT pelo NCM) e vai
no XML (`vTotTrib`) e no DANFE.

A linha do DANFE só saía com valor acima de zero. Com o perfil em 0% — o
padrão de quem não preencheu —, ela sumia, e a loja descumpria a lei sem nada
avisar. Agora ela sai sempre, e o percentual zerado fica AVISADO na nota.
Avisado e não bloqueado: falta de percentual não é motivo para a SEFAZ
recusar, e travar a venda por isso seria pior que o problema.
"""
ROTULO = "TRIBUTOS TOTAIS INCIDENTES R$"
FONTE = "(LEI FEDERAL 12.741/2012)"
CHAVE_DO_AVISO = "aviso_lei_12741"


def itens_sem_percentual(invoice):
    """Descrição dos itens vendidos com tributo aproximado zerado."""
    return [
        item.description
        for item in invoice.items.all().order_by("line_number")
        if item.total_price and not item.approx_tax_value
    ]


def aviso(invoice):
    itens = itens_sem_percentual(invoice)
    if not itens:
        return None
    nomes = ", ".join(dict.fromkeys(itens))
    return (f"Tributos aproximados (Lei 12.741) em 0% no perfil fiscal de: {nomes}. O cupom sai "
            "com R$ 0,00 de tributos; preencha o percentual pelo NCM (tabela do IBPT).")


def registrar_aviso(invoice):
    """Grava (ou limpa) o aviso em `fiscal_payload`, sem bloquear a emissão."""
    payload = dict(invoice.fiscal_payload or {})
    texto = aviso(invoice)
    if texto:
        payload[CHAVE_DO_AVISO] = texto
    else:
        payload.pop(CHAVE_DO_AVISO, None)
    invoice.fiscal_payload = payload
