"""Fases 1-3 do plano de estoque: entradas, lotes, FIFO/FEFO e conferencia.

Ver `docs/IMPLEMENTACAO_ESTOQUE.md`, secoes 5.1, 11, 14 e 27.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.menu.models import Ingredient
from apps.stock.lots import (
    cancel_stock_entry,
    post_stock_entry,
    post_stock_exit,
    scan_exit_label,
    suggest_exit_lots,
)
from apps.stock.models import (
    StockEntry,
    StockEntryItem,
    StockExit,
    StockExitItem,
    StockLocation,
    StockLot,
    StockMovement,
    StockSettings,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant(account):
    with tenant_context(account):
        yield


@pytest.fixture
def location(account, restaurant, branch, manager_user):
    return StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Deposito",
        created_by=manager_user, updated_by=manager_user,
    )


@pytest.fixture
def insumo(account, restaurant, branch, manager_user):
    return Ingredient.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Macarrao",
        unit="g", created_by=manager_user, updated_by=manager_user,
    )


def _entry(account, restaurant, branch, user, location, **kwargs):
    return StockEntry.objects.create(
        account=account, restaurant=restaurant, branch=branch, location=location,
        effective_date=kwargs.pop("effective_date", timezone.localdate()),
        created_by=user, updated_by=user, **kwargs,
    )


def _entry_item(entry, ingredient, user, **kwargs):
    return StockEntryItem.objects.create(
        account=entry.account, restaurant=entry.restaurant, branch=entry.branch,
        entry=entry, ingredient=ingredient, created_by=user, updated_by=user, **kwargs,
    )


def _exit(account, restaurant, branch, user, location, **kwargs):
    return StockExit.objects.create(
        account=account, restaurant=restaurant, branch=branch, location=location,
        effective_date=kwargs.pop("effective_date", timezone.localdate()),
        reason=kwargs.pop("reason", "Consumo da cozinha"),
        created_by=user, updated_by=user, **kwargs,
    )


def _exit_item(exit_document, ingredient, quantity, user):
    return StockExitItem.objects.create(
        account=exit_document.account, restaurant=exit_document.restaurant,
        branch=exit_document.branch, exit=exit_document, ingredient=ingredient,
        requested_quantity=Decimal(quantity), created_by=user, updated_by=user,
    )


def _settings(account, restaurant, branch, user, **kwargs):
    return StockSettings.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        created_by=user, updated_by=user, **kwargs,
    )


# ── entrada ─────────────────────────────────────────────────────────────────
def test_entrada_converte_embalagem_para_unidade_base(
    account, restaurant, branch, manager_user, location, insumo
):
    """2 pacotes de 5 kg viram 10.000 g."""
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(
        entry, insumo, manager_user,
        package_quantity=Decimal("2"), content_per_package=Decimal("5"),
        content_unit="kg", unit_cost=Decimal("0.01"),
    )

    lots = post_stock_entry(entry=entry, user=manager_user)

    assert len(lots) == 1
    assert lots[0].quantity == Decimal("10000.000")
    entry.refresh_from_db()
    assert entry.status == StockEntry.STATUS_POSTED


def test_entrada_gera_movimento_positivo_e_codigo_de_lote(
    account, restaurant, branch, manager_user, location, insumo
):
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("500"), content_unit="g")

    lots = post_stock_entry(entry=entry, user=manager_user)

    movement = StockMovement.objects.get(entry=entry)
    assert movement.quantity == Decimal("500.000")
    assert movement.lot_id == lots[0].id
    # Prefixo legivel do insumo, para o operador conferir a etiqueta a olho.
    assert lots[0].code.startswith("MAC-")


def test_validade_obrigatoria_quando_a_filial_exige(
    account, restaurant, branch, manager_user, location, insumo
):
    _settings(account, restaurant, branch, manager_user, expiry_control_enabled=True)
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("100"), content_unit="g")

    with pytest.raises(ValidationError):
        post_stock_entry(entry=entry, user=manager_user)


def test_validade_opcional_quando_a_filial_nao_exige(
    account, restaurant, branch, manager_user, location, insumo
):
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("100"), content_unit="g")

    assert len(post_stock_entry(entry=entry, user=manager_user)) == 1


def test_validade_anterior_a_entrada_e_recusada(
    account, restaurant, branch, manager_user, location, insumo
):
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(
        entry, insumo, manager_user, package_quantity=Decimal("1"),
        content_per_package=Decimal("100"), content_unit="g",
        expires_at=timezone.localdate() - timedelta(days=1),
    )

    with pytest.raises(ValidationError):
        post_stock_entry(entry=entry, user=manager_user)


def test_entrada_confirmada_nao_confirma_de_novo(
    account, restaurant, branch, manager_user, location, insumo
):
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("100"), content_unit="g")
    post_stock_entry(entry=entry, user=manager_user)

    with pytest.raises(ValidationError):
        post_stock_entry(entry=entry, user=manager_user)


def test_cancelar_entrada_com_lote_intacto_devolve_o_saldo(
    account, restaurant, branch, manager_user, location, insumo
):
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("100"), content_unit="g")
    post_stock_entry(entry=entry, user=manager_user)

    cancel_stock_entry(entry=entry, user=manager_user, reason="Nota errada")

    entry.refresh_from_db()
    assert entry.status == StockEntry.STATUS_CANCELLED
    assert StockLot.objects.get(entry_item__entry=entry).quantity == Decimal("0")


def test_cancelar_entrada_com_lote_ja_consumido_e_recusado(
    account, restaurant, branch, manager_user, location, insumo
):
    """Devolver um saldo que ja saiu produziria um numero plausivel e errado."""
    entry = _entry(account, restaurant, branch, manager_user, location)
    _entry_item(entry, insumo, manager_user, package_quantity=Decimal("1"), content_per_package=Decimal("100"), content_unit="g")
    post_stock_entry(entry=entry, user=manager_user)

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "40", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)
    post_stock_exit(exit_document=exit_document, user=manager_user)

    with pytest.raises(ValidationError):
        cancel_stock_entry(entry=entry, user=manager_user)


# ── FIFO / FEFO ─────────────────────────────────────────────────────────────
def _lot(account, restaurant, branch, user, insumo, location, *, code, entered, expires, quantity):
    return StockLot.objects.create(
        account=account, restaurant=restaurant, branch=branch, ingredient=insumo,
        location=location, code=code, entered_at=entered, expires_at=expires,
        initial_quantity=Decimal(quantity), quantity=Decimal(quantity),
        created_by=user, updated_by=user,
    )


def test_fifo_escolhe_a_entrada_mais_antiga(
    account, restaurant, branch, manager_user, location, insumo
):
    _settings(account, restaurant, branch, manager_user, picking_strategy=StockSettings.PICKING_FIFO)
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="A", entered=hoje - timedelta(days=1), expires=hoje + timedelta(days=30), quantity="100")
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="B", entered=hoje - timedelta(days=5), expires=hoje + timedelta(days=2), quantity="100")

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "50", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    # B entrou antes, mesmo vencendo depois de A na ordem de validade.
    assert [a.lot.code for a in item.allocations.all()] == ["B"]


def test_fefo_escolhe_a_validade_mais_proxima(
    account, restaurant, branch, manager_user, location, insumo
):
    _settings(account, restaurant, branch, manager_user, picking_strategy=StockSettings.PICKING_FEFO)
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="A", entered=hoje - timedelta(days=5), expires=hoje + timedelta(days=30), quantity="100")
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="B", entered=hoje - timedelta(days=1), expires=hoje + timedelta(days=2), quantity="100")

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "50", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    assert [a.lot.code for a in item.allocations.all()] == ["B"]


def test_fefo_deixa_lote_sem_validade_por_ultimo(
    account, restaurant, branch, manager_user, location, insumo
):
    """Lote sem validade nao tem urgencia declarada; nao pode furar a fila."""
    _settings(account, restaurant, branch, manager_user, picking_strategy=StockSettings.PICKING_FEFO)
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="SEM", entered=hoje - timedelta(days=10), expires=None, quantity="100")
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="COM", entered=hoje, expires=hoje + timedelta(days=3), quantity="100")

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "50", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    assert [a.lot.code for a in item.allocations.all()] == ["COM"]


def test_consumo_dividido_entre_dois_lotes(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="A", entered=hoje, expires=hoje + timedelta(days=2), quantity="30")
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="B", entered=hoje, expires=hoje + timedelta(days=9), quantity="100")

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "50", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    alocado = {a.lot.code: a.suggested_quantity for a in item.allocations.all()}
    assert alocado == {"A": Decimal("30.000"), "B": Decimal("20.000")}


def test_lote_vencido_nunca_e_sugerido(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="VENCIDO", entered=hoje - timedelta(days=20), expires=hoje - timedelta(days=1), quantity="100")

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "10", manager_user)
    shortages = suggest_exit_lots(exit_document=exit_document, user=manager_user)

    assert item.allocations.count() == 0
    assert shortages and shortages[0]["missing"] == "10.000"


def test_lote_bloqueado_nao_participa_da_separacao(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    lot = _lot(account, restaurant, branch, manager_user, insumo, location,
               code="BLOQ", entered=hoje, expires=hoje + timedelta(days=10), quantity="100")
    lot.status = StockLot.STATUS_BLOCKED
    lot.save(update_fields=["status"])

    exit_document = _exit(account, restaurant, branch, manager_user, location)
    item = _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    assert item.allocations.count() == 0


# ── conferencia por etiqueta ────────────────────────────────────────────────
def test_leitura_da_etiqueta_correta_confirma_a_alocacao(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-AAA111", entered=hoje, expires=hoje + timedelta(days=5), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location, require_label_scan=True)
    _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    allocation = scan_exit_label(exit_document=exit_document, code="mac-aaa111", user=manager_user)

    assert allocation.is_confirmed
    assert allocation.scanned_code == "MAC-AAA111"


def test_etiqueta_de_outro_lote_diz_qual_era_o_indicado(
    account, restaurant, branch, manager_user, location, insumo
):
    """A troca nao pode ocorrer em silencio (secao 14.1)."""
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-CERTO", entered=hoje, expires=hoje + timedelta(days=2), quantity="100")
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-ERRADO", entered=hoje, expires=hoje + timedelta(days=90), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location, require_label_scan=True)
    _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    with pytest.raises(ValidationError) as error:
        scan_exit_label(exit_document=exit_document, code="MAC-ERRADO", user=manager_user)

    assert "MAC-CERTO" in str(error.value)


def test_etiqueta_desconhecida_e_recusada(
    account, restaurant, branch, manager_user, location, insumo
):
    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "10", manager_user)

    with pytest.raises(ValidationError):
        scan_exit_label(exit_document=exit_document, code="NAO-EXISTE", user=manager_user)


def test_leitura_duplicada_e_recusada(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-DUP", entered=hoje, expires=hoje + timedelta(days=5), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location, require_label_scan=True)
    _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)
    scan_exit_label(exit_document=exit_document, code="MAC-DUP", user=manager_user)

    with pytest.raises(ValidationError):
        scan_exit_label(exit_document=exit_document, code="MAC-DUP", user=manager_user)


def test_confirmacao_exige_conferencia_quando_configurada(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-SCAN", entered=hoje, expires=hoje + timedelta(days=5), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location, require_label_scan=True)
    _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    with pytest.raises(ValidationError):
        post_stock_exit(exit_document=exit_document, user=manager_user)


# ── saida ───────────────────────────────────────────────────────────────────
def test_saida_confirmada_baixa_o_lote_e_gera_movimento(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    lot = _lot(account, restaurant, branch, manager_user, insumo, location,
               code="MAC-OUT", entered=hoje, expires=hoje + timedelta(days=5), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "30", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    movements = post_stock_exit(exit_document=exit_document, user=manager_user)

    lot.refresh_from_db()
    exit_document.refresh_from_db()
    assert lot.quantity == Decimal("70.000")
    assert exit_document.status == StockExit.STATUS_POSTED
    assert movements[0].quantity == Decimal("-30.000")


def test_lote_zerado_fica_esgotado(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    lot = _lot(account, restaurant, branch, manager_user, insumo, location,
               code="MAC-ZERO", entered=hoje, expires=hoje + timedelta(days=5), quantity="20")
    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "20", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)
    post_stock_exit(exit_document=exit_document, user=manager_user)

    lot.refresh_from_db()
    assert lot.quantity == Decimal("0.000")
    assert lot.status == StockLot.STATUS_DEPLETED


def test_saldo_insuficiente_bloqueia_a_confirmacao(
    account, restaurant, branch, manager_user, location, insumo
):
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-POUCO", entered=hoje, expires=hoje + timedelta(days=5), quantity="10")
    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "50", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    with pytest.raises(ValidationError):
        post_stock_exit(exit_document=exit_document, user=manager_user)


def test_saida_sem_separacao_nao_confirma(
    account, restaurant, branch, manager_user, location, insumo
):
    exit_document = _exit(account, restaurant, branch, manager_user, location)
    _exit_item(exit_document, insumo, "10", manager_user)

    with pytest.raises(ValidationError):
        post_stock_exit(exit_document=exit_document, user=manager_user)


def test_reseparar_descarta_conferencias_anteriores(
    account, restaurant, branch, manager_user, location, insumo
):
    """As leituras apontavam para lotes que podem nao ser mais os indicados."""
    hoje = timezone.localdate()
    _lot(account, restaurant, branch, manager_user, insumo, location,
         code="MAC-RE", entered=hoje, expires=hoje + timedelta(days=5), quantity="100")
    exit_document = _exit(account, restaurant, branch, manager_user, location, require_label_scan=True)
    item = _exit_item(exit_document, insumo, "10", manager_user)
    suggest_exit_lots(exit_document=exit_document, user=manager_user)
    scan_exit_label(exit_document=exit_document, code="MAC-RE", user=manager_user)

    suggest_exit_lots(exit_document=exit_document, user=manager_user)

    assert item.allocations.count() == 1
    assert not item.allocations.first().is_confirmed
