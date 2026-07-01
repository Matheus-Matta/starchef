<template>
  <div class="resource-view" :class="{ 'resource-view--cards': isCardResource }">
    <section v-if="isMenuCatalog" class="menu-hero">
      <div class="menu-hero__copy">
        <span class="menu-hero__eyebrow">Cardapio operacional</span>
        <h2>Itens prontos para vender, preparar e controlar.</h2>
        <p>{{ subtitle }}</p>
      </div>
      <div class="menu-hero__metrics">
        <div class="menu-metric">
          <span>{{ total }}</span>
          <small>itens cadastrados</small>
        </div>
        <div class="menu-metric menu-metric--green">
          <span>{{ menuStats.active }}</span>
          <small>ativos na venda</small>
        </div>
        <div class="menu-metric menu-metric--blue">
          <span>{{ money(menuStats.averagePrice) }}</span>
          <small>preco medio da pagina</small>
        </div>
      </div>
    </section>

    <section v-if="isTableCards" class="table-overview">
      <div class="table-overview__copy">
        <span>Mapa operacional</span>
        <h2>Mesas e comandas em leitura rapida.</h2>
      </div>
      <div class="table-overview__metrics">
        <div>
          <strong>{{ total }}</strong>
          <span>mesas</span>
        </div>
        <div>
          <strong>{{ tableStats.free }}</strong>
          <span>livres</span>
        </div>
        <div>
          <strong>{{ tableStats.busy }}</strong>
          <span>ocupadas</span>
        </div>
        <div>
          <strong>{{ tableStats.capacity }}</strong>
          <span>lugares</span>
        </div>
      </div>
    </section>

    <Toolbar class="resource-toolbar">
      <template #start>
        <IconField icon-position="left" class="resource-toolbar__search">
          <InputIcon class="pi pi-search" />
          <InputText v-model="search" :placeholder="`Buscar em ${title.toLowerCase()}...`" @keyup.enter="loadRows" />
        </IconField>
      </template>

      <template #end>
        <div class="resource-toolbar__actions">
          <Dropdown
            v-if="isMenuCatalog"
            v-model="activeFilter"
            class="resource-filter"
            :options="activeOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <Dropdown
            v-if="isMenuCatalog"
            v-model="typeFilter"
            class="resource-filter"
            :options="typeOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <Dropdown
            v-if="isMenuCatalog"
            v-model="sectorFilter"
            class="resource-filter"
            :options="sectorOptions"
            option-label="label"
            option-value="value"
            @change="loadRows"
          />
          <SelectButton
            v-if="isCardResource"
            v-model="viewMode"
            class="view-mode"
            :options="viewModeOptions"
            option-label="label"
            option-value="value"
            :allow-empty="false"
          />
          <Button icon="pi pi-refresh" label="Atualizar" :loading="loading" severity="secondary" outlined @click="loadRows" />
          <Button v-if="formEnabled" icon="pi pi-plus" label="Novo" @click="goToCreate" />
        </div>
      </template>
    </Toolbar>

    <div v-if="error" class="resource-error">
      <i class="pi pi-exclamation-triangle" />
      {{ error }}
    </div>

    <template v-if="isCardResource && viewMode === 'grid'">
      <div v-if="loading" class="table-grid">
        <div v-for="index in 8" :key="index" class="table-card table-card--loading">
          <Skeleton height="150px" border-radius="14px" />
          <Skeleton width="70%" height="18px" />
          <Skeleton width="100%" height="38px" />
          <Skeleton width="44%" height="28px" />
        </div>
      </div>

      <div v-else-if="rows.length && isTableCards" class="table-grid">
        <article
          v-for="table in rows"
          :key="table.id"
          class="table-card"
          :class="`table-card--${table.status || 'free'}`"
          tabindex="0"
          @click="openDetail(table)"
          @keyup.enter="openDetail(table)"
        >
          <div class="table-card__head">
            <span class="table-card__icon"><i class="pi pi-table" /></span>
            <Tag :value="tableStatusLabel(table.status)" :severity="tableStatusSeverity(table.status)" rounded />
          </div>

          <div class="table-card__main">
            <span>Mesa</span>
            <strong>{{ table.number || "-" }}</strong>
          </div>

          <div class="table-card__meta">
            <div>
              <i class="pi pi-map-marker" />
              <span>{{ table.sector_name || "Sem setor" }}</span>
            </div>
            <div>
              <i class="pi pi-users" />
              <span>{{ table.capacity || 0 }} lugares</span>
            </div>
          </div>

          <div class="table-card__footer">
            <span :class="{ on: table.is_active }">{{ table.is_active ? "Ativa" : "Inativa" }}</span>
            <Button icon="pi pi-arrow-right" rounded text aria-label="Ver detalhe da mesa" @click.stop="openDetail(table)" />
          </div>
        </article>
      </div>

      <div v-else class="resource-empty">
        <i class="pi pi-search" />
        <strong>Nenhum registro encontrado</strong>
        <span>Ajuste a busca ou atualize para ver outros resultados.</span>
      </div>
    </template>

    <section v-else class="resource-panel">
      <div class="resource-panel__header">
        <div>
          <h2>{{ title }}</h2>
          <p>{{ subtitle }}</p>
        </div>
        <Tag :value="loading ? 'Carregando' : `${total} registros`" :severity="loading ? 'warning' : 'info'" />
      </div>

      <DataTable
        :value="rows"
        data-key="id"
        class="resource-datatable"
        :loading="loading"
        :row-hover="true"
        responsive-layout="scroll"
        @row-click="openDetail($event.data)"
      >
        <Column v-for="column in columns" :key="column.key" :field="column.key" :header="column.label" :body-style="columnBodyStyle(column)">
          <template #body="{ data }">
            <span v-if="column.type === 'status'" class="status-chip" :data-status="value(data, column)">{{ label(value(data, column), column.map) }}</span>
            <span v-else-if="column.type === 'money'" class="num strong">{{ money(value(data, column)) }}</span>
            <span v-else-if="column.type === 'date'" class="num muted">{{ dateTime(value(data, column)) }}</span>
            <Tag
              v-else-if="column.type === 'boolean'"
              :value="value(data, column) ? 'Ativo' : 'Inativo'"
              :severity="value(data, column) ? 'success' : 'danger'"
              rounded
            />
            <span v-else class="cell-text">{{ label(value(data, column), column.map) }}</span>
          </template>
        </Column>

        <template #empty>
          <div class="resource-empty resource-empty--table">
            <i class="pi pi-inbox" />
            <strong>Nenhum registro encontrado</strong>
            <span>Tente atualizar ou pesquisar por outro termo.</span>
          </div>
        </template>
      </DataTable>
    </section>

    <div class="resource-footer">
      <Button label="Anterior" icon="pi pi-chevron-left" severity="secondary" outlined :disabled="!previousUrl || loading" @click="loadUrl(previousUrl)" />
      <span>Pagina {{ page }}</span>
      <Button label="Proxima" icon="pi pi-chevron-right" icon-pos="right" severity="secondary" outlined :disabled="!nextUrl || loading" @click="loadUrl(nextUrl)" />
    </div>

    <!-- eslint-disable-next-line vue/no-v-model-argument -->
    <Sidebar v-model:visible="detailOpen" position="right" class="item-detail-panel" :show-close-icon="false">
      <template #header>
        <div class="detail-header">
          <div>
            <span>{{ isMenuCatalog ? "Detalhe do item" : isTableCards ? "Detalhe da mesa" : "Detalhe do registro" }}</span>
            <strong>{{ selectedRowTitle }}</strong>
          </div>
          <div class="detail-header__actions">
            <Button icon="pi pi-times" rounded text severity="secondary" aria-label="Fechar detalhe" @click="detailOpen = false" />
          </div>
        </div>
      </template>

      <div v-if="selectedRow" class="drawer-body">
        <div class="item-detail">
          <template v-if="isMenuCatalog">
            <div class="item-detail__hero" :class="fallbackClass(selectedRow)">
              <img v-if="imageUrl(selectedRow.image)" :src="imageUrl(selectedRow.image)" :alt="selectedRow.name" />
              <div v-else class="item-detail__fallback">
                <i :class="typeIcon(selectedRow.product_type)" />
              </div>
            </div>

            <div class="item-detail__title">
              <div>
                <span>{{ selectedRow.category_name || "Sem categoria" }}</span>
                <h3>{{ selectedRow.name }}</h3>
              </div>
              <strong>{{ money(selectedRow.current_price) }}</strong>
            </div>

            <p class="item-detail__description">{{ selectedRow.description || "Ainda nao ha descricao para este item." }}</p>

            <div class="item-detail__stats">
              <div>
                <i class="pi pi-clock" />
                <span>Preparo</span>
                <strong>{{ selectedRow.average_preparation_time || 0 }} min</strong>
              </div>
              <div>
                <i class="pi pi-chart-line" />
                <span>Margem</span>
                <strong>{{ percent(selectedRow.margin_percent) }}</strong>
              </div>
              <div>
                <i class="pi pi-wallet" />
                <span>Custo</span>
                <strong>{{ money(selectedRow.estimated_cost) }}</strong>
              </div>
            </div>

            <div class="item-detail__section">
              <div class="item-detail__section-head">
                <h4>Disponibilidade</h4>
                <Tag :value="selectedRow.is_active ? 'Ativo' : 'Inativo'" :severity="selectedRow.is_active ? 'success' : 'danger'" rounded />
              </div>
              <div class="availability-grid">
                <span :class="{ on: selectedRow.available_for_table }"><i class="pi pi-table" /> Mesa</span>
                <span :class="{ on: selectedRow.available_for_counter }"><i class="pi pi-shopping-bag" /> Balcao</span>
                <span :class="{ on: selectedRow.available_for_delivery }"><i class="pi pi-truck" /> Delivery</span>
                <span :class="{ on: selectedRow.allows_addons }"><i class="pi pi-plus-circle" /> Adicionais</span>
              </div>
            </div>

            <Divider />

            <div class="item-detail__section">
              <div class="item-detail__section-head">
                <h4>Rentabilidade</h4>
                <span>{{ percent(selectedRow.margin_percent) }}</span>
              </div>
              <ProgressBar :value="progressValue(selectedRow.margin_percent)" :show-value="false" />
            </div>

            <div class="item-detail__section">
              <div class="item-detail__section-head">
                <h4>Variacoes</h4>
                <span>{{ selectedRow.variations?.length || 0 }}</span>
              </div>
              <div v-if="selectedRow.variations?.length" class="detail-list">
                <div v-for="variation in selectedRow.variations" :key="variation.id" class="detail-list__row">
                  <span>{{ variation.name }}</span>
                  <strong>{{ money(variation.price_delta) }}</strong>
                </div>
              </div>
              <p v-else class="item-detail__muted">Nenhuma variacao cadastrada.</p>
            </div>

            <div class="item-detail__section">
              <div class="item-detail__section-head">
                <h4>Ficha tecnica</h4>
                <span>{{ selectedRow.recipe?.items?.length || 0 }} ingredientes</span>
              </div>
              <div v-if="selectedRow.recipe?.items?.length" class="detail-list">
                <div v-for="ingredient in selectedRow.recipe.items" :key="ingredient.id" class="detail-list__row">
                  <span>{{ ingredient.ingredient_name }}</span>
                  <strong>{{ quantity(ingredient.quantity) }} {{ ingredient.unit }}</strong>
                </div>
              </div>
              <p v-else class="item-detail__muted">Nenhuma ficha tecnica cadastrada.</p>
            </div>
          </template>

          <template v-else>
            <div class="rich-detail">
              <div class="rich-detail__hero" :class="`rich-accent--${detailMeta.accent}`">
                <span class="rich-detail__avatar"><i :class="`pi ${detailMeta.icon}`" /></span>
                <div class="rich-detail__headline">
                  <span>{{ detailMeta.eyebrow }}</span>
                  <h3>{{ detailMeta.title(selectedRow) }}</h3>
                  <p v-if="detailMeta.subtitle">{{ detailMeta.subtitle(selectedRow) }}</p>
                </div>
                <span v-if="heroBadge" class="rich-detail__badge">{{ heroBadge.value }}</span>
              </div>

              <div v-if="detailMetrics.length" class="rich-detail__metrics">
                <div v-for="metric in detailMetrics" :key="metric.label" class="rich-detail__metric">
                  <span>{{ metric.label }}</span>
                  <strong>{{ metric.display }}</strong>
                </div>
              </div>

              <div class="rich-detail__fields">
                <div v-for="field in detailFields" :key="field.key" class="rich-detail__field">
                  <span class="rich-detail__field-label">{{ field.label }}</span>
                  <span v-if="field.type === 'status'" class="status-chip" :data-status="field._value">{{ label(field._value, field.map) }}</span>
                  <Tag
                    v-else-if="field.type === 'boolean'"
                    :value="field._value ? 'Ativo' : 'Inativo'"
                    :severity="field._value ? 'success' : 'danger'"
                    rounded
                  />
                  <strong v-else-if="field.type === 'money'" class="rich-detail__field-money">{{ money(field._value) }}</strong>
                  <span v-else-if="field.type === 'date'" class="rich-detail__field-value">{{ dateTime(field._value) }}</span>
                  <span v-else class="rich-detail__field-value">{{ label(field._value, field.map) }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <div class="drawer-footer">
        <Button
          v-if="formEnabled && selectedRow?.id"
          icon="pi pi-pencil"
          label="Editar registro"
          @click="goToEdit(selectedRow.id)"
        />
        <Button label="Fechar" severity="secondary" outlined @click="detailOpen = false" />
      </div>
    </Sidebar>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Column from "primevue/column";
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import DataTable from "primevue/datatable";
import Divider from "primevue/divider";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import ProgressBar from "primevue/progressbar";
import SelectButton from "primevue/selectbutton";
import Sidebar from "primevue/sidebar";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import Toolbar from "primevue/toolbar";

import { api, API_BASE_URL } from "../services/api";

const route = useRoute();
const router = useRouter();

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "Dados carregados do backend." },
  endpoint: { type: String, required: true },
  columns: { type: Array, required: true },
  defaultParams: { type: Object, default: () => ({}) },
  formEnabled: { type: Boolean, default: false },
  globalScope: { type: Boolean, default: false },
});

const rows = ref([]);
const total = ref(0);
const page = ref(1);
const nextUrl = ref("");
const previousUrl = ref("");
const loading = ref(false);
const error = ref("");
const search = ref("");
const activeFilter = ref("all");
const typeFilter = ref("all");
const sectorFilter = ref("all");
const viewMode = ref("grid");
const selectedRow = ref(null);
const detailOpen = ref(false);

const activeOptions = [
  { label: "Todos", value: "all" },
  { label: "Ativos", value: true },
  { label: "Inativos", value: false },
];
const typeOptions = [
  { label: "Todos os tipos", value: "all" },
  { label: "Pratos", value: "meal" },
  { label: "Bebidas", value: "drink" },
  { label: "Sobremesas", value: "dessert" },
  { label: "Combos", value: "combo" },
  { label: "Adicionais", value: "addon" },
];
const sectorOptions = [
  { label: "Todos os setores", value: "all" },
  { label: "Cozinha", value: "kitchen" },
  { label: "Bar", value: "bar" },
  { label: "Sobremesa", value: "dessert" },
];
const viewModeOptions = [
  { label: "Cards", value: "grid" },
  { label: "Tabela", value: "table" },
];

const tableStatuses = {
  free: "Livre",
  occupied: "Ocupada",
  reserved: "Reservada",
  cleaning: "Limpeza",
};

const isMenuCatalog = computed(() => props.endpoint.includes("/menu/products"));
const isTableCards = computed(() => props.endpoint.includes("/tables"));
const isCardResource = computed(() => isTableCards.value);
const selectedRowTitle = computed(() => {
  if (isTableCards.value && selectedRow.value) return `Mesa ${selectedRow.value.number || "-"}`;
  return selectedRow.value?.name || selectedRow.value?.trade_name || selectedRow.value?.username || selectedRow.value?.id || "-";
});
const menuStats = computed(() => {
  const active = rows.value.filter((item) => item.is_active).length;
  const prices = rows.value.map((item) => Number(item.current_price || 0)).filter((price) => price > 0);
  const averagePrice = prices.length ? prices.reduce((sum, price) => sum + price, 0) / prices.length : 0;
  return { active, averagePrice };
});
const tableStats = computed(() => ({
  free: rows.value.filter((table) => table.status === "free").length,
  busy: rows.value.filter((table) => ["occupied", "reserved"].includes(table.status)).length,
  capacity: rows.value.reduce((sum, table) => sum + Number(table.capacity || 0), 0),
}));

/* ── Detail drawer: per-type configuration ─────────────────────────── */
const orderStatuses = {
  open: "Aberto", sent_to_kitchen: "Cozinha", preparing: "Preparo", partially_ready: "Parcial",
  ready: "Pronto", delivered: "Entregue", awaiting_payment: "Pagamento", paid: "Pago",
  cancelled: "Cancelado", refunded: "Estornado",
};
const orderTypes = { table: "Mesa", command: "Comanda", counter: "Balcao", delivery: "Delivery", takeaway: "Retirada", internal: "Interno" };
const profileTypes = { admin: "Admin", owner: "Proprietario", manager: "Gerente", waiter: "Garcom", kitchen: "Cozinha", cashier: "Caixa", driver: "Entregador" };
const cashStatuses = { open: "Aberto", closed: "Fechado" };

const detailType = computed(() => {
  const e = props.endpoint;
  if (e.includes("/menu/products")) return "product";
  if (e.includes("/orders")) return "order";
  if (e.includes("/tables")) return "table";
  if (e.includes("/customers")) return "customer";
  if (e.includes("/cash-register")) return "cash";
  if (e.includes("/menu/categories")) return "category";
  if (e.includes("/menu/ingredients")) return "ingredient";
  if (e.includes("/menu/recipes")) return "recipe";
  if (e.includes("/menu/menus")) return "menu";
  if (e.includes("/menu/addons")) return "addon";
  if (e.includes("/stock/movements")) return "stock";
  if (e.includes("/stock/locations")) return "location";
  if (e.includes("/delivery/zones")) return "zone";
  if (e.includes("/delivery/deliverymen")) return "deliveryman";
  if (e.includes("/payments/methods")) return "paymentMethod";
  if (e.includes("/payments")) return "payment";
  if (e.includes("/invoices")) return "invoice";
  if (e.includes("/printers")) return "printer";
  if (e.includes("/restaurants")) return "restaurant";
  if (e.includes("/branches")) return "branch";
  if (e.includes("/users")) return "user";
  if (e.includes("/roles")) return "role";
  if (e.includes("/kitchen/stations")) return "station";
  return "generic";
});

const DETAIL_META = {
  order: {
    icon: "pi-receipt", accent: "violet", eyebrow: "Pedido", badgeKey: "status",
    title: (r) => `Pedido #${r.sequence ?? "-"}`,
    subtitle: (r) => orderTypes[r.order_type] || "Pedido",
    badge: (r) => ({ value: orderStatuses[r.status] || r.status }),
    metrics: [
      { label: "Total", key: "total", type: "money" },
      { label: "Mesa", key: "table_number" },
      { label: "Cliente", key: "customer_name" },
    ],
  },
  table: {
    icon: "pi-table", accent: "blue", eyebrow: "Mesa", badgeKey: "status",
    title: (r) => `Mesa ${r.number || "-"}`,
    subtitle: (r) => r.sector_name || "Sem setor",
    badge: (r) => ({ value: tableStatuses[r.status] || r.status }),
    metrics: [{ label: "Capacidade", key: "capacity", suffix: " lugares" }],
  },
  customer: {
    icon: "pi-user", accent: "teal", eyebrow: "Cliente",
    title: (r) => r.name || "Cliente",
    subtitle: (r) => r.phone || r.email || "Sem contato",
  },
  cash: {
    icon: "pi-wallet", accent: "green", eyebrow: "Caixa", badgeKey: "status",
    title: () => "Caixa",
    subtitle: (r) => cashStatuses[r.status] || r.status,
    badge: (r) => ({ value: cashStatuses[r.status] || r.status }),
    metrics: [
      { label: "Abertura", key: "opening_amount", type: "money" },
      { label: "Esperado", key: "expected_amount", type: "money" },
    ],
  },
  user: {
    icon: "pi-user", accent: "indigo", eyebrow: "Usuario", badgeKey: "profile.profile_type",
    title: (r) => r.first_name || r.username || "Usuario",
    subtitle: (r) => r.email || r.username,
    badge: (r) => ({ value: profileTypes[r.profile?.profile_type] || r.profile?.profile_type || "-" }),
  },
  payment: {
    icon: "pi-dollar", accent: "teal", eyebrow: "Pagamento",
    title: (r) => money(r.amount),
    subtitle: (r) => r.payment_method?.name || "Pagamento",
    metrics: [
      { label: "Valor", key: "amount", type: "money" },
      { label: "Troco", key: "change_amount", type: "money" },
    ],
  },
  ingredient: {
    icon: "pi-box", accent: "amber", eyebrow: "Ingrediente",
    title: (r) => r.name || "Ingrediente",
    subtitle: (r) => `Unidade: ${r.unit || "-"}`,
    metrics: [
      { label: "Custo medio", key: "average_cost", type: "money" },
      { label: "Estoque min.", key: "minimum_stock" },
    ],
  },
  station: {
    icon: "pi-desktop", accent: "green", eyebrow: "Estacao KDS",
    title: (r) => r.name || "Estacao",
    subtitle: (r) => r.restaurant_name || "-",
    metrics: [{ label: "SLA", key: "sla_minutes", suffix: " min" }],
  },
  branch: {
    icon: "pi-sitemap", accent: "blue", eyebrow: "Filial",
    title: (r) => r.name || "Filial",
    subtitle: (r) => r.restaurant_name || "-",
  },
  restaurant: { icon: "pi-building", accent: "violet", eyebrow: "Restaurante", subtitle: (r) => r.city || r.legal_name || "-" },
  category: { icon: "pi-tags", accent: "indigo", eyebrow: "Categoria" },
  recipe: { icon: "pi-book", accent: "amber", eyebrow: "Receita" },
  menu: { icon: "pi-bookmark", accent: "indigo", eyebrow: "Cardapio" },
  addon: { icon: "pi-plus-circle", accent: "teal", eyebrow: "Adicional" },
  stock: { icon: "pi-database", accent: "amber", eyebrow: "Movimentacao" },
  location: { icon: "pi-map-marker", accent: "slate", eyebrow: "Local de estoque" },
  zone: { icon: "pi-map", accent: "blue", eyebrow: "Zona de entrega" },
  deliveryman: { icon: "pi-truck", accent: "green", eyebrow: "Entregador" },
  paymentMethod: { icon: "pi-credit-card", accent: "teal", eyebrow: "Forma de pagamento" },
  invoice: { icon: "pi-file", accent: "indigo", eyebrow: "Nota fiscal" },
  printer: { icon: "pi-print", accent: "slate", eyebrow: "Impressora" },
  role: { icon: "pi-shield", accent: "rose", eyebrow: "Perfil de acesso" },
  generic: { icon: "pi-folder-open", accent: "slate", eyebrow: "Registro" },
};

const detailMeta = computed(() => {
  const base = { icon: "pi-folder-open", accent: "slate", eyebrow: "Registro", metrics: [], title: () => selectedRowTitle.value, subtitle: null, badge: null };
  return { ...base, ...(DETAIL_META[detailType.value] || {}) };
});

const heroBadge = computed(() => {
  if (!selectedRow.value || !detailMeta.value.badge) return null;
  return detailMeta.value.badge(selectedRow.value);
});

const detailMetrics = computed(() => {
  if (!selectedRow.value) return [];
  return (detailMeta.value.metrics || []).map((m) => {
    let display = formatField(selectedRow.value, m.key, m.type, m.map);
    if (m.suffix && display !== "-") display = `${display}${m.suffix}`;
    return { label: m.label, display };
  });
});

const detailFields = computed(() => {
  if (!selectedRow.value) return [];
  const excluded = new Set((detailMeta.value.metrics || []).map((m) => m.key));
  if (detailMeta.value.badgeKey) excluded.add(detailMeta.value.badgeKey);
  return props.columns
    .filter((column) => !excluded.has(column.key))
    .map((column) => ({ ...column, _value: value(selectedRow.value, column) }));
});

function formatField(row, key, type, map) {
  const cellValue = get(row, key);
  if (type === "money") return money(cellValue);
  if (type === "date") return dateTime(cellValue);
  if (type === "boolean") return cellValue ? "Ativo" : "Inativo";
  if (cellValue == null || cellValue === "") return "-";
  return map ? map[cellValue] || cellValue : cellValue;
}

async function loadRows() {
  loading.value = true;
  error.value = "";
  try {
    const params = { ...props.defaultParams };
    if (search.value) params.search = search.value;
    if (isMenuCatalog.value) {
      if (activeFilter.value !== "all") params.is_active = activeFilter.value;
      if (typeFilter.value !== "all") params.product_type = typeFilter.value;
      if (sectorFilter.value !== "all") params.production_sector = sectorFilter.value;
    }
    const response = await api.get(props.endpoint, { params, skipRestaurantScope: props.globalScope });
    applyResponse(response.data);
  } catch {
    error.value = "Nao foi possivel carregar os dados.";
    rows.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}


async function loadUrl(url) {
  if (!url) return;
  loading.value = true;
  error.value = "";
  try {
    const { path, params } = parseApiUrl(url);
    const response = await api.get(path, { params, skipRestaurantScope: props.globalScope });
    applyResponse(response.data);
  } catch {
    error.value = "Nao foi possivel carregar a pagina.";
  } finally {
    loading.value = false;
  }
}

function applyResponse(data) {
  rows.value = data.results || data || [];
  total.value = data.count ?? rows.value.length;
  nextUrl.value = data.next || "";
  previousUrl.value = data.previous || "";
  page.value = pageFromUrl(previousUrl.value, nextUrl.value);

  if (selectedRow.value) {
    selectedRow.value = rows.value.find((row) => row.id === selectedRow.value.id) || selectedRow.value;
  }
}


function openDetail(row) {
  selectedRow.value = row;
  detailOpen.value = true;
}

function goToCreate() {
  router.push({ name: `${route.name}--novo` });
}

function goToEdit(id) {
  detailOpen.value = false;
  router.push({ name: `${route.name}--editar`, params: { id } });
}

function pageFromUrl(previous, next) {
  const nextPage = queryPage(next);
  if (nextPage) return nextPage - 1;
  const previousPage = queryPage(previous);
  if (previousPage) return previousPage + 1;
  return 1;
}

function queryPage(url) {
  if (!url) return null;
  const parsed = new URL(url, window.location.origin);
  return Number(parsed.searchParams.get("page") || 1);
}

function parseApiUrl(url) {
  const parsed = new URL(url, window.location.origin);
  const path = parsed.pathname.replace("/api/v1", "");
  const params = Object.fromEntries(parsed.searchParams.entries());
  return { path, params };
}

function value(row, column) {
  return column.value ? column.value(row) : get(row, column.key);
}

function get(row, path) {
  return path.split(".").reduce((current, key) => (current == null ? current : current[key]), row);
}

function label(cellValue, map) {
  if (cellValue == null || cellValue === "") return "-";
  return map?.[cellValue] || cellValue;
}

function money(cellValue) {
  return Number(cellValue || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function dateTime(cellValue) {
  if (!cellValue) return "-";
  return new Date(cellValue).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function quantity(cellValue) {
  return Number(cellValue || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

function percent(cellValue) {
  return `${Number(cellValue || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function progressValue(cellValue) {
  return Math.max(0, Math.min(100, Number(cellValue || 0)));
}

function tableStatusLabel(cellValue) {
  return tableStatuses[cellValue] || "Status";
}

function tableStatusSeverity(cellValue) {
  if (cellValue === "free") return "success";
  if (cellValue === "occupied") return "danger";
  if (cellValue === "reserved") return "info";
  if (cellValue === "cleaning") return "warning";
  return "secondary";
}

function typeIcon(type) {
  const icons = {
    meal: "pi pi-shop",
    drink: "pi pi-cup",
    dessert: "pi pi-star",
    combo: "pi pi-sparkles",
    addon: "pi pi-plus-circle",
    input: "pi pi-box",
  };
  return icons[type] || "pi pi-image";
}

function fallbackClass(item) {
  return `food-fallback food-fallback--${item.product_type || "meal"}`;
}

function imageUrl(image) {
  if (!image) return "";
  if (/^https?:\/\//.test(image)) return image;
  const apiRoot = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  return image.startsWith("/") ? `${apiRoot}${image}` : `${apiRoot}/${image}`;
}

function columnBodyStyle(column) {
  return {
    textAlign: column.align === "right" ? "right" : "left",
    whiteSpace: "nowrap",
  };
}

watch(
  () => props.endpoint,
  () => {
    activeFilter.value = "all";
    typeFilter.value = "all";
    sectorFilter.value = "all";
    selectedRow.value = null;
    detailOpen.value = false;
    viewMode.value = "grid";
    loadRows();
  },
);

onMounted(() => {
  loadRows();
});
</script>

<style scoped>
.resource-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.menu-hero {
  min-height: 188px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.72fr);
  gap: 18px;
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.1), transparent 46%),
    linear-gradient(45deg, rgba(22, 163, 74, 0.1), transparent 50%),
    var(--surface-card);
  overflow: hidden;
}

.menu-hero__copy {
  max-width: 640px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
}

.menu-hero__eyebrow {
  width: fit-content;
  padding: 6px 10px;
  border-radius: var(--radius-pill);
  background: var(--surface-card);
  color: var(--info-text);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.menu-hero h2 {
  max-width: 620px;
  font: var(--weight-extra) 32px/1.08 var(--font-sans);
  color: var(--text-strong);
}

.menu-hero p {
  max-width: 520px;
  color: var(--text-muted);
  font: var(--weight-medium) 14px/1.6 var(--font-sans);
}

.menu-hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-content: end;
}

.menu-metric {
  min-height: 104px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 7px;
  padding: 16px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-sm);
}

[data-theme="dark"] .menu-metric {
  background: rgba(24, 24, 27, 0.74);
}

.menu-metric span {
  color: var(--text-strong);
  font: var(--weight-extra) 24px/1 var(--font-sans);
}

.menu-metric small {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1.3 var(--font-sans);
}

.menu-metric--green {
  border-color: rgba(22, 163, 74, 0.24);
}

.menu-metric--blue {
  border-color: rgba(37, 99, 235, 0.24);
}

.table-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.82fr);
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
}

.table-overview__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.table-overview__copy span {
  color: var(--info-text);
  font: var(--weight-extra) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

.table-overview__copy h2 {
  color: var(--text-strong);
  font: var(--weight-extra) 22px/1.18 var(--font-sans);
}

.table-overview__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.table-overview__metrics div {
  min-height: 78px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.table-overview__metrics strong {
  color: var(--text-strong);
  font: var(--weight-extra) 22px/1 var(--font-sans);
}

.table-overview__metrics span {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
}

.resource-toolbar {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  padding: 10px;
  overflow: visible;
}

.resource-toolbar__search {
  width: min(420px, 46vw);
}

.resource-toolbar__actions {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 8px;
}

.resource-filter {
  min-width: 148px;
  flex-shrink: 0;
}

.resource-error {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 14px;
  color: var(--danger-text);
  background: var(--danger-subtle);
  border: 1px solid rgba(220, 38, 38, 0.16);
  border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}


.table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 14px;
}

.table-card {
  min-height: 236px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  overflow: hidden;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out), border-color var(--dur-base) var(--ease-out);
}

.table-card:hover,
.table-card:focus-visible {
  transform: translateY(-2px);
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: var(--shadow-md);
}

.table-card--loading {
  cursor: default;
}

.table-card--free {
  border-top: 4px solid #047857;
}

.table-card--occupied {
  border-top: 4px solid #b91c1c;
}

.table-card--reserved {
  border-top: 4px solid #1d4ed8;
}

.table-card--cleaning {
  border-top: 4px solid #b45309;
}

.table-card__head,
.table-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.table-card__icon {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--info-text);
}

.table-card__main {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 70px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, rgba(29, 78, 216, 0.08), rgba(4, 120, 87, 0.08)), var(--surface-sunken);
}

.table-card__main span {
  color: var(--text-muted);
  font: var(--weight-extra) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

.table-card__main strong {
  color: var(--text-strong);
  font: var(--weight-extra) 34px/1 var(--font-sans);
}

.table-card__meta {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.table-card__meta div {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1.2 var(--font-sans);
}

.table-card__meta i {
  color: var(--text-subtle);
  font-size: 13px;
}

.table-card__meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-card__footer {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.table-card__footer > span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font: var(--weight-extra) 11px/1 var(--font-sans);
}

.table-card__footer > span::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #475569;
}

.table-card__footer > span.on::before {
  background: #047857;
}

.resource-panel {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
}

.resource-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border-bottom: 1px solid var(--border-subtle);
}

.resource-panel__header h2 {
  color: var(--text-strong);
  font: var(--font-card-title);
}

.resource-panel__header p {
  margin-top: 4px;
  color: var(--text-muted);
  font: var(--font-caption);
}

.cell-text {
  max-width: 280px;
  display: inline-block;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}

.strong {
  color: var(--text-strong);
  font-weight: var(--weight-bold);
}

.muted {
  color: var(--text-muted);
}

.resource-empty {
  min-height: 260px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-muted);
  text-align: center;
}

.resource-empty--table {
  min-height: 180px;
}

.resource-empty i {
  color: var(--text-subtle);
  font-size: 28px;
}

.resource-empty strong {
  color: var(--text-strong);
  font: var(--weight-bold) 15px/1.2 var(--font-sans);
}

.resource-empty span {
  font: var(--weight-medium) 13px/1.4 var(--font-sans);
}

.resource-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.resource-footer span {
  color: var(--text-muted);
  font: var(--weight-semibold) 12px/1 var(--font-sans);
}

.detail-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.detail-header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.detail-header div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.detail-header span {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.detail-header strong {
  overflow: hidden;
  color: var(--text-strong);
  font: var(--weight-extra) 17px/1.2 var(--font-sans);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-detail {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.item-detail__hero {
  height: 220px;
  overflow: hidden;
  border-radius: var(--radius-lg);
}

.item-detail__hero img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.item-detail__fallback {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: rgba(255, 255, 255, 0.92);
}

.item-detail__fallback i {
  font-size: 38px;
}

.food-fallback--meal    { background: linear-gradient(135deg, #1d4ed8, #0f766e 52%, #16a34a); }
.food-fallback--drink   { background: linear-gradient(135deg, #2563eb, #0891b2 52%, #14b8a6); }
.food-fallback--dessert { background: linear-gradient(135deg, #1d4ed8, #4f46e5 48%, #0d9488); }
.food-fallback--combo   { background: linear-gradient(135deg, #0369a1, #2563eb 48%, #059669); }
.food-fallback--addon,
.food-fallback--input   { background: linear-gradient(135deg, #047857, #0f766e 48%, #2563eb); }

.item-detail__title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.item-detail__title span {
  display: block;
  margin-bottom: 4px;
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
}

.item-detail__title h3 {
  color: var(--text-strong);
  font: var(--weight-extra) 22px/1.15 var(--font-sans);
}

.item-detail__title strong {
  flex-shrink: 0;
  color: var(--info-text);
  font: var(--weight-extra) 18px/1 var(--font-sans);
}

.item-detail__description {
  color: var(--text-muted);
  font: var(--weight-medium) 13.5px/1.65 var(--font-sans);
}

.item-detail__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.item-detail__stats div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.item-detail__stats i {
  color: var(--info-text);
}

.item-detail__stats span,
.item-detail__section-head span,
.item-detail__muted {
  color: var(--text-muted);
  font: var(--weight-semibold) 11px/1.2 var(--font-sans);
}

.item-detail__stats strong {
  color: var(--text-strong);
  font: var(--weight-extra) 13px/1.2 var(--font-sans);
}

.item-detail__section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.item-detail__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.item-detail__section-head h4 {
  color: var(--text-strong);
  font: var(--weight-extra) 14px/1.2 var(--font-sans);
}

.availability-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

@media (max-width: 480px) {
  .availability-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.availability-grid span {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  background: var(--surface-card);
  font: var(--weight-bold) 12px/1 var(--font-sans);
}

.availability-grid span.on {
  color: var(--success-text);
  background: var(--success-subtle);
  border-color: rgba(22, 163, 74, 0.18);
}

.detail-list {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.detail-list__row,
.generic-detail__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-list__row:last-child,
.generic-detail__row:last-child {
  border-bottom: none;
}

.detail-list__row span,
.generic-detail__row span {
  min-width: 0;
  overflow: hidden;
  color: var(--text-body);
  font: var(--weight-semibold) 12.5px/1.25 var(--font-sans);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-list__row strong,
.generic-detail__row strong {
  flex-shrink: 0;
  color: var(--text-strong);
  font: var(--weight-bold) 12px/1 var(--font-sans);
}

.generic-detail {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

/* ── Rich detail drawer (per-type) ─────────────────────────────────── */
.rich-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.rich-detail__hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  border-radius: var(--radius-lg);
  color: #fff;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.rich-detail__avatar {
  width: 58px;
  height: 58px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.18);
  font-size: 25px;
}

.rich-detail__headline {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rich-detail__headline span {
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
  opacity: 0.85;
}

.rich-detail__headline h3 {
  overflow: hidden;
  font: var(--weight-extra) 23px/1.15 var(--font-sans);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rich-detail__headline p {
  font: var(--weight-semibold) 13px/1.3 var(--font-sans);
  opacity: 0.92;
}

.rich-detail__badge {
  flex-shrink: 0;
  padding: 6px 12px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.32);
  color: #fff;
  font: var(--weight-extra) 12px/1 var(--font-sans);
  white-space: nowrap;
}

.rich-detail__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
}

.rich-detail__metric {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.rich-detail__metric span {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.rich-detail__metric strong {
  color: var(--text-strong);
  font: var(--weight-extra) 19px/1.1 var(--font-sans);
}

.rich-detail__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--border-subtle);
}

.rich-detail__field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 13px 15px;
  background: var(--surface-card);
}

.rich-detail__field-label {
  color: var(--text-muted);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

.rich-detail__field-value {
  color: var(--text-strong);
  font: var(--weight-semibold) 13.5px/1.4 var(--font-sans);
  word-break: break-word;
}

.rich-detail__field-money {
  color: var(--success-text);
  font: var(--weight-extra) 14.5px/1 var(--font-sans);
}

.rich-accent--violet  { background: linear-gradient(135deg, #7c3aed, #4f46e5); }
.rich-accent--blue    { background: linear-gradient(135deg, #2563eb, #1d4ed8); }
.rich-accent--green   { background: linear-gradient(135deg, #059669, #047857); }
.rich-accent--amber   { background: linear-gradient(135deg, #d97706, #b45309); }
.rich-accent--rose    { background: linear-gradient(135deg, #e11d48, #be123c); }
.rich-accent--teal    { background: linear-gradient(135deg, #0d9488, #0f766e); }
.rich-accent--indigo  { background: linear-gradient(135deg, #4338ca, #3730a3); }
.rich-accent--slate   { background: linear-gradient(135deg, #475569, #334155); }

@media (max-width: 640px) {
  .rich-detail__fields {
    grid-template-columns: 1fr;
  }
}

:deep(.p-toolbar) {
  gap: 10px;
  overflow: visible;
  flex-wrap: nowrap;
}

:deep(.p-toolbar-group-start) {
  min-width: 0;
  flex: 1 1 auto;
}

:deep(.p-toolbar-group-end) {
  min-width: 0;
  flex: 0 0 auto;
}

:deep(.p-inputtext),
:deep(.p-dropdown),
:deep(.p-selectbutton .p-button),
:deep(.p-button) {
  font-family: var(--font-sans);
}

:deep(.p-inputtext) {
  width: 100%;
  height: 40px;
}

:deep(.p-dropdown) {
  height: 40px;
  align-items: center;
}

:deep(.p-dropdown-label) {
  display: flex;
  align-items: center;
  padding: 0 0 0 12px;
  font: var(--weight-semibold) 12px/1 var(--font-sans);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:deep(.p-dropdown-panel) {
  z-index: 9999 !important;
}

:deep(.p-selectbutton .p-button) {
  height: 40px;
  padding: 0 12px;
}

:deep(.resource-datatable .p-datatable-thead > tr > th) {
  padding: 12px 16px;
  border-color: var(--border-subtle);
  color: var(--text-subtle);
  background: var(--surface-sunken);
  font: var(--weight-extra) 11px/1 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}

:deep(.resource-datatable .p-datatable-tbody > tr) {
  color: var(--text-body);
  background: var(--surface-card);
  cursor: pointer;
}

:deep(.resource-datatable .p-datatable-tbody > tr > td) {
  padding: 13px 16px;
  border-color: var(--border-subtle);
  font: var(--weight-medium) 13px/1.25 var(--font-sans);
}

:deep(.resource-datatable .p-datatable-tbody > tr:hover) {
  background: var(--surface-hover);
}

:deep(.p-tag) {
  border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans);
}

:deep(.p-tag.p-tag-info) {
  background: #1d4ed8;
  border-color: #1e40af;
  color: #fff;
}

:deep(.p-tag.p-tag-success) {
  background: #047857;
  border-color: #065f46;
  color: #fff;
}

:deep(.p-tag.p-tag-warning) {
  background: #b45309;
  border-color: #92400e;
  color: #fff;
}

:deep(.p-tag.p-tag-danger) {
  background: #b91c1c;
  border-color: #991b1b;
  color: #fff;
}

:deep(.p-tag.p-tag-secondary) {
  background: #475569;
  border-color: #334155;
  color: #fff;
}

/* ── Status chip: uma cor sólida por valor ─────────────────────────── */
.status-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 99px;
  border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans);
  white-space: nowrap;
  color: #fff;
  background: #475569;
}

/* Pedidos — cor única por status */
.status-chip[data-status="open"]             { background: #2563eb; border-color: #1d4ed8; }
.status-chip[data-status="sent_to_kitchen"]  { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="preparing"]        { background: #4338ca; border-color: #3730a3; }
.status-chip[data-status="partially_ready"]  { background: #0891b2; border-color: #0e7490; }
.status-chip[data-status="ready"]            { background: #059669; border-color: #047857; }
.status-chip[data-status="delivered"]        { background: #16a34a; border-color: #15803d; }
.status-chip[data-status="awaiting_payment"] { background: #d97706; border-color: #b45309; }
.status-chip[data-status="paid"]             { background: #047857; border-color: #065f46; }
.status-chip[data-status="cancelled"]        { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="refunded"]         { background: #be185d; border-color: #9d174d; }

/* Mesas */
.status-chip[data-status="free"]      { background: #047857; border-color: #065f46; }
.status-chip[data-status="occupied"]  { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="reserved"]  { background: #1d4ed8; border-color: #1e40af; }
.status-chip[data-status="cleaning"]  { background: #b45309; border-color: #92400e; }

/* Caixa / fiscal */
.status-chip[data-status="closed"]    { background: #475569; border-color: #334155; }
.status-chip[data-status="issued"]    { background: #047857; border-color: #065f46; }
.status-chip[data-status="draft"]     { background: #64748b; border-color: #475569; }
.status-chip[data-status="error"]     { background: #b91c1c; border-color: #991b1b; }

/* Estoque */
.status-chip[data-status="in"]          { background: #047857; border-color: #065f46; }
.status-chip[data-status="out"]         { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="adjustment"]  { background: #b45309; border-color: #92400e; }
.status-chip[data-status="sale"]        { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="inventory"]   { background: #475569; border-color: #334155; }

/* Usuários */
.status-chip[data-status="admin"]    { background: #b91c1c; border-color: #991b1b; }
.status-chip[data-status="owner"]    { background: #7c3aed; border-color: #6d28d9; }
.status-chip[data-status="manager"]  { background: #1d4ed8; border-color: #1e40af; }
.status-chip[data-status="waiter"]   { background: #0891b2; border-color: #0e7490; }
.status-chip[data-status="kitchen"]  { background: #d97706; border-color: #b45309; }
.status-chip[data-status="cashier"]  { background: #059669; border-color: #047857; }
.status-chip[data-status="driver"]   { background: #475569; border-color: #334155; }

:deep(.item-detail-panel.p-sidebar) {
  min-width: 40rem;
  width: min(1080px, 96vw);
  display: flex;
  flex-direction: column;
  color: var(--text-body);
  background: var(--surface-card);
}

:deep(.item-detail-panel .p-sidebar-header) {
  flex-shrink: 0;
  padding: 20px 22px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

:deep(.item-detail-panel .p-sidebar-content) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
  scrollbar-width: thin;
  scrollbar-color: var(--border-subtle) transparent;
}

.drawer-footer {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-card);
}

@media (max-width: 1100px) {
  :deep(.item-detail-panel.p-sidebar) {
    min-width: unset;
    width: min(860px, 96vw);
  }
}

@media (max-width: 900px) {
  :deep(.item-detail-panel.p-sidebar) {
    width: min(680px, 96vw);
  }
}

@media (max-width: 640px) {
  :deep(.item-detail-panel.p-sidebar) {
    width: 100vw;
  }

  :deep(.item-detail-panel .p-sidebar-header) {
    padding: 16px 16px 12px;
  }

  .drawer-body {
    padding: 16px;
  }

  .drawer-footer {
    padding: 12px 16px;
  }
}

:deep(.p-progressbar) {
  height: 9px;
  border-radius: var(--radius-pill);
  background: var(--surface-sunken);
}

:deep(.p-progressbar-value) {
  background: linear-gradient(90deg, var(--info), var(--success));
}

@media (max-width: 1180px) {
  .menu-hero {
    grid-template-columns: 1fr;
  }

  .table-overview {
    grid-template-columns: 1fr;
  }

  .menu-hero__metrics {
    align-content: stretch;
  }
}

@media (max-width: 860px) {
  :deep(.p-toolbar) {
    flex-wrap: wrap;
  }

  :deep(.p-toolbar-group-start) {
    flex: 1 1 100%;
  }

  :deep(.p-toolbar-group-end) {
    flex: 1 1 100%;
  }

  .resource-toolbar__search {
    width: 100%;
  }

  .resource-toolbar__actions {
    width: 100%;
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .resource-filter {
    flex: 1 1 140px;
    min-width: 0;
  }

  .resource-toolbar__actions :deep(.p-button),
  .view-mode {
    flex: 1 1 auto;
  }
}

@media (max-width: 640px) {
  .menu-hero {
    padding: 18px;
  }

  .menu-hero h2 {
    font-size: 25px;
  }

  .menu-hero__metrics,
  .table-overview__metrics,
  .item-detail__stats {
    grid-template-columns: 1fr;
  }

  .resource-footer {
    justify-content: stretch;
  }

  .resource-footer :deep(.p-button) {
    flex: 1;
  }
}
</style>
