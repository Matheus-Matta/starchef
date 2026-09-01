"""Resume quanto tempo a NFC-e leva para ser autorizada.

Existe para responder UMA pergunta antes de decidir arquitetura: o cliente
chega a esperar pelo cupom fiscal, ou a SEFAZ responde na hora?

A resposta muda o caminho. Se autoriza em segundos, basta o terminal aguardar
um instante e reconsultar. Se demora com frequencia, ai vale assumir a
numeracao e preparar a contingencia de verdade — trabalho bem maior, e que so
se justifica com numero na mao.

    python manage.py fiscal_timing --days 30
"""
from django.core.management.base import BaseCommand

from apps.invoices.models import Invoice


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


def _format_ms(value):
    if value is None:
        return "-"
    return f"{value / 1000:.1f}s" if value >= 1000 else f"{value}ms"


class Command(BaseCommand):
    help = "Resume o tempo de autorizacao das NFC-e emitidas."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Janela em dias (padrao: 30).")
        parser.add_argument("--account", default=None, help="Limita a uma conta.")

    def handle(self, *args, **options):
        from django.utils import timezone
        from datetime import timedelta

        since = timezone.now() - timedelta(days=options["days"])
        queryset = Invoice.all_objects.filter(created_at__gte=since)
        if options["account"]:
            queryset = queryset.filter(account_id=options["account"])

        emit_times = []
        authorized_times = []
        immediate = 0
        delayed = 0
        never = 0
        states = {}

        for invoice in queryset.only("fiscal_payload", "status"):
            timing = (invoice.fiscal_payload or {}).get("timing") or {}
            if timing.get("emit_ms") is not None:
                emit_times.append(timing["emit_ms"])
            state = timing.get("emit_state") or "-"
            states[state] = states.get(state, 0) + 1

            authorized_after = timing.get("authorized_after_ms")
            if authorized_after is None:
                if invoice.status != Invoice.STATUS_ISSUED:
                    never += 1
                continue
            authorized_times.append(authorized_after)
            # "Na hora" = ja voltou autorizada da propria chamada de emissao.
            if state == "authorized":
                immediate += 1
            else:
                delayed += 1

        total = len(emit_times)
        self.stdout.write(f"Notas na janela de {options['days']} dias: {total}")
        if not total:
            self.stdout.write("Nenhuma emissao registrada com medicao ainda.")
            return

        self.stdout.write("")
        self.stdout.write("Duracao da CHAMADA de emissao (quanto o provedor demora a responder):")
        self.stdout.write(f"  mediana {_format_ms(_percentile(emit_times, 0.5))}")
        self.stdout.write(f"  p90     {_format_ms(_percentile(emit_times, 0.9))}")
        self.stdout.write(f"  pior    {_format_ms(max(emit_times))}")

        self.stdout.write("")
        self.stdout.write("Como a nota voltou da emissao:")
        for state, count in sorted(states.items(), key=lambda item: -item[1]):
            share = count * 100 / total
            self.stdout.write(f"  {state:<24} {count:>5}  ({share:.1f}%)")

        self.stdout.write("")
        self.stdout.write("Tempo ate a AUTORIZACAO (o que o cliente esperaria pelo cupom):")
        if authorized_times:
            self.stdout.write(f"  mediana {_format_ms(_percentile(authorized_times, 0.5))}")
            self.stdout.write(f"  p90     {_format_ms(_percentile(authorized_times, 0.9))}")
            self.stdout.write(f"  pior    {_format_ms(max(authorized_times))}")
        else:
            self.stdout.write("  nenhuma nota autorizada na janela")
        self.stdout.write(f"  autorizadas na propria emissao: {immediate}")
        self.stdout.write(f"  autorizadas depois:             {delayed}")
        self.stdout.write(f"  ainda nao autorizadas:          {never}")

        self.stdout.write("")
        if delayed == 0 and never == 0:
            self.stdout.write(
                "Leitura: todas autorizaram na propria emissao. Esperar e "
                "reconsultar no terminal resolve — contingencia nao se justifica."
            )
        else:
            share = (delayed + never) * 100 / total
            self.stdout.write(
                f"Leitura: {share:.1f}% das notas nao sairam autorizadas na emissao. "
                "Acima de poucos por cento, vale assumir a numeracao e preparar "
                "a contingencia."
            )
