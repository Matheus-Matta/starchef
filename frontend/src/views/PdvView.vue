<template>
  <div class="pdv">
    <!-- ── STEP 1: Escolher tipo de pedido ───────────────────────── -->
    <div v-if="step === 'type'" class="pdv__step pdv__step--type">
      <div class="pdv__step-header">
        <h2>Novo pedido</h2>
        <p>Selecione o tipo de atendimento para comecar.</p>
      </div>
      <div class="pdv__type-grid">
        <button
          v-for="t in orderTypes"
          :key="t.value"
          class="pdv__type-card"
          :class="{ 'pdv__type-card--selected': orderType === t.value }"
          type="button"
          @click="selectType(t.value)"
        >
          <span class="pdv__type-icon"><i :class="`pi ${t.icon}`" /></span>
          <strong>{{ t.label }}</strong>
          <small>{{ t.hint }}</small>
        </button>
      </div>
    </div>

    <!-- ── STEP 2: Selecionar mesa / cliente ─────────────────────── -->
    <div v-if="step === 'context'" class="pdv__step pdv__step--context">
      <div class="pdv__step-header">
        <button class="pdv__back" type="button" @click="step = 'type'">
          <AppIcon name="arrow-left" :size="16" /> Voltar
        </button>
        <h2>{{ contextTitle }}</h2>
      </div>

      <!-- Seleção de mesa -->
      <div v-if="orderType === 'table'" class="pdv__tables">
        <div v-if="loadingTables" class="pdv__loading">Carregando mesas...</div>
        <template v-else>
          <div class="pdv__tables-bar">
            <span class="pdv__tables-count">
              <span class="pdv__dot pdv__dot--free" />
              {{ freeTables.length }} {{ freeTables.length === 1 ? "mesa livre" : "mesas livres" }}
            </span>
          </div>
          <div class="pdv__table-grid">
            <button
              v-for="table in freeTables"
              :key="table.id"
              class="pdv__table-card"
              :class="{ 'pdv__table-card--selected': selectedTable?.id === table.id }"
              type="button"
              @click="selectedTable = table"
            >
              <span class="pdv__table-top">
                <span class="pdv__table-icon"><AppIcon name="armchair" :size="15" /></span>
                <span class="pdv__table-status"><span class="pdv__dot pdv__dot--free" />Livre</span>
              </span>
              <strong class="pdv__table-number">{{ table.number }}</strong>
              <span class="pdv__table-meta">
                <small>{{ table.sector_name || "Mesa" }}</small>
                <span class="pdv__table-cap"><AppIcon name="users" :size="12" />{{ table.capacity }}</span>
              </span>
              <span v-if="selectedTable?.id === table.id" class="pdv__table-check"><AppIcon name="check" :size="13" /></span>
            </button>
            <div v-if="!freeTables.length" class="pdv__empty">Nenhuma mesa livre no momento.</div>
          </div>
        </template>
      </div>

      <!-- Seleção de cliente (delivery/takeaway) -->
      <div v-if="['delivery', 'takeaway'].includes(orderType)" class="pdv__customer-search">
        <div class="pdv__search-box">
          <AppIcon name="search" :size="16" />
          <input v-model="customerSearch" placeholder="Buscar cliente por nome ou telefone..." @input="searchCustomers" />
        </div>
        <div v-if="customers.length" class="pdv__customer-list">
          <button
            v-for="c in customers"
            :key="c.id"
            class="pdv__customer-option"
            :class="{ 'pdv__customer-option--selected': selectedCustomer?.id === c.id }"
            type="button"
            @click="selectedCustomer = c"
          >
            <strong>{{ c.name }}</strong>
            <small>{{ c.phone || c.email || "Sem contato" }}</small>
          </button>
        </div>
        <div v-if="customerSearch && !customers.length" class="pdv__empty">Nenhum cliente encontrado.</div>
      </div>

      <div class="pdv__step-footer">
        <button
          class="pdv__btn pdv__btn--primary"
          type="button"
          :disabled="!canProceedContext"
          @click="startOrder"
        >
          {{ creatingOrder ? "Abrindo pedido..." : "Abrir pedido" }}
        </button>
      </div>
    </div>

    <!-- ── STEP 3: Montar pedido ─────────────────────────────────── -->
    <div v-if="step === 'order'" class="pdv__order">
      <!-- Coluna esquerda: cardápio -->
      <div class="pdv__menu-col">
        <div class="pdv__menu-top">
          <div class="pdv__search-box">
            <AppIcon name="search" :size="16" />
            <input v-model="productSearch" placeholder="Buscar produto..." />
          </div>
          <div class="pdv__category-tabs">
            <button
              class="pdv__cat-tab"
              :class="{ 'pdv__cat-tab--active': activeCategory === null }"
              type="button"
              @click="activeCategory = null"
            >Todos</button>
            <button
              v-for="cat in categories"
              :key="cat.id"
              class="pdv__cat-tab"
              :class="{ 'pdv__cat-tab--active': activeCategory === cat.id }"
              type="button"
              @click="activeCategory = cat.id"
            >{{ cat.name }}</button>
          </div>
        </div>

        <div class="pdv__products">
          <div v-if="loadingProducts" class="pdv__loading">Carregando produtos...</div>
          <div v-else class="pdv__product-grid">
            <button
              v-for="product in filteredProducts"
              :key="product.id"
              class="pdv__product-card"
              type="button"
              :disabled="!product.is_active"
              @click="addItem(product)"
            >
              <div v-if="product.image" class="pdv__product-img">
                <img :src="product.image" :alt="product.name" />
                <span class="pdv__product-add"><AppIcon name="plus" :size="14" /></span>
              </div>
              <div v-else class="pdv__product-img pdv__product-img--placeholder">
                <i class="pi pi-box" />
                <span class="pdv__product-add"><AppIcon name="plus" :size="14" /></span>
              </div>
              <div class="pdv__product-info">
                <strong>{{ product.name }}</strong>
                <span class="pdv__product-price">{{ money(product.current_price) }}</span>
                <small v-if="!product.is_active" class="pdv__inactive">Inativo</small>
              </div>
            </button>
            <div v-if="!filteredProducts.length" class="pdv__empty">Nenhum produto encontrado.</div>
          </div>
        </div>
      </div>

      <!-- Coluna direita: resumo do pedido -->
      <div class="pdv__cart-col">
        <div class="pdv__cart-header">
          <div class="pdv__order-info">
            <strong>Pedido #{{ currentOrder?.sequence }}</strong>
            <span>{{ orderTypeLabel }}{{ tableLabel }}</span>
          </div>
          <div v-if="currentOrder" class="pdv__order-badges">
            <span class="pdv__badge pdv__badge--prod" :class="`pdv__prod--${currentOrder.production_status}`">
              {{ prodStatusLabel(currentOrder.production_status) }}
            </span>
          </div>
        </div>

        <div class="pdv__cart-items">
          <div v-if="!cartItems.length" class="pdv__cart-empty">
            <i class="pi pi-shopping-cart" style="font-size:28px;opacity:0.3" />
            <span>Nenhum item adicionado</span>
          </div>

          <!-- Itens já enviados (em produção) -->
          <template v-if="sentItems.length">
            <div class="pdv__cart-section-label">
              <AppIcon name="soup" :size="12" />Em producao ({{ sentItems.length }})
            </div>
            <div v-for="item in sentItems" :key="item.id" class="pdv__cart-item pdv__cart-item--sent">
              <div class="pdv__cart-item-info">
                <strong>{{ item.product_name }}</strong>
                <small v-if="item.customer_note">{{ item.customer_note }}</small>
                <div class="pdv__cart-item-meta">
                  <span v-if="item.batch_number" class="pdv__batch-tag">Rodada {{ item.batch_number }}</span>
                  <span class="pdv__cart-item-status" :class="`pdv__status--${item.status}`">
                    {{ itemStatusLabel(item.status) }}
                  </span>
                </div>
              </div>
              <div class="pdv__cart-item-price">
                <span>{{ item.quantity }}x {{ money(item.unit_price) }}</span>
                <strong :class="{ 'pdv__price--comped': item.status === 'comped' }">{{ money(item.total_price) }}</strong>
              </div>
            </div>
          </template>

          <!-- Itens pendentes (rodada atual) -->
          <template v-if="pendingItems.length">
            <div class="pdv__cart-section-label pdv__cart-section-label--pending">
              <AppIcon name="clock" :size="12" />Aguardando envio ({{ pendingItems.length }})
            </div>
            <div v-for="item in pendingItems" :key="item.id" class="pdv__cart-item">
              <div class="pdv__cart-item-info">
                <strong>{{ item.product_name }}</strong>
                <small v-if="item.customer_note">{{ item.customer_note }}</small>
              </div>
              <div class="pdv__cart-item-right">
                <div class="pdv__cart-item-price">
                  <span>{{ item.quantity }}x {{ money(item.unit_price) }}</span>
                  <strong>{{ money(item.total_price) }}</strong>
                </div>
                <button class="pdv__void-btn" type="button" title="Cancelar item" @click="voidItem(item)">
                  <AppIcon name="x" :size="13" />
                </button>
              </div>
            </div>
          </template>
        </div>

        <!-- Nota -->
        <div v-if="addingNoteFor" class="pdv__overlay" @click.self="addingNoteFor = null">
          <div class="pdv__modal">
            <h4>Observacao para <em>{{ addingNoteFor.product?.name }}</em></h4>
            <textarea v-model="pendingNote" class="pdv__note-input" rows="3" placeholder="Ex: sem cebola, bem passado..." />
            <div class="pdv__modal-actions">
              <button class="pdv__btn pdv__btn--ghost" type="button" @click="addingNoteFor = null; pendingNote = ''">Cancelar</button>
              <button class="pdv__btn pdv__btn--primary" type="button" @click="confirmNote">Confirmar</button>
            </div>
          </div>
        </div>

        <div class="pdv__cart-totals">
          <div class="pdv__total-row">
            <span>Subtotal</span>
            <strong>{{ money(currentOrder?.subtotal) }}</strong>
          </div>
          <div v-if="currentOrder?.service_fee > 0" class="pdv__total-row">
            <span>Taxa de servico</span>
            <strong>{{ money(currentOrder?.service_fee) }}</strong>
          </div>
          <div class="pdv__total-row pdv__total-row--total">
            <span>Total</span>
            <strong>{{ money(currentOrder?.total) }}</strong>
          </div>
        </div>

        <div class="pdv__cart-actions">
          <button
            class="pdv__btn pdv__btn--secondary"
            type="button"
            :disabled="!pendingItems.length || sendingKitchen"
            @click="sendToKitchen"
          >
            <AppIcon name="soup" :size="16" />
            {{ sendingKitchen ? "Enviando..." : `Enviar p/ cozinha${pendingItems.length ? ` (${pendingItems.length})` : ""}` }}
          </button>
          <button
            class="pdv__btn pdv__btn--danger"
            type="button"
            @click="showCancelModal = true"
          >
            Cancelar pedido
          </button>
          <button
            class="pdv__btn pdv__btn--primary"
            type="button"
            :disabled="!cartItems.length || cartItems.every(i => i.status === 'cancelled')"
            @click="goToClose"
          >
            Fechar pedido
          </button>
        </div>
      </div>
    </div>

    <!-- ── STEP 4: Fechamento + pagamento ────────────────────────── -->
    <div v-if="step === 'close'" class="pdv__step pdv__step--close">
      <div class="pdv__step-header">
        <button class="pdv__back" type="button" @click="step = 'order'">
          <AppIcon name="arrow-left" :size="16" /> Voltar ao pedido
        </button>
        <h2>Fechar pedido #{{ currentOrder?.sequence }}</h2>
      </div>

      <div class="pdv__close-body">
        <!-- Coluna esquerda: resumo -->
        <div class="pdv__close-left">
          <div class="pdv__close-section">
            <h4>Resumo do pedido</h4>
            <div class="pdv__close-items">
              <div
                v-for="item in cartItems.filter(i => i.status !== 'cancelled')"
                :key="item.id"
                class="pdv__close-item"
                :class="{ 'pdv__close-item--comped': item.status === 'comped' }"
              >
                <span>{{ item.quantity }}x {{ item.product_name }}</span>
                <strong>{{ item.status === 'comped' ? 'Cortesia' : money(item.total_price) }}</strong>
              </div>
            </div>
          </div>

          <div class="pdv__close-section">
            <h4>Desconto</h4>
            <div class="pdv__discount-row">
              <input
                v-model.number="discount"
                type="number"
                min="0"
                step="0.01"
                class="pdv__close-input"
                placeholder="0,00"
              />
              <span>R$</span>
            </div>
          </div>

          <div class="pdv__close-totals">
            <div class="pdv__total-row">
              <span>Subtotal</span>
              <strong>{{ money(currentOrder?.subtotal) }}</strong>
            </div>
            <div v-if="discount > 0" class="pdv__total-row pdv__total-row--discount">
              <span>Desconto</span>
              <strong>-{{ money(discount) }}</strong>
            </div>
            <div class="pdv__total-row pdv__total-row--total">
              <span>TOTAL</span>
              <strong>{{ money(finalTotal) }}</strong>
            </div>
          </div>
        </div>

        <!-- Coluna direita: pagamento -->
        <div class="pdv__close-right">
          <!-- Pagamentos já registrados -->
          <div v-if="registeredPayments.length" class="pdv__close-section">
            <h4>Pagamentos registrados</h4>
            <div class="pdv__payment-history">
              <div v-for="p in registeredPayments" :key="p.id" class="pdv__payment-record">
                <span>{{ p.payment_method_name || "Pagamento" }}</span>
                <strong>{{ money(p.amount) }}</strong>
              </div>
            </div>
            <div class="pdv__remaining-row">
              <span>Restante</span>
              <strong :class="remainingAmount <= 0 ? 'pdv__remaining--paid' : 'pdv__remaining--due'">
                {{ money(remainingAmount) }}
              </strong>
            </div>
          </div>

          <!-- Adicionar pagamento -->
          <div v-if="remainingAmount > 0" class="pdv__close-section">
            <h4>{{ registeredPayments.length ? "Adicionar pagamento" : "Forma de pagamento" }}</h4>
            <div class="pdv__payment-methods">
              <button
                v-for="method in paymentMethods"
                :key="method.id"
                class="pdv__payment-btn"
                :class="{ 'pdv__payment-btn--selected': selectedPaymentMethod?.id === method.id }"
                type="button"
                @click="selectedPaymentMethod = method"
              >
                <i :class="`pi ${paymentIcon(method.method_type)}`" />
                {{ method.name }}
              </button>
            </div>

            <div class="pdv__close-section" style="margin-top:14px">
              <h4>Valor</h4>
              <input
                v-model.number="amountReceived"
                type="number"
                min="0"
                step="0.01"
                class="pdv__close-input pdv__close-input--large"
                :placeholder="money(remainingAmount)"
              />
              <div v-if="changeAmount > 0" class="pdv__change">
                Troco: <strong>{{ money(changeAmount) }}</strong>
              </div>
            </div>

            <div v-if="payError" class="pdv__error">{{ payError }}</div>

            <button
              class="pdv__btn pdv__btn--secondary pdv__btn--full"
              type="button"
              :disabled="!canAddPayment || paying"
              @click="addPayment"
            >
              <AppIcon name="plus" :size="15" />
              {{ paying ? "Registrando..." : "Adicionar pagamento" }}
            </button>
          </div>

          <!-- Confirmar quando tudo pago -->
          <div v-if="remainingAmount <= 0 && registeredPayments.length" class="pdv__paid-confirm">
            <AppIcon name="check-circle" :size="32" />
            <p>Pagamento completo!</p>
            <button class="pdv__btn pdv__btn--primary pdv__btn--full" type="button" @click="confirmPaid">
              Finalizar pedido
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── STEP 5: Sucesso ───────────────────────────────────────── -->
    <div v-if="step === 'success'" class="pdv__step pdv__step--success">
      <div class="pdv__success-icon">
        <i class="pi pi-check-circle" />
      </div>
      <h2>Pedido pago!</h2>
      <p>Pedido #{{ lastPaidSequence }} finalizado com sucesso.</p>
      <div class="pdv__success-actions">
        <button class="pdv__btn pdv__btn--primary" type="button" @click="newOrder">
          Novo pedido
        </button>
      </div>
    </div>

    <!-- Modal cancelar -->
    <div v-if="showCancelModal" class="pdv__overlay" @click.self="showCancelModal = false">
      <div class="pdv__modal">
        <h3>Cancelar pedido?</h3>
        <p>Informe o motivo do cancelamento.</p>
        <textarea v-model="cancelReason" class="pdv__note-input" rows="3" placeholder="Ex: cliente desistiu..." />
        <div class="pdv__modal-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" @click="showCancelModal = false">Voltar</button>
          <button class="pdv__btn pdv__btn--danger" type="button" :disabled="!cancelReason || cancelling" @click="cancelOrder">
            {{ cancelling ? "Cancelando..." : "Cancelar pedido" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AppIcon from "../components/AppIcon.vue";
import { api } from "../services/api";

// ── State ────────────────────────────────────────────────────────
const step = ref("type");
const orderType = ref(null);
const selectedTable = ref(null);
const selectedCustomer = ref(null);
const currentOrder = ref(null);
const cartItems = ref([]);
const lastPaidSequence = ref(null);
const registeredPayments = ref([]);

// products
const allProducts = ref([]);
const categories = ref([]);
const activeCategory = ref(null);
const productSearch = ref("");
const loadingProducts = ref(false);

// tables
const allTables = ref([]);
const loadingTables = ref(false);

// customers
const customers = ref([]);
const customerSearch = ref("");

// payment
const paymentMethods = ref([]);
const selectedPaymentMethod = ref(null);
const amountReceived = ref(0);
const paying = ref(false);
const payError = ref("");

// misc
const discount = ref(0);
const sendingKitchen = ref(false);
const creatingOrder = ref(false);
const showCancelModal = ref(false);
const cancelReason = ref("");
const cancelling = ref(false);
const addingNoteFor = ref(null);
const pendingNote = ref("");

// ── Order types ──────────────────────────────────────────────────
const orderTypes = [
  { value: "table", label: "Mesa", icon: "pi-th-large", hint: "Atendimento em mesa com comanda" },
  { value: "counter", label: "Balcao", icon: "pi-building", hint: "Entrega imediata no balcao" },
  { value: "delivery", label: "Delivery", icon: "pi-truck", hint: "Entrega no endereco do cliente" },
  { value: "takeaway", label: "Retirada", icon: "pi-send", hint: "Cliente retira no estabelecimento" },
  { value: "command", label: "Comanda", icon: "pi-id-card", hint: "Comanda de consumo aberta" },
];

// ── Computed ─────────────────────────────────────────────────────
const contextTitle = computed(() => {
  if (orderType.value === "table") return "Selecionar mesa";
  if (["delivery", "takeaway"].includes(orderType.value)) return "Selecionar cliente (opcional)";
  return "Confirmar tipo";
});

const canProceedContext = computed(() => {
  if (orderType.value === "table") return !!selectedTable.value;
  return true;
});

const freeTables = computed(() => allTables.value.filter((t) => t.status === "free" && t.is_active));

const filteredProducts = computed(() => {
  let list = allProducts.value.filter((p) => p.is_active);
  if (activeCategory.value) list = list.filter((p) => p.category === activeCategory.value);
  if (productSearch.value.trim()) {
    const q = productSearch.value.toLowerCase();
    list = list.filter((p) => p.name.toLowerCase().includes(q) || (p.internal_code || "").toLowerCase().includes(q));
  }
  return list;
});

// Items split by status
const pendingItems = computed(() => cartItems.value.filter((i) => i.status === "pending"));
const sentItems = computed(() => cartItems.value.filter((i) => i.status !== "pending" && i.status !== "cancelled"));

const orderTypeLabel = computed(() => orderTypes.find((t) => t.value === orderType.value)?.label || "");
const tableLabel = computed(() => (selectedTable.value ? ` — Mesa ${selectedTable.value.number}` : ""));

const finalTotal = computed(() => {
  const sub = Number(currentOrder.value?.subtotal || 0);
  const fee = Number(currentOrder.value?.service_fee || 0);
  const disc = Number(discount.value || 0);
  return Math.max(0, sub + fee - disc);
});

const totalPaid = computed(() => registeredPayments.value.reduce((s, p) => s + Number(p.amount), 0));
const remainingAmount = computed(() => Math.max(0, finalTotal.value - totalPaid.value));
const changeAmount = computed(() => Math.max(0, Number(amountReceived.value || 0) - remainingAmount.value));
const canAddPayment = computed(() => selectedPaymentMethod.value && amountReceived.value > 0);

// ── Methods ──────────────────────────────────────────────────────
function selectType(type) {
  orderType.value = type;
  step.value = "context";
}

async function startOrder() {
  creatingOrder.value = true;
  try {
    const profile = await loadProfile();
    const payload = {
      order_type: orderType.value,
      restaurant: profile.restaurant_id,
      branch: profile.branch_id,
    };
    if (selectedTable.value) payload.table = selectedTable.value.id;
    if (selectedCustomer.value) payload.customer = selectedCustomer.value.id;

    const res = await api.post("/orders/", payload);
    currentOrder.value = res.data;
    cartItems.value = [];
    discount.value = 0;
    await loadProducts(profile);
    step.value = "order";
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao abrir pedido.");
  } finally {
    creatingOrder.value = false;
  }
}

let profileCache = null;
async function loadProfile() {
  if (!profileCache) {
    const res = await api.get("/auth/me/");
    profileCache = res.data;
  }
  return profileCache;
}

async function loadProducts(profile) {
  loadingProducts.value = true;
  try {
    const [prodRes, catRes] = await Promise.all([
      api.get("/menu/products/", { params: { branch: profile.branch_id, is_active: true, page_size: 200 } }),
      api.get("/menu/categories/", { params: { branch: profile.branch_id, is_active: true, page_size: 100 } }),
    ]);
    allProducts.value = prodRes.data.results || prodRes.data;
    categories.value = catRes.data.results || catRes.data;
  } finally {
    loadingProducts.value = false;
  }
}

async function loadTables() {
  loadingTables.value = true;
  try {
    const res = await api.get("/tables/", { params: { page_size: 200 } });
    allTables.value = res.data.results || res.data;
  } finally {
    loadingTables.value = false;
  }
}

async function loadPaymentMethods() {
  const profile = await loadProfile();
  const res = await api.get("/payments/methods/", { params: { branch: profile.branch_id, is_active: true } });
  paymentMethods.value = res.data.results || res.data;
}

async function searchCustomers() {
  if (!customerSearch.value.trim()) { customers.value = []; return; }
  try {
    const res = await api.get("/customers/", { params: { search: customerSearch.value, page_size: 20 } });
    customers.value = res.data.results || res.data;
  } catch { customers.value = []; }
}

async function addItem(product) {
  if (!currentOrder.value) return;
  try {
    await api.post(`/orders/${currentOrder.value.id}/items/`, { product: product.id, quantity: 1 });
    await refreshCart();
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao adicionar item.");
  }
}

async function voidItem(item) {
  try {
    await api.delete(`/orders/${currentOrder.value.id}/items/${item.id}/void/`);
    await refreshCart();
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao cancelar item.");
  }
}

async function refreshCart() {
  const [itemsRes, orderRes] = await Promise.all([
    api.get(`/orders/${currentOrder.value.id}/items/`),
    api.get(`/orders/${currentOrder.value.id}/`),
  ]);
  cartItems.value = Array.isArray(itemsRes.data) ? itemsRes.data : (itemsRes.data.results || []);
  currentOrder.value = orderRes.data;
}

async function sendToKitchen() {
  if (!pendingItems.value.length) return;
  sendingKitchen.value = true;
  try {
    await api.post(`/orders/${currentOrder.value.id}/send-to-kitchen/`);
    await refreshCart();
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao enviar para cozinha.");
  } finally {
    sendingKitchen.value = false;
  }
}

async function goToClose() {
  await loadPaymentMethods();
  // Close the order account first
  try {
    const res = await api.post(`/orders/${currentOrder.value.id}/close/`, { discount: discount.value || 0 });
    currentOrder.value = res.data;
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao fechar pedido.");
    return;
  }
  // Load existing payments
  await refreshPayments();
  amountReceived.value = remainingAmount.value;
  step.value = "close";
}

async function refreshPayments() {
  try {
    const res = await api.get(`/orders/${currentOrder.value.id}/payments/`);
    registeredPayments.value = Array.isArray(res.data) ? res.data : (res.data.results || []);
  } catch {
    registeredPayments.value = [];
  }
}

async function addPayment() {
  if (!canAddPayment.value) return;
  paying.value = true;
  payError.value = "";
  try {
    await api.post(`/orders/${currentOrder.value.id}/pay/`, {
      payment_method: selectedPaymentMethod.value.id,
      amount: amountReceived.value,
    });
    await Promise.all([refreshPayments(), refreshCart()]);
    selectedPaymentMethod.value = null;
    amountReceived.value = remainingAmount.value;
  } catch (e) {
    payError.value = e.response?.data?.detail?.[0] || e.response?.data?.detail || "Erro ao registrar pagamento.";
  } finally {
    paying.value = false;
  }
}

async function confirmPaid() {
  lastPaidSequence.value = currentOrder.value.sequence;
  step.value = "success";
}

async function cancelOrder() {
  if (!cancelReason.value) return;
  cancelling.value = true;
  try {
    await api.post(`/orders/${currentOrder.value.id}/cancel/`, { reason: cancelReason.value });
    showCancelModal.value = false;
    newOrder();
  } catch (e) {
    alert(e.response?.data?.detail || "Erro ao cancelar pedido.");
  } finally {
    cancelling.value = false;
  }
}

function newOrder() {
  step.value = "type";
  orderType.value = null;
  selectedTable.value = null;
  selectedCustomer.value = null;
  currentOrder.value = null;
  cartItems.value = [];
  discount.value = 0;
  selectedPaymentMethod.value = null;
  amountReceived.value = 0;
  payError.value = "";
  cancelReason.value = "";
  productSearch.value = "";
  customerSearch.value = "";
  customers.value = [];
  registeredPayments.value = [];
  profileCache = null;
}

function confirmNote() {
  addingNoteFor.value = null;
  pendingNote.value = "";
}

function itemStatusLabel(s) {
  return { pending: "Pendente", sent: "Cozinha", preparing: "Preparo", ready: "Pronto", delivered: "Entregue", cancelled: "Cancelado", comped: "Cortesia" }[s] || s;
}

function prodStatusLabel(s) {
  return { idle: "Sem envio", sent_to_kitchen: "Na cozinha", preparing: "Em preparo", partially_ready: "Parcial", ready: "Pronto", delivered: "Entregue" }[s] || s;
}

function paymentIcon(type) {
  return { cash: "pi-dollar", card: "pi-credit-card", pix: "pi-qrcode", voucher: "pi-ticket" }[type] || "pi-wallet";
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

onMounted(() => {
  loadTables();
});
</script>

<style scoped>
.pdv {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ── Steps ──────────────────────────────────────────────────── */
.pdv__step {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.pdv__step-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pdv__step-header h2 {
  font: var(--weight-extra) 22px/1.15 var(--font-sans);
  color: var(--text-strong);
  margin: 0;
}

.pdv__step-header p {
  font: var(--weight-medium) 14px/1.5 var(--font-sans);
  color: var(--text-muted);
  margin: 0;
}

.pdv__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 4px;
}
.pdv__back:hover { color: var(--text-body); }

/* ── Type selection ─────────────────────────────────────────── */
.pdv__type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 14px;
}

.pdv__type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 16px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
  color: var(--text-body);
}
.pdv__type-card:hover {
  border-color: var(--brand-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.pdv__type-card--selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 18%, transparent), var(--shadow-sm);
}
.pdv__type-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--brand-subtle);
  color: var(--text-brand);
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.pdv__type-icon .pi { font-size: 24px; }
.pdv__type-card--selected .pdv__type-icon { background: var(--brand); color: #fff; }
.pdv__type-card strong { font: var(--weight-bold) 15px/1 var(--font-sans); color: var(--text-strong); }
.pdv__type-card small { font: var(--weight-medium) 11.5px/1.4 var(--font-sans); color: var(--text-muted); text-align: center; }

/* ── Tables ─────────────────────────────────────────────────── */
.pdv__tables { display: flex; flex-direction: column; gap: 14px; }

.pdv__tables-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pdv__tables-count {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: var(--weight-bold) 12px/1 var(--font-sans);
  color: var(--text-muted);
}

.pdv__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pdv__dot--free { background: var(--success); box-shadow: 0 0 0 3px var(--success-subtle); }

.pdv__table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 12px;
}
.pdv__table-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  text-align: left;
  color: var(--text-body);
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.pdv__table-card:hover {
  border-color: var(--brand-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.pdv__table-card--selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 18%, transparent), var(--shadow-sm);
}

.pdv__table-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pdv__table-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: var(--brand-subtle);
  color: var(--text-brand);
}
.pdv__table-card--selected .pdv__table-icon { background: var(--brand); color: #fff; }

.pdv__table-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: var(--weight-bold) 9.5px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--success-text);
}

.pdv__table-number {
  font: var(--weight-extra) 26px/1 var(--font-sans);
  color: var(--text-strong);
  letter-spacing: var(--tracking-tight);
}

.pdv__table-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}
.pdv__table-meta small {
  font: var(--weight-semibold) 11.5px/1 var(--font-sans);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pdv__table-cap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font: var(--weight-bold) 11.5px/1 var(--font-sans);
  color: var(--text-subtle);
}

.pdv__table-check {
  position: absolute;
  top: 10px;
  right: 10px;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
}
.pdv__table-card--selected .pdv__table-status { visibility: hidden; }

/* ── Customer search ─────────────────────────────────────────── */
.pdv__search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 40px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
}
.pdv__search-box input {
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font: var(--weight-medium) 13.5px/1 var(--font-sans);
  color: var(--text-body);
}
.pdv__customer-search { display: flex; flex-direction: column; gap: 10px; }
.pdv__customer-list { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow-y: auto; }
.pdv__customer-option {
  display: flex; flex-direction: column; gap: 2px; padding: 10px 14px;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer; text-align: left; color: var(--text-body);
}
.pdv__customer-option:hover,
.pdv__customer-option--selected { background: var(--brand-subtle); border-color: var(--brand); }
.pdv__customer-option strong { font: var(--weight-bold) 13px/1 var(--font-sans); }
.pdv__customer-option small { font: var(--weight-medium) 11.5px/1 var(--font-sans); color: var(--text-muted); }

/* ── Order step ─────────────────────────────────────────────── */
.pdv__order {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 340px;
  min-height: 0;
  overflow: hidden;
}

.pdv__menu-col { display: flex; flex-direction: column; border-right: 1px solid var(--border); overflow: hidden; }
.pdv__menu-top {
  padding: 14px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.pdv__category-tabs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 2px; }
.pdv__cat-tab {
  white-space: nowrap;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  background: var(--surface-card);
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1 var(--font-sans);
  cursor: pointer;
}
.pdv__cat-tab--active { background: var(--brand); border-color: var(--brand); color: #fff; }

.pdv__products { flex: 1; overflow-y: auto; padding: 14px 16px; }
.pdv__product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(144px, 1fr)); gap: 12px; }
.pdv__product-card {
  display: flex; flex-direction: column;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg);
  overflow: hidden; cursor: pointer; text-align: left; color: var(--text-body);
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.pdv__product-card:hover:not(:disabled) { border-color: var(--brand-border); box-shadow: var(--shadow-md); transform: translateY(-2px); }
.pdv__product-card:disabled { opacity: 0.5; cursor: not-allowed; }
.pdv__product-img { position: relative; height: 92px; overflow: hidden; background: var(--surface-sunken); }
.pdv__product-img img { width: 100%; height: 100%; object-fit: cover; }
.pdv__product-img--placeholder { display: flex; align-items: center; justify-content: center; color: var(--text-subtle); font-size: 26px; }
.pdv__product-add {
  position: absolute; bottom: 6px; right: 6px;
  display: grid; place-items: center; width: 26px; height: 26px;
  border-radius: 50%; background: var(--brand); color: #fff;
  box-shadow: var(--shadow-sm);
  opacity: 0; transform: scale(0.8) translateY(4px);
  transition: opacity var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.pdv__product-card:hover:not(:disabled) .pdv__product-add { opacity: 1; transform: scale(1) translateY(0); }
.pdv__product-info { padding: 9px 11px 11px; display: flex; flex-direction: column; gap: 4px; }
.pdv__product-info strong { font: var(--weight-bold) 12.5px/1.3 var(--font-sans); color: var(--text-strong); }
.pdv__product-price { font: var(--weight-extra) 13px/1 var(--font-sans); color: var(--text-brand); }
.pdv__inactive { font: var(--weight-medium) 10.5px/1 var(--font-sans); color: var(--text-muted); background: var(--surface-sunken); border-radius: 4px; padding: 2px 5px; width: fit-content; }

/* ── Cart ───────────────────────────────────────────────────── */
.pdv__cart-col { display: flex; flex-direction: column; overflow: hidden; background: var(--surface-card); }

.pdv__cart-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pdv__order-info { display: flex; flex-direction: column; gap: 2px; }
.pdv__order-info strong { font: var(--weight-extra) 15px/1 var(--font-sans); color: var(--text-strong); }
.pdv__order-info span { font: var(--weight-medium) 12px/1 var(--font-sans); color: var(--text-muted); }

.pdv__order-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.pdv__badge {
  padding: 3px 8px; border-radius: var(--radius-pill);
  font: var(--weight-bold) 10px/1 var(--font-sans);
}
.pdv__prod--idle { background: var(--surface-active); color: var(--text-muted); }
.pdv__prod--sent_to_kitchen { background: #fef3c7; color: #92400e; }
.pdv__prod--preparing { background: #dbeafe; color: #1d4ed8; }
.pdv__prod--partially_ready { background: #fce7f3; color: #9d174d; }
.pdv__prod--ready { background: #d1fae5; color: #065f46; }
.pdv__prod--delivered { background: #e0e7ff; color: #3730a3; }

.pdv__cart-items { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }

.pdv__cart-section-label {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 6px;
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-top: 4px;
}
.pdv__cart-section-label--pending { color: var(--brand); }

.pdv__cart-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
  color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans);
}

.pdv__cart-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: var(--surface-sunken);
  border-radius: var(--radius-sm);
}
.pdv__cart-item--sent { opacity: 0.85; }

.pdv__cart-item-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.pdv__cart-item-info strong { font: var(--weight-bold) 12.5px/1.3 var(--font-sans); color: var(--text-strong); }
.pdv__cart-item-info small { font: var(--weight-medium) 11px/1.3 var(--font-sans); color: var(--text-muted); }

.pdv__cart-item-meta { display: flex; align-items: center; gap: 5px; margin-top: 2px; }
.pdv__batch-tag {
  padding: 1px 6px; border-radius: 3px;
  background: var(--brand-subtle); color: var(--text-brand);
  font: var(--weight-bold) 10px/1.4 var(--font-sans);
}

.pdv__cart-item-status {
  font: var(--weight-bold) 10px/1 var(--font-sans); text-transform: uppercase;
  padding: 2px 5px; border-radius: 4px; width: fit-content;
}
.pdv__status--pending { background: var(--surface-active); color: var(--text-muted); }
.pdv__status--sent { background: #fef3c7; color: #92400e; }
.pdv__status--preparing { background: #dbeafe; color: #1d4ed8; }
.pdv__status--ready { background: #d1fae5; color: #065f46; }
.pdv__status--delivered { background: #e0e7ff; color: #3730a3; }
.pdv__status--cancelled { background: #fee2e2; color: #991b1b; }
.pdv__status--comped { background: #fce7f3; color: #9d174d; }

.pdv__cart-item-right { display: flex; align-items: flex-end; gap: 6px; flex-shrink: 0; }

.pdv__cart-item-price { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.pdv__cart-item-price span { font: var(--weight-medium) 11px/1 var(--font-sans); color: var(--text-muted); }
.pdv__cart-item-price strong { font: var(--weight-bold) 13px/1 var(--font-sans); color: var(--text-strong); }
.pdv__price--comped { text-decoration: line-through; color: var(--text-muted); }

.pdv__void-btn {
  width: 26px; height: 26px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-card); color: var(--text-muted); cursor: pointer;
  flex-shrink: 0;
}
.pdv__void-btn:hover { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }

.pdv__cart-totals {
  padding: 10px 12px;
  border-top: 1px solid var(--border-subtle);
  display: flex; flex-direction: column; gap: 5px; flex-shrink: 0;
}

.pdv__total-row {
  display: flex; justify-content: space-between;
  font: var(--weight-medium) 13px/1 var(--font-sans); color: var(--text-body);
}
.pdv__total-row--discount { color: var(--success-text, #065f46); }
.pdv__total-row--total {
  font: var(--weight-extra) 16px/1 var(--font-sans); color: var(--text-strong);
  padding-top: 5px; border-top: 1px solid var(--border-subtle);
}

.pdv__cart-actions {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px; border-top: 1px solid var(--border); flex-shrink: 0;
}

/* ── Close step ─────────────────────────────────────────────── */
.pdv__step--close { max-width: 860px; }
.pdv__close-body { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }

.pdv__close-section { display: flex; flex-direction: column; gap: 12px; }
.pdv__close-section h4 {
  font: var(--weight-bold) 12px/1 var(--font-sans); text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-subtle); margin: 0;
}

.pdv__close-items { display: flex; flex-direction: column; gap: 4px; }
.pdv__close-item {
  display: flex; justify-content: space-between;
  font: var(--weight-medium) 13px/1.4 var(--font-sans); color: var(--text-body);
}
.pdv__close-item--comped { color: var(--text-muted); font-style: italic; }

.pdv__close-totals {
  display: flex; flex-direction: column; gap: 6px;
  padding: 12px; background: var(--surface-sunken); border-radius: var(--radius-md);
}

.pdv__discount-row { display: flex; align-items: center; gap: 8px; }
.pdv__close-input {
  height: 42px; padding: 0 12px; border: 1px solid var(--border);
  border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 14px/1 var(--font-sans); flex: 1;
}
.pdv__close-input--large { font-size: 18px; height: 50px; width: 100%; }

.pdv__change { font: var(--weight-semibold) 14px/1 var(--font-sans); color: var(--text-muted); margin-top: 4px; }
.pdv__change strong { color: var(--brand); }

.pdv__payment-methods { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.pdv__payment-btn {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 12px 8px; border: 2px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 12px/1 var(--font-sans); cursor: pointer; transition: all 0.12s;
}
.pdv__payment-btn:hover { border-color: var(--brand); }
.pdv__payment-btn--selected { border-color: var(--brand); background: var(--brand-subtle); color: var(--brand); }

/* Payments history in close step */
.pdv__payment-history { display: flex; flex-direction: column; gap: 4px; }
.pdv__payment-record {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 10px; background: var(--surface-sunken); border-radius: var(--radius-sm);
  font: var(--weight-medium) 13px/1 var(--font-sans); color: var(--text-body);
}
.pdv__payment-record strong { font-weight: var(--weight-bold); color: var(--text-strong); }

.pdv__remaining-row {
  display: flex; justify-content: space-between;
  font: var(--weight-bold) 14px/1 var(--font-sans); color: var(--text-body);
  padding: 8px 2px 0;
}
.pdv__remaining--paid { color: #065f46; }
.pdv__remaining--due { color: #92400e; }

.pdv__paid-confirm {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  padding: 24px; background: #d1fae5; border-radius: var(--radius-lg);
  color: #065f46; text-align: center;
}
.pdv__paid-confirm p { font: var(--weight-bold) 14px/1 var(--font-sans); margin: 0; }

/* ── Success ────────────────────────────────────────────────── */
.pdv__step--success { align-items: center; justify-content: center; text-align: center; }
.pdv__success-icon { font-size: 72px; color: var(--brand); }
.pdv__success-icon .pi { font-size: 72px; }
.pdv__step--success h2 { font: var(--weight-extra) 28px/1.1 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__step--success p { font: var(--weight-medium) 15px/1.5 var(--font-sans); color: var(--text-muted); margin: 0; }
.pdv__success-actions { margin-top: 8px; }

/* ── Buttons ────────────────────────────────────────────────── */
.pdv__btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 0 18px; height: 42px; border: none; border-radius: var(--radius-md);
  font: var(--weight-bold) 13.5px/1 var(--font-sans); cursor: pointer; transition: all 0.12s;
}
.pdv__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pdv__btn--primary { background: var(--brand); color: #fff; }
.pdv__btn--primary:hover:not(:disabled) { filter: brightness(1.1); }
.pdv__btn--secondary { background: var(--surface-active); color: var(--text-body); border: 1px solid var(--border); }
.pdv__btn--secondary:hover:not(:disabled) { background: var(--border); }
.pdv__btn--danger { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.pdv__btn--danger:hover:not(:disabled) { background: #fca5a5; }
.pdv__btn--ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
.pdv__btn--full { width: 100%; }

/* ── Modals / Overlays ──────────────────────────────────────── */
.pdv__overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.pdv__modal {
  background: var(--surface-card); border-radius: var(--radius-lg);
  padding: 28px; max-width: 420px; width: calc(100% - 40px);
  display: flex; flex-direction: column; gap: 14px; box-shadow: var(--shadow-lg);
}
.pdv__modal h3 { font: var(--weight-extra) 18px/1.2 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__modal h4 { font: var(--weight-bold) 14px/1.2 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__modal p { font: var(--weight-medium) 13.5px/1.5 var(--font-sans); color: var(--text-muted); margin: 0; }
.pdv__modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

.pdv__note-input {
  resize: vertical; padding: 10px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-medium) 13.5px/1.5 var(--font-sans); width: 100%; box-sizing: border-box;
}

/* ── Misc ───────────────────────────────────────────────────── */
.pdv__loading { padding: 20px; text-align: center; color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); }
.pdv__empty { padding: 20px; text-align: center; color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); grid-column: 1/-1; }
.pdv__error { padding: 10px 14px; background: #fee2e2; color: #991b1b; border-radius: var(--radius-sm); font: var(--weight-semibold) 13px/1.4 var(--font-sans); }
.pdv__step-footer { display: flex; justify-content: flex-end; }

@media (max-width: 860px) {
  .pdv__order { grid-template-columns: 1fr; grid-template-rows: 1fr auto; }
  .pdv__close-body { grid-template-columns: 1fr; }
}
</style>
