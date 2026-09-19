"""`manage.py sync_check_registry` — nada fica sem decisão: nem model, nem VÍNCULO.

Roda no deploy. Ele lista o que sincroniza, o que foi excluído com motivo, e
FALHA quando aparece um model que não está em nenhuma das duas listas. É a
proteção contra o defeito silencioso do §11.3: alguém cria um model, ninguém
percebe que ele ficou de fora, e meses depois a loja opera com um cadastro que
a nuvem nunca viu.

A mesma checagem vale para campo ManyToMany, e ela nasceu de um defeito real:
`CashStation.operators` nunca viajou. O caixa chegava na loja, a pessoa
chegava, e a LIGAÇÃO entre os dois não — então nenhum operador conseguia abrir
caixa, e tudo que se olhava na tela parecia presente.

Um M2M é invisível para a checagem de model porque ele não é um model: a
tabela de ligação é criada pelo Django e nunca aparece em `get_models()`.
Por isso a segunda varredura existe.
"""
from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from apps.synchronization.decisions import EXCLUDED
from apps.synchronization.services.registry import registry

#: Apps cujos models não são dado de negócio nosso.
APPS_IGNORADOS = {"admin", "contenttypes", "sessions", "token_blacklist"}


def vinculos_sem_decisao():
    """`(entity_type, campo, alvo)` de todo M2M nem declarado nem excluído.

    A chave natural importa tanto quanto a declaração: casar por `id` num
    modelo cujo id é inteiro sequencial (o `auth.User`, por exemplo) ligaria
    o registro à pessoa ERRADA do outro lado, porque os dois bancos numeram
    independentemente. Por isso `m2m_fields` pede a chave explicitamente em
    vez de assumir `id`.
    """
    faltando = []
    for entrada in registry.ordered():
        declarados = set(entrada.m2m_fields or {})
        excluidos = set(entrada.exclude_fields or ())
        for campo in entrada.model._meta.many_to_many:
            if campo.name in declarados or campo.name in excluidos:
                continue
            faltando.append((entrada.entity_type, campo.name, campo.related_model._meta.label))
    return faltando


class Command(BaseCommand):
    help = "Confere se todo model do projeto tem decisão explícita de sincronização."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="só o veredito")

    def handle(self, *args, **options):
        import apps.synchronization.catalog  # noqa: F401  (popula o registro)

        registrados = registry.registered_labels()
        sem_decisao = []

        for model in django_apps.get_models():
            etiqueta = f"{model._meta.app_label}.{model.__name__}"
            if model._meta.app_label in APPS_IGNORADOS or model._meta.proxy:
                continue
            if etiqueta in registrados or etiqueta in EXCLUDED:
                continue
            sem_decisao.append(etiqueta)

        if not options["quiet"]:
            self._relatorio(registrados, sem_decisao)

        if sem_decisao:
            raise CommandError(
                f"{len(sem_decisao)} model(s) sem decisão de sincronização: "
                + ", ".join(sorted(sem_decisao))
                + ". Declare em apps/synchronization/catalog.py ou em decisions.py."
            )

        vinculos = vinculos_sem_decisao()
        if vinculos:
            raise CommandError(
                f"{len(vinculos)} vínculo(s) ManyToMany sem decisão: "
                + ", ".join(f"{e}.{c}" for e, c, _ in sorted(vinculos))
                + ". Um M2M não declarado NUNCA viaja, e o sintoma é o registro "
                "chegar sem a ligação — o pior formato de falha, porque a tela "
                "parece completa. Declare em `m2m_fields` (com a chave natural) "
                "ou em `exclude_fields`, se for para ficar de fora mesmo."
            )
        self.stdout.write(self.style.SUCCESS(
            f"OK: {len(registrados)} sincronizados, {len(EXCLUDED)} excluídos com motivo."
        ))

    def _relatorio(self, registrados, sem_decisao):
        self.stdout.write(self.style.MIGRATE_HEADING("\nSincronizados (ordem de carga):"))
        for entrada in registry.ordered():
            marca = "essencial" if entrada.include_in_bootstrap else "completo "
            self.stdout.write(
                f"  [{marca}] {entrada.entity_type:<22} {entrada.model_label:<34}"
                f" {entrada.flow:<15} {entrada.conflict_policy}"
            )
        self.stdout.write(self.style.MIGRATE_HEADING("\nExcluídos:"))
        for etiqueta, motivo in sorted(EXCLUDED.items()):
            self.stdout.write(f"  {etiqueta:<40} {motivo}")
        if sem_decisao:
            self.stdout.write(self.style.ERROR("\nSem decisão:"))
            for etiqueta in sorted(sem_decisao):
                self.stdout.write(self.style.ERROR(f"  {etiqueta}"))
