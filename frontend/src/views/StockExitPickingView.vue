<template>
  <div class="picking">
    <header class="picking__head">
      <div>
        <span class="picking__eyebrow">CONFERÊNCIA DE SAÍDA</span>
        <h1>Separação por etiqueta</h1>
        <p>Leia a etiqueta de cada lote indicado. A leitura confirma que saiu o lote certo.</p>
      </div>
      <div class="picking__head-actions">
        <Tag :value="`${confirmedCount} de ${allocations.length} conferidos`" :severity="allConfirmed ? 'success' : 'warning'" rounded />
        <Button label="Voltar" icon="pi pi-arrow-left" text @click="goBack" />
        <Button
          label="Confirmar saída"
          icon="pi pi-check"
          :loading="posting"
          :disabled="!canPost"
          @click="confirmPost"
        />
      </div>
    </header>

    <!-- O campo fica sempre focado: o leitor USB digita e envia Enter, e um
         clique acidental fora do campo faria a próxima leitura se perder. -->
    <section class="picking__scanner" :class="{ 'picking__scanner--error': !!scanError }">
      <i class="pi pi-qrcode" />
      <input
        ref="scanInput"
        v-model="code"
        type="text"
        placeholder="Leia ou digite o código da etiqueta..."
        autocomplete="off"
        spellcheck="false"
        @keyup.enter="submitCode"
        @blur="refocus"
      />
      <Button label="Conferir" size="small" :loading="scanning" @click="submitCode" />
    </section>

    <div v-if="scanError" class="picking__alert picking__alert--error">
      <i class="pi pi-times-circle" /> {{ scanError }}
    </div>
    <div v-if="lastOk" class="picking__alert picking__alert--ok">
      <i class="pi pi-check-circle" /> Lote {{ lastOk }} conferido.
    </div>

    <div v-if="loading" class="picking__card"><Skeleton height="200px" /></div>

    <section v-else class="picking__list">
      <article
        v-for="allocation in allocations"
        :key="allocation.id"
        class="picking__item"
        :class="{ 'picking__item--done': allocation.is_confirmed }"
      >
        <div class="picking__item-status">
          <i :class="allocation.is_confirmed ? 'pi pi-check-circle' : 'pi pi-circle'" />
        </div>
        <div class="picking__item-body">
          <strong>{{ allocation.ingredient_name }}</strong>
          <div class="picking__item-lot">
            Retire o lote <code>{{ allocation.lot_code }}</code>
          </div>
          <div class="picking__item-meta">
            <span>Quantidade: <strong>{{ allocation.suggested_quantity }}</strong></span>
            <span>Entrada: {{ formatDate(allocation.lot_entered_at) }}</span>
            <span v-if="allocation.lot_expires_at" :class="{ 'picking__soon': isSoon(allocation.lot_expires_at) }">
              Validade: {{ formatDate(allocation.lot_expires_at) }}
            </span>
            <span>Saldo no lote: {{ allocation.lot_available }}</span>
          </div>
        </div>
        <Tag
          :value="allocation.is_confirmed ? 'Conferido' : 'Pendente'"
          :severity="allocation.is_confirmed ? 'success' : 'warning'"
          rounded
        />
      </article>

      <div v-if="!allocations.length" class="picking__empty">
        <i class="pi pi-inbox" />
        <p>Nenhum lote separado. Volte e use “Separar lotes”.</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const props = defineProps({ id: { type: String, default: "" } });

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();

const loading = ref(true);
const scanning = ref(false);
const posting = ref(false);
const scanError = ref("");
const lastOk = ref("");
const code = ref("");
const scanInput = ref(null);
const allocations = ref([]);
const requireScan = ref(true);
const status = ref("draft");

const exitId = computed(() => props.id || route.params.id || "");
const confirmedCount = computed(() => allocations.value.filter((item) => item.is_confirmed).length);
const allConfirmed = computed(
  () => allocations.value.length > 0 && confirmedCount.value === allocations.value.length,
);
const canPost = computed(
  () => status.value === "draft" && allocations.value.length > 0 && (!requireScan.value || allConfirmed.value),
);

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = String(value).split("-");
  return day ? `${day}/${month}/${year}` : value;
}

function isSoon(value) {
  if (!value) return false;
  const days = (new Date(value) - new Date()) / 86400000;
  return days <= 7;
}

function refocus() {
  // Devolve o foco no próximo tick para não brigar com o clique que o tirou.
  nextTick(() => scanInput.value?.focus());
}

function goBack() {
  router.push({ name: "estoque-saida-documento", params: { id: exitId.value } });
}

async function submitCode() {
  const value = code.value.trim();
  if (!value || scanning.value) return;
  scanning.value = true;
  scanError.value = "";
  lastOk.value = "";
  try {
    await api.post(`/stock/exits/${exitId.value}/scan_label/`, { code: value });
    lastOk.value = value.toUpperCase();
    code.value = "";
    await load({ silent: true });
  } catch (err) {
    scanError.value = normalizeApiError(err).message;
    // O código errado permanece selecionado: o operador vê o que leu e a
    // próxima leitura o substitui inteiro.
    scanInput.value?.select();
  } finally {
    scanning.value = false;
    refocus();
  }
}

function confirmPost() {
  confirm.require({
    header: "Confirmar a saída?",
    message: "O saldo dos lotes conferidos será baixado. A saída não poderá mais ser editada.",
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Confirmar saída",
    rejectLabel: "Voltar",
    accept: post,
  });
}

async function post() {
  posting.value = true;
  scanError.value = "";
  try {
    await api.post(`/stock/exits/${exitId.value}/post_exit/`, {});
    toast.add({ severity: "success", summary: "Saída confirmada", life: 3500 });
    router.push({ name: "estoque-saida-documento", params: { id: exitId.value } });
  } catch (err) {
    scanError.value = normalizeApiError(err).message;
  } finally {
    posting.value = false;
  }
}

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true;
  try {
    const { data } = await api.get(`/stock/exits/${exitId.value}/`);
    status.value = data.status;
    requireScan.value = !!data.require_label_scan;
    allocations.value = (data.items || []).flatMap((item) => item.allocations || []);
  } catch (err) {
    scanError.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await load();
  refocus();
});
</script>

<style scoped>
.picking { display: flex; flex-direction: column; gap: 16px; max-width: 1000px; margin: 0 auto; }
.picking__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.picking__eyebrow { color: var(--text-brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.picking__head h1 { margin: 7px 0 5px; color: var(--text-strong); font-size: 25px; }
.picking__head p { margin: 0; max-width: 620px; color: var(--text-muted); font-size: 13px; line-height: 1.5; }
.picking__head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.picking__scanner { display: flex; align-items: center; gap: 12px; padding: 16px 18px; border: 2px solid var(--brand-border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.picking__scanner i { color: var(--text-brand); font-size: 22px; }
.picking__scanner input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text-strong); font: var(--weight-bold) 17px/1.2 var(--font-mono, "Courier New", monospace); letter-spacing: .04em; }
.picking__scanner input::placeholder { color: var(--text-subtle); font-weight: var(--weight-medium); letter-spacing: normal; }
.picking__scanner--error { border-color: var(--danger); }

.picking__alert { display: flex; align-items: center; gap: 9px; padding: 12px 14px; border-radius: var(--radius-md); font-size: 13px; }
.picking__alert--error { border: 1px solid var(--danger-border); background: var(--danger-subtle); color: var(--danger-text); }
.picking__alert--ok { border: 1px solid var(--success); background: var(--success-subtle); color: var(--success-text); }

.picking__card { padding: 22px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); }
.picking__list { display: flex; flex-direction: column; gap: 10px; }
.picking__item { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 15px 18px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); }
.picking__item--done { border-color: var(--success); background: var(--success-subtle); }
.picking__item-status i { font-size: 22px; color: var(--text-subtle); }
.picking__item--done .picking__item-status i { color: var(--success); }
.picking__item-body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.picking__item-body strong { color: var(--text-strong); font-size: 14px; }
.picking__item-lot { color: var(--text-body); font-size: 13px; }
.picking__item-lot code { padding: 2px 7px; border-radius: 5px; background: var(--surface-sunken); font-family: "Courier New", monospace; font-weight: 700; }
.picking__item-meta { display: flex; flex-wrap: wrap; gap: 14px; color: var(--text-muted); font-size: 12px; }
.picking__soon { color: var(--warning-text); font-weight: var(--weight-bold); }

.picking__empty { padding: 50px 20px; border: 1px dashed var(--border-strong); border-radius: var(--radius-md); text-align: center; color: var(--text-muted); }
.picking__empty i { font-size: 26px; }
.picking__empty p { margin: 10px 0 0; font-size: 13px; }

@media (max-width: 680px) {
  .picking__head { flex-direction: column; }
  .picking__item { grid-template-columns: 28px minmax(0, 1fr); }
}
</style>
