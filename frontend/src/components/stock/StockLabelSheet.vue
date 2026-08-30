<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="Etiquetas dos lotes"
    :style="{ width: '860px', maxWidth: '95vw' }"
  >
    <div class="labelsheet__bar">
      <span>{{ labels.length }} etiqueta(s) · {{ templateName }}</span>
      <Button label="Imprimir" icon="pi pi-print" size="small" @click="print" />
    </div>

    <!-- A folha visível é a MESMA que vai para a impressora: o que o operador
         confere na tela é literalmente o que sai no papel. -->
    <div ref="sheet" class="labelsheet" :style="sheetStyle">
      <article v-for="(label, index) in labels" :key="`${label.lot_id}-${index}`" class="labelsheet__item" :style="itemStyle">
        <div class="labelsheet__text">
          <strong v-if="show('show_ingredient')" class="labelsheet__name">{{ label.ingredient_name }}</strong>
          <span v-if="show('show_lot_code')" class="labelsheet__code">{{ label.code }}</span>
          <span v-if="show('show_supplier_lot') && label.supplier_lot">Lote forn.: {{ label.supplier_lot }}</span>
          <span v-if="show('show_quantity')">{{ formatQuantity(label) }}</span>
          <span v-if="show('show_entered_at')">Entrada: {{ formatDate(label.entered_at) }}</span>
          <span v-if="show('show_expires_at') && label.expires_at" class="labelsheet__expiry">
            Val.: {{ formatDate(label.expires_at) }}
          </span>
          <span v-if="show('show_location')">{{ label.location_name }}</span>
          <span v-if="template?.custom_text">{{ template.custom_text }}</span>
        </div>
        <img v-if="label.code_uri" class="labelsheet__code-img" :src="label.code_uri" :alt="label.code" />
      </article>
    </div>
  </Dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import Button from "primevue/button";
import Dialog from "primevue/dialog";

/**
 * Folha de etiquetas impressa pelo NAVEGADOR.
 *
 * Não passa pela fila de impressão do agente local de propósito: a fila serve
 * a impressora térmica do balcão, que imprime bobina contínua. Etiqueta
 * adesiva tem largura e altura exatas, e é o `@page`/`mm` do navegador que
 * respeita isso em qualquer impressora que o computador já tenha instalada —
 * sem depender de o agente estar rodando.
 */
const visible = ref(false);
const labels = ref([]);
const template = ref(null);
const sheet = ref(null);

const templateName = computed(() => template.value?.name || "Modelo padrão");

/** Sem modelo cadastrado, tudo aparece: é o comportamento menos surpreendente. */
function show(field) {
  if (!template.value) return true;
  return template.value[field] !== false;
}

const mm = (value, fallback) => Number(value ?? fallback);

const sheetStyle = computed(() => ({
  gridTemplateColumns: `repeat(${Math.max(1, Number(template.value?.columns || 1))}, max-content)`,
}));

const itemStyle = computed(() => ({
  width: `${mm(template.value?.width_mm, 60)}mm`,
  height: `${mm(template.value?.height_mm, 40)}mm`,
  padding: `${mm(template.value?.margin_mm, 2)}mm`,
  fontSize: `${mm(template.value?.font_size_pt, 8)}pt`,
}));

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = String(value).split("-");
  return day ? `${day}/${month}/${year}` : value;
}

function formatQuantity(label) {
  const quantity = Number(label.quantity || 0);
  return `${quantity.toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${label.unit || ""}`.trim();
}

function open(nextLabels, nextTemplate) {
  labels.value = nextLabels || [];
  template.value = nextTemplate || null;
  visible.value = true;
}

function print() {
  const node = sheet.value;
  if (!node) return;
  const width = mm(template.value?.width_mm, 60);
  const height = mm(template.value?.height_mm, 40);
  // Janela própria em vez de `@media print` na página inteira: a folha sai
  // sozinha, sem sidebar, sem cabeçalho e sem o resto do app disputando a
  // caixa de impressão.
  const win = window.open("", "_blank", "width=780,height=620");
  if (!win) return;
  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Etiquetas</title>
    <style>
      @page { size: ${width}mm ${height}mm; margin: 0; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: Arial, Helvetica, sans-serif; }
      .labelsheet { display: block; }
      .labelsheet__item {
        display: flex; align-items: center; justify-content: space-between; gap: 2mm;
        width: ${width}mm; height: ${height}mm; padding: ${mm(template.value?.margin_mm, 2)}mm;
        font-size: ${mm(template.value?.font_size_pt, 8)}pt; overflow: hidden;
        page-break-after: always; break-after: page;
      }
      .labelsheet__item:last-child { page-break-after: auto; break-after: auto; }
      .labelsheet__text { display: flex; flex-direction: column; gap: .4mm; min-width: 0; }
      .labelsheet__name { font-size: 1.15em; }
      .labelsheet__code { font-family: "Courier New", monospace; font-weight: 700; }
      .labelsheet__expiry { font-weight: 700; }
      .labelsheet__code-img { max-height: ${height - 4}mm; max-width: 45%; object-fit: contain; }
    </style></head><body>${node.outerHTML}</body></html>`);
  win.document.close();
  win.focus();
  // `onload` garante que as imagens (data-URI do QR) já estejam decodificadas:
  // imprimir antes disso sai com o espaço do código em branco.
  win.onload = () => win.print();
}

defineExpose({ open });
</script>

<style scoped>
.labelsheet__bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; color: var(--text-muted); font-size: 12.5px; }
.labelsheet { display: grid; gap: 4px; justify-content: start; max-height: 60vh; overflow: auto; padding: 4px; background: var(--surface-sunken); border-radius: var(--radius-md); }
.labelsheet__item { display: flex; align-items: center; justify-content: space-between; gap: 6px; overflow: hidden; border: 1px dashed var(--border-strong); border-radius: 3px; background: #fff; color: #111; }
.labelsheet__text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.labelsheet__name { font-size: 1.15em; }
.labelsheet__code { font-family: "Courier New", monospace; font-weight: 700; }
.labelsheet__expiry { font-weight: 700; }
.labelsheet__code-img { max-width: 45%; max-height: 90%; object-fit: contain; }
</style>
