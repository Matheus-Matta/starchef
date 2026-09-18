"""`manage.py sync_issue_ticket` — emite um bilhete de matrícula de uso único.

Rode na NUVEM, no momento em que alguém vai instalar o backend de uma loja. O
código aparece UMA vez, na saída deste comando: não há como recuperá-lo depois,
porque o que fica gravado é o hash.

    manage.py sync_issue_ticket --account <uuid> --label "Loja Centro"

O código emitido entra no lugar do `SYNC_ENROLL_SECRET` da loja. O segredo fixo
continua funcionando — instalação que já existe não quebra —, mas ele não
expira e não diz quem o usou, e o bilhete existe para aposentá-lo.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account
from apps.synchronization.services import enrollment, guard


class Command(BaseCommand):
    help = "Emite um bilhete de matrícula de uso único para uma conta."

    def add_arguments(self, parser):
        parser.add_argument("--account", required=True, help="UUID da conta")
        parser.add_argument("--restaurant", default="", help="UUID do restaurante (opcional)")
        parser.add_argument("--label", default="", help="Para que serve este bilhete")
        parser.add_argument(
            "--minutes", type=int, default=None,
            help="Validade em minutos (padrão: 30)",
        )

    def handle(self, *args, **options):
        guard.ensure_environment()

        conta = Account.objects.filter(pk=options["account"]).first()
        if conta is None:
            raise CommandError(f"Conta {options['account']} não encontrada.")

        restaurante = None
        if options["restaurant"]:
            from apps.restaurants.models import Restaurant

            restaurante = Restaurant.all_objects.filter(
                pk=options["restaurant"], account=conta
            ).first()
            if restaurante is None:
                raise CommandError(
                    f"Restaurante {options['restaurant']} não encontrado nesta conta."
                )

        bilhete, codigo = enrollment.emitir_bilhete(
            conta=conta,
            restaurante=restaurante,
            label=options["label"],
            validade_minutos=options["minutes"],
        )

        self.stdout.write(self.style.SUCCESS("Bilhete emitido."))
        self.stdout.write(f"  conta:    {conta.name} ({conta.id})")
        if restaurante is not None:
            self.stdout.write(f"  loja:     {restaurante} ({restaurante.id})")
        self.stdout.write(f"  validade: até {bilhete.expires_at:%d/%m/%Y %H:%M} UTC")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  SYNC_ENROLL_SECRET=" + codigo))
        self.stdout.write("")
        self.stdout.write(
            "Este código aparece uma vez só. Vale para UMA matrícula e depois morre — "
            "reapresentá-lo é recusado, mesmo dentro do prazo."
        )
