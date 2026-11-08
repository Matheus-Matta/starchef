"""Exportar os XML das notas de um período num ZIP (o pedido do contador).

Poucas notas com o XML já guardado saem na hora, na própria requisição. O
resto vai para o worker (`BulkJob`): montar o ZIP de um mês inteiro, ou
buscar o XML de cada nota na Focus, passa fácil do tempo de uma requisição. O
aviso chega pelo sino, que leva à página da exportação com o botão de baixar.

O arquivo é TEMPORÁRIO: some 24 h depois (`exportacao_xml_arquivo.py`). O XML
de verdade continua na nota — o ZIP é só a entrega.
"""
import tempfile
import zipfile

from django.utils import timezone
from rest_framework import serializers

from apps.invoices.exportacao_xml_arquivo import VALIDADE, salvar
from apps.invoices.models import FiscalConfig, Invoice
from apps.invoices.xml_da_nota import XmlIndisponivel, nome_do_arquivo, xml_da_nota

#: Até aqui, e só com o XML já guardado, o ZIP sai na hora.
LIMITE_NA_HORA = 50
MAIOR_PERIODO_EM_DIAS = 366

_PASTA_POR_STATUS = {
    Invoice.STATUS_ISSUED: "autorizadas",
    Invoice.STATUS_CANCELLED: "canceladas",
    Invoice.STATUS_PENDING: "pendentes",
    Invoice.STATUS_ERROR: "com-erro",
}


class FiltroExportacao(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    # Autorizadas e canceladas por padrão: é o que o contador escritura.
    status = serializers.ListField(
        child=serializers.ChoiceField(choices=list(_PASTA_POR_STATUS)),
        required=False, allow_empty=False,
    )
    document_model = serializers.ChoiceField(
        choices=[FiscalConfig.MODEL_NFCE, FiscalConfig.MODEL_NFE], required=False, allow_blank=True,
    )
    restaurant = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, data):
        if data["date_to"] < data["date_from"]:
            raise serializers.ValidationError({"date_to": "A data final vem antes da inicial."})
        if (data["date_to"] - data["date_from"]).days > MAIOR_PERIODO_EM_DIAS:
            raise serializers.ValidationError(
                {"date_to": f"Exporte no máximo {MAIOR_PERIODO_EM_DIAS} dias de cada vez."}
            )
        return data

    def payload(self, escopo):
        """Os filtros como o worker os recebe (JSON), com o recorte do usuário."""
        dados = self.validated_data
        return {
            "date_from": dados["date_from"].isoformat(),
            "date_to": dados["date_to"].isoformat(),
            "status": dados.get("status") or [Invoice.STATUS_ISSUED, Invoice.STATUS_CANCELLED],
            "document_model": dados.get("document_model") or "",
            "restaurant": str(dados["restaurant"]) if dados.get("restaurant") else "",
            "escopo": escopo,
        }


def notas_do_filtro(payload):
    """As notas COM XML do filtro. `escopo` é o restaurante do usuário que pediu.

    `None` = administrador (a conta inteira); `""` = usuário sem restaurante,
    que no resto da API também não vê nota nenhuma.
    """
    escopo = payload.get("escopo")
    if escopo == "":
        return Invoice.objects.none()
    notas = Invoice.objects.filter(
        issued_at__date__gte=payload["date_from"],
        issued_at__date__lte=payload["date_to"],
        status__in=payload["status"],
    ).exclude(xml_content="")
    for campo, valor in (("document_model", payload.get("document_model")),
                         ("restaurant_id", payload.get("restaurant")), ("restaurant_id", escopo)):
        if valor:
            notas = notas.filter(**{campo: valor})
    return notas.order_by("issued_at", "number")


def cabe_na_hora(notas):
    """Poucas, e nenhuma dependendo de buscar o XML fora (Focus)."""
    return notas.count() <= LIMITE_NA_HORA and not notas.exclude(xml_content__startswith="<").exists()


def montar_zip(notas, destino):
    """Escreve o ZIP em `destino`. Devolve (quantos XML entraram, falhas)."""
    total, falhas = 0, []
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
        for nota in notas.iterator():
            try:
                conteudo = xml_da_nota(nota)
            except XmlIndisponivel as exc:
                falhas.append({"numero": nota.number, "chave": nota.access_key, "motivo": str(exc)})
                continue
            zip_.writestr(f"{_PASTA_POR_STATUS.get(nota.status, nota.status)}/{nome_do_arquivo(nota)}", conteudo)
            total += 1
        if falhas:
            linhas = [f"Nota {f['numero']} ({f['chave'] or 'sem chave'}): {f['motivo']}" for f in falhas]
            zip_.writestr("falhas.txt", "\n".join(linhas) + "\n")
    return total, falhas


def nome_do_zip(payload):
    return f"notas-fiscais_{payload['date_from']}_a_{payload['date_to']}.zip"


def run_xml_export_job(job):
    """Monta e guarda o ZIP. O `payload` some ao terminar; o nome vai no resultado."""
    notas = notas_do_filtro(job.payload)
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as temporario:
        total, falhas = montar_zip(notas, temporario)
        resultado = {"total": total, "quantidade_de_falhas": len(falhas), "falhas": falhas[:20],
                     "nome": nome_do_zip(job.payload)}
        if not total:
            return resultado
        temporario.seek(0)
        resultado["arquivo"] = salvar(job, temporario)
    resultado["expira_em"] = (timezone.now() + VALIDADE).isoformat()
    return resultado


def resumo(job):
    """Título, corpo, se há aviso e a rota — para a notificação do sino."""
    resultado = job.result or {}
    rota = f"/notas-fiscais/exportar-xml/{job.pk}"
    falhas = resultado.get("quantidade_de_falhas", 0)
    if not resultado.get("total"):
        motivo = f"{falhas} nota(s) sem XML disponível." if falhas else "Nenhuma nota com XML no período."
        return "Exportação de XML sem arquivo", motivo, True, rota
    corpo = f"{resultado['total']} XML(s) no ZIP. Baixe em até 24 horas: depois o arquivo é apagado."
    if falhas:
        corpo += f" {falhas} nota(s) ficaram de fora (veja falhas.txt)."
    return "Exportação de XML pronta", corpo, bool(falhas), rota
