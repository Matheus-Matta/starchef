"""`manage.py sync_caixa` — o histórico do caixa na sincronização.

Sem opção, só lê: os eventos do caixa do período NESTE servidor, quantos em
cada estado, e os que pararam, com o motivo. Rode na loja (o que não saiu) e
na nuvem (o que chegou e não entrou).

`--reenviar` (só na loja) gera de novo os eventos das sessões do período para
a nuvem completar o histórico. Seguro de repetir: o que ela já tem é ignorado.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.services import caixa_diagnostico


class Command(BaseCommand):
    help = "Mostra onde parou o histórico do caixa na sincronização; --reenviar manda de novo (loja)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=7, help="período a olhar (padrão: 7 dias)")
        parser.add_argument("--sessao", help="uma sessão de caixa específica (UUID), para --reenviar")
        parser.add_argument("--reenviar", action="store_true",
                            help="gera de novo os eventos das sessões (rode na LOJA)")

    def handle(self, *args, **options):
        if options["reenviar"]:
            try:
                total = caixa_diagnostico.reenviar(dias=options["dias"], sessao=options.get("sessao"))
            except caixa_diagnostico.SoNaLoja as erro:
                raise CommandError(str(erro)) from erro
            self.stdout.write(self.style.SUCCESS(
                f"{total} evento(s) do caixa na fila. Acompanhe com: manage.py sync_caixa"
            ))
            return
        self._relatorio(caixa_diagnostico.diagnostico(dias=options["dias"]), options["dias"])

    def _relatorio(self, dados, dias):
        escrever = self.stdout.write
        escrever(self.style.MIGRATE_HEADING(f"Eventos do caixa nos últimos {dias} dia(s)"))
        if not dados["contagem"]:
            escrever("  nenhum evento do caixa neste servidor no período")
        for (direcao, tipo, estado), quantos in sorted(dados["contagem"].items()):
            escrever(f"  {direcao:<8} {tipo:<14} {estado:<13} {quantos}")

        escrever(self.style.MIGRATE_HEADING("Parados (não aplicados / não confirmados)"))
        if not dados["parados"]:
            escrever("  nenhum")
        for evento in dados["parados"]:
            escrever(
                f"  {evento['direction']:<8} {evento['entity_type']:<14} {evento['entity_id']} "
                f"{evento['status']} tentativas={evento['attempts']}"
            )
            if evento["last_error"]:
                escrever(f"      motivo: {evento['last_error'][:300]}")

        escrever(self.style.MIGRATE_HEADING("Conflitos"))
        for conflito in dados["conflitos"] or [{"entity_type": "nenhum", "entity_id": "", "status": ""}]:
            escrever(f"  {conflito['entity_type']:<14} {conflito['entity_id']} {conflito['status']}")

        escrever(self.style.MIGRATE_HEADING("Descartados"))
        for descarte in dados["descartes"] or [{"entity_type": "nenhum", "entity_id": "", "motivo": ""}]:
            escrever(f"  {descarte['entity_type']:<14} {descarte['entity_id']} {descarte['motivo']}")
