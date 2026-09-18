<template>
  <section class="krules">
    <header class="krules__head">
      <div><h3>Regras da estação</h3><p>Filtre pedidos e mova cards automaticamente entre colunas.</p></div>
      <button class="krules__add" type="button" @click="openRule()"><i class="pi pi-plus" /> Nova regra</button>
    </header>
    <div v-if="!rules.length" class="krules__empty">Sem regras: a estação mantém o comportamento anterior por setor.</div>
    <article v-for="(rule, index) in rules" :key="rule.id" class="krule" :class="{ 'krule--off': !rule.enabled }">
      <span class="krule__order">{{ index + 1 }}</span>
      <div class="krule__body">
        <strong>{{ rule.name }}</strong>
        <small>{{ summary(rule) }}</small>
      </div>
      <button class="krule__toggle" type="button" @click="toggle(index)">{{ rule.enabled ? "Ativa" : "Inativa" }}</button>
      <button class="krule__icon" type="button" :disabled="index === 0" title="Subir" @click="reorder(index, -1)"><i class="pi pi-arrow-up" /></button>
      <button class="krule__icon" type="button" :disabled="index === rules.length - 1" title="Descer" @click="reorder(index, 1)"><i class="pi pi-arrow-down" /></button>
      <button class="krule__icon" type="button" title="Editar" @click="openRule(rule, index)"><i class="pi pi-pencil" /></button>
      <button class="krule__icon krule__icon--danger" type="button" title="Excluir" @click="remove(index)"><i class="pi pi-times" /></button>
    </article>

    <div v-if="form.open" class="krules-modal" @click.self="form.open = false">
      <div class="krules-modal__box">
        <h3>{{ form.index === null ? "Nova regra" : "Editar regra" }}</h3>
        <div class="krules-modal__grid">
          <label>Nome<input v-model="form.name" type="text" placeholder="Ex.: Atrasados após 5 minutos" /></label>
          <label>Ação<select v-model="form.action"><option value="include">Incluir pedido</option><option value="exclude">Não exibir pedido</option><option value="move">Mover para coluna</option></select></label>
          <label v-if="form.action === 'move'">Coluna de destino<select v-model="form.target_column"><option value="">Selecione…</option><option v-for="column in columns" :key="column.id" :value="column.id">{{ column.name }}</option></select></label>
          <label>Combinação<select v-model="form.match"><option value="all">Todas as condições</option><option value="any">Qualquer condição</option></select></label>
        </div>
        <div class="krules-modal__conditions">
          <div class="krules-modal__condition-head"><strong>Condições</strong><button type="button" @click="addCondition"><i class="pi pi-plus" /> Condição</button></div>
          <div v-if="!form.conditions.length" class="krules__empty">Sem condição = sempre.</div>
          <div v-for="(condition, index) in form.conditions" :key="index" class="kcondition">
            <select v-model="condition.field" @change="resetCondition(condition)"><option v-for="field in FIELDS" :key="field.value" :value="field.value">{{ field.label }}</option></select>
            <select v-model="condition.operator"><option v-for="operator in operatorsFor(condition.field)" :key="operator.value" :value="operator.value">{{ operator.label }}</option></select>
            <select v-if="valuesFor(condition.field).length && needsValue(condition.operator)" v-model="condition.value"><option value="">Selecione…</option><option v-for="value in valuesFor(condition.field)" :key="value.value" :value="value.value">{{ value.label }}</option></select>
            <input v-else-if="needsValue(condition.operator)" v-model="condition.value" :type="isMinutes(condition.field) ? 'number' : 'text'" :min="isMinutes(condition.field) ? 0 : undefined" placeholder="Valor" />
            <span v-else class="kcondition__no-value">sem valor</span>
            <button type="button" title="Remover condição" @click="form.conditions.splice(index, 1)"><i class="pi pi-times" /></button>
          </div>
        </div>
        <p v-if="error" class="krules-modal__error">{{ error }}</p>
        <footer><label class="krules__check"><input v-model="form.enabled" type="checkbox" /> Regra ativa</label><button type="button" @click="form.open = false">Cancelar</button><button class="krules__save" type="button" :disabled="saving || !canSave" @click="saveRule">Salvar regra</button></footer>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { FIELDS, OPERATORS, fieldValues, ruleSummary } from "../../utils/kdsRules";

const props = defineProps({ station: { type: Object, required: true } });
const emit = defineEmits(["saved"]);
const rules = ref([]);
const saving = ref(false);
const error = ref("");
const columns = computed(() => (props.station.columns || []).filter((column) => column.is_active));
const blank = () => ({ open: false, index: null, id: "", name: "", action: "include", match: "all", target_column: "", enabled: true, conditions: [] });
const form = reactive(blank());

watch(() => props.station, (station) => { rules.value = structuredClone(station.rules || []); }, { immediate: true, deep: true });
const canSave = computed(() => form.name.trim() && (form.action !== "move" || form.target_column));
function valuesFor(field) { return fieldValues(field); }
function isMinutes(field) { return field.startsWith("minutes_"); }
function needsValue(operator) { return !["true", "false"].includes(operator); }
function operatorsFor(field) { return ["has_customer_note", "has_table", "has_command"].includes(field) ? OPERATORS.boolean : (isMinutes(field) ? OPERATORS.number : OPERATORS.text); }
function resetCondition(condition) { condition.operator = operatorsFor(condition.field)[0].value; condition.value = ""; }
function addCondition() { form.conditions.push({ field: "order_type", operator: "equals", value: "" }); }
function summary(rule) { return ruleSummary(rule, props.station.columns || []); }
function openRule(rule, index = null) { error.value = ""; Object.assign(form, rule ? structuredClone({ ...rule, open: true, index }) : { ...blank(), open: true }); }

async function persist(next) {
  saving.value = true; error.value = "";
  try {
    const payload = next.map((rule, index) => ({ ...rule, priority: index }));
    const { data } = await api.patch(`/kitchen/stations/${props.station.id}/`, { rules: payload });
    rules.value = structuredClone(data.rules || []); emit("saved", data);
  } catch (err) { error.value = normalizeApiError(err).message; }
  finally { saving.value = false; }
}
async function saveRule() {
  const rule = { id: form.id || `rule-${Date.now()}`, name: form.name.trim(), action: form.action, match: form.match, target_column: form.action === "move" ? form.target_column : null, enabled: form.enabled, conditions: structuredClone(form.conditions) };
  const next = [...rules.value]; if (form.index === null) next.push(rule); else next.splice(form.index, 1, rule);
  await persist(next); if (!error.value) form.open = false;
}
function remove(index) { if (window.confirm("Excluir esta regra?")) persist(rules.value.filter((_, position) => position !== index)); }
function toggle(index) { const next = structuredClone(rules.value); next[index].enabled = !next[index].enabled; persist(next); }
function reorder(index, delta) { const next = structuredClone(rules.value); [next[index], next[index + delta]] = [next[index + delta], next[index]]; persist(next); }
</script>

<style scoped>
.krules{display:flex;flex-direction:column;gap:8px;margin-top:8px;padding-top:16px;border-top:1px solid var(--border)}.krules__head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.krules h3{margin:0;color:var(--text-strong);font:var(--weight-extra) 15px/1.2 var(--font-sans)}.krules p{margin:3px 0 0;color:var(--text-muted);font:var(--weight-medium) 11.5px/1.4 var(--font-sans)}.krules__add,.krules-modal button{height:34px;padding:0 11px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-card);color:var(--text-body);cursor:pointer}.krules__empty{padding:12px;color:var(--text-muted);font-size:12px;text-align:center;border:1px dashed var(--border);border-radius:var(--radius-md)}.krule{display:flex;align-items:center;gap:7px;padding:9px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-sunken)}.krule--off{opacity:.6}.krule__order{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--brand-subtle);color:var(--text-brand);font-weight:800}.krule__body{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0}.krule__body strong{font-size:13px;color:var(--text-strong)}.krule__body small{font-size:11px;color:var(--text-muted)}.krule__toggle{border:0;background:var(--success-subtle);color:var(--success-text);font-size:10px;font-weight:800}.krule__icon{width:30px;height:30px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface-card);color:var(--text-muted);cursor:pointer}.krule__icon--danger{color:var(--danger-text)}.krule__icon:disabled{opacity:.35}.krules-modal{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:16px;background:rgba(0,0,0,.55)}.krules-modal__box{width:min(760px,100%);max-height:90vh;overflow:auto;display:flex;flex-direction:column;gap:14px;padding:20px;background:var(--surface-card);border-radius:var(--radius-lg)}.krules-modal__grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.krules-modal label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:700;color:var(--text-strong)}.krules-modal input,.krules-modal select{height:38px;padding:0 10px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-ground);color:var(--text-body)}.krules-modal__conditions{display:flex;flex-direction:column;gap:8px}.krules-modal__condition-head{display:flex;justify-content:space-between;align-items:center}.kcondition{display:grid;grid-template-columns:1.2fr 1fr 1fr 34px;gap:7px}.kcondition__no-value{display:flex;align-items:center;color:var(--text-subtle);font-size:11px}.krules-modal__error{color:var(--danger-text)!important}.krules-modal footer{display:flex;align-items:center;justify-content:flex-end;gap:8px}.krules-modal footer .krules__check{margin-right:auto;flex-direction:row;align-items:center}.krules-modal .krules__save{background:var(--brand);border-color:var(--brand);color:var(--on-brand)}@media(max-width:650px){.krules-modal__grid{grid-template-columns:1fr}.kcondition{grid-template-columns:1fr}.krule{flex-wrap:wrap}.krule__body{flex-basis:70%}}
</style>
