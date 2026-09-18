"""Registro dos models sincronizáveis.

Cada entrada responde às seis perguntas que o plano exige de todo model:
serializador, dependências, política de conflito, escopo, se entra no
bootstrap e se sincroniza. O que NÃO está aqui não sincroniza — e o comando
`manage.py sync_check_registry` falha o deploy quando aparece um model novo
sem decisão explícita (ver `decisions.py`).
"""
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from apps.synchronization.constants import ConflictResolution


@dataclass(frozen=True)
class SyncEntry:
    """A declaração de um model sincronizável."""

    #: Nome lógico que viaja no evento. Nunca muda depois de publicado.
    entity_type: str
    #: "app_label.ModelName".
    model_label: str
    #: Quem vence quando os dois lados mexeram no mesmo registro.
    conflict_policy: str = ConflictResolution.CLOUD_WINS
    #: Entidades que precisam existir antes desta (ordem de carga).
    dependencies: tuple = ()
    #: Entra na carga de "dados essenciais"?
    include_in_bootstrap: bool = True
    #: "account" (uma cópia por conta) ou "store" (por restaurante).
    scope: str = "account"
    #: Direção permitida: "cloud_to_local", "local_to_cloud" ou "both".
    flow: str = "both"
    #: Campos que nunca viajam (segredo, cache, derivado).
    exclude_fields: tuple = ()
    #: Campos que o destino NUNCA sobrescreve (ex.: ajuste local de impressora).
    local_only_fields: tuple = ()
    #: Append-only: o destino insere, mas nunca atualiza nem apaga.
    immutable: bool = False
    #: Entra na carga para a LOJA mesmo sendo `local_to_cloud`.
    #:
    #: Existe para o estado vivo do salão. Pedido e sessão de caixa nascem na
    #: loja e sobem — mas uma loja que está ASSUMINDO a operação começa com o
    #: banco vazio e herdaria as mesas ocupadas sem nenhuma comanda, e os
    #: terminais sem a sessão de caixa que já está aberta. A direção contínua
    #: continua sendo só para cima; o que muda é a semeadura inicial.
    seed_to_local: bool = False
    #: Filtro aplicado SÓ na carga essencial, como kwargs de `QuerySet.filter`.
    #:
    #: "Dados essenciais" leva o que a loja precisa para abrir a porta e
    #: atender: cadastros mais o estado vivo do salão — a comanda que está
    #: aberta, a sessão de caixa que está em turno. O histórico de meses não
    #: entra aí.
    #:
    #: "Sincronizar tudo" ignora este filtro de propósito: ali a promessa é
    #: trazer TODOS os dados da conta, e quem decide o que nunca sincroniza é
    #: `decisions.py` — auditoria, log, notificação, sessão e token.
    essential_filter: dict = field(default_factory=dict)

    @property
    def model(self):
        app_label, model_name = self.model_label.split(".")
        return django_apps.get_model(app_label, model_name)


@dataclass
class Registry:
    entries: dict = field(default_factory=dict)

    def register(self, entry):
        if entry.entity_type in self.entries:
            raise ValueError(f"entity_type duplicado no registro: {entry.entity_type}")
        self.entries[entry.entity_type] = entry
        return entry

    def get(self, entity_type):
        return self.entries.get(entity_type)

    def require(self, entity_type):
        entrada = self.get(entity_type)
        if entrada is None:
            raise KeyError(f"Entidade não registrada para sincronização: {entity_type}")
        return entrada

    def for_model(self, model):
        etiqueta = f"{model._meta.app_label}.{model.__name__}"
        for entrada in self.entries.values():
            if entrada.model_label == etiqueta:
                return entrada
        return None

    def registered_labels(self):
        return {entrada.model_label for entrada in self.entries.values()}

    def ordered(self, *, bootstrap_only=False):
        """Ordem topológica das entidades — dependência antes de dependente.

        É essa ordem que impede o erro clássico da carga: item de pedido
        chegando antes do pedido e quebrando a chave estrangeira.
        """
        pendentes = [
            e for e in self.entries.values() if not bootstrap_only or e.include_in_bootstrap
        ]
        resolvidas, resultado = set(), []
        while pendentes:
            avancou = False
            for entrada in list(pendentes):
                if all(dep in resolvidas or dep not in self.entries for dep in entrada.dependencies):
                    resultado.append(entrada)
                    resolvidas.add(entrada.entity_type)
                    pendentes.remove(entrada)
                    avancou = True
            if not avancou:
                nomes = ", ".join(e.entity_type for e in pendentes)
                raise ValueError(f"Ciclo de dependência entre entidades: {nomes}")
        return resultado

    def flows_to_local(self, entity_type):
        entrada = self.require(entity_type)
        return entrada.flow in ("both", "cloud_to_local")

    def flows_to_cloud(self, entity_type):
        entrada = self.require(entity_type)
        return entrada.flow in ("both", "local_to_cloud")


registry = Registry()
