"""Retransmite notas fiscais em contingencia (tpEmis=9) para o provider real.

Uma nota cai em contingencia quando o provider (SEFAZ direta ou um integrador
como Focus NFe) estava indisponivel no momento da venda — o DANFE ja foi
impresso normalmente, com o aviso de contingencia, mas a nota ainda precisa
ser transmitida quando a conexao voltar. Este comando tenta de novo.

    python manage.py reprocess_pending_invoices

Sem agendamento automatico ainda (Celery beat) — rode manualmente ou agende
por fora enquanto a frequencia ideal nao e definida.
"""
from django.core.management.base import BaseCommand

from apps.invoices.services import reprocess_pending_fiscal_invoices


class Command(BaseCommand):
    help = "Retransmite notas fiscais em contingencia (tpEmis=9) para o provider configurado."

    def handle(self, *args, **options):
        retried, issued = reprocess_pending_fiscal_invoices()
        self.stdout.write(self.style.SUCCESS(f"{retried} nota(s) em contingencia verificada(s), {issued} autorizada(s) agora."))
