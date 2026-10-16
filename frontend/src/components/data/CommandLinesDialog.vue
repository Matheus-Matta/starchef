<template>
  <AppEntityDialog
    :visible="visible"
    title="Linhas da comanda da balança"
    save-label="Salvar linhas"
    :saving="salvando"
    :dirty="mudou"
    width="620px"
    @update:visible="emit('update:visible', $event)"
    @save="salvar"
  >
    <p class="cl-ajuda">
      Saem na comanda da pesagem, abaixo do produto, preço do kg, peso e valor, com um traço para escrever e três
      quadrados. Valem para todas as balanças do restaurante. As linhas em branco saem sempre no fim.
    </p>
    <select v-if="!escopo" v-model="restauranteId" class="cl-select" aria-label="Restaurante" @change="carregar">
      <option value="" disabled>Escolha o restaurante</option>
      <option v-for="r in restaurantes" :key="r.id" :value="r.id">{{ r.trade_name || r.legal_name }}</option>
    </select>
    <div class="cl-acoes">
      <Dropdown
        v-model="produtoEscolhido" :options="produtos" option-label="name" option-value="id" filter
        placeholder="Adicionar item do cardápio" :disabled="bloqueado" class="cl-produto" @change="adicionarProduto"
      />
      <InputText
        v-model="titulo" :maxlength="MAXIMO_DO_TITULO" placeholder="Título (ex.: Coca-Cola)" :disabled="bloqueado"
        @keydown.enter.prevent="adicionarTitulo"
      />
      <Button label="Título" icon="pi pi-plus" outlined :disabled="bloqueado || !tituloValido(titulo)" @click="adicionarTitulo" />
      <Button label="Em branco" icon="pi pi-pencil" outlined :disabled="bloqueado" @click="adicionar({ tipo: 'branco' })" />
    </div>
    <p v-if="erro" class="cl-erro">{{ erro }}</p>
    <ol v-if="linhas.length" class="cl-lista">
      <li v-for="(linha, i) in linhas" :key="i" class="cl-linha">
        <span v-if="linha.tipo !== 'branco'" class="cl-nome" :title="rotuloDaLinha(linha, nomes)">{{ rotuloDaLinha(linha, nomes) }}</span>
        <span class="cl-traco" :class="{ 'cl-traco--cheio': linha.tipo === 'branco' }" />
        <span class="cl-quadros"><i /><i /><i /></span>
        <Button icon="pi pi-arrow-up" text rounded aria-label="Subir" :disabled="linha.tipo === 'branco'" @click="linhas = mover(linhas, i, i - 1)" />
        <Button icon="pi pi-arrow-down" text rounded aria-label="Descer" :disabled="linha.tipo === 'branco'" @click="linhas = mover(linhas, i, i + 1)" />
        <Button icon="pi pi-times" text rounded severity="danger" aria-label="Remover" @click="linhas = linhas.filter((_, j) => j !== i)" />
      </li>
    </ol>
    <p v-else class="cl-ajuda">{{ carregando ? "Carregando..." : "Nenhuma linha: a comanda sai só com a pesagem." }}</p>
  </AppEntityDialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Button from "primevue/button";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import { useToast } from "primevue/usetoast";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import { api } from "../../services/api";
import { getBrowserValue } from "../../services/browserPersistence";
import { normalizeApiError } from "../../utils/apiError";
import { MAXIMO_DE_LINHAS, MAXIMO_DO_TITULO, emOrdemDeImpressao, linhasDaApi, mover, rotuloDaLinha, tituloValido } from "./commandLines";

const props = defineProps({ visible: { type: Boolean, default: false } });
const emit = defineEmits(["update:visible"]);
const toast = useToast();

// O restaurante escolhido na barra lateral; sem escopo ("todos"), pergunta.
const escopo = getBrowserValue("starchef-restaurant-scope") || "";
const restauranteId = ref(escopo);
const restaurantes = ref([]);
const produtos = ref([]);
const linhas = ref([]);
const original = ref("[]");
const produtoEscolhido = ref(null);
const titulo = ref("");
const erro = ref("");
const carregando = ref(false);
const salvando = ref(false);

const nomes = computed(() => Object.fromEntries(produtos.value.map((p) => [String(p.id), p.name])));
const mudou = computed(() => JSON.stringify(linhas.value) !== original.value);
const bloqueado = computed(() => !restauranteId.value || carregando.value || linhas.value.length >= MAXIMO_DE_LINHAS);

function adicionar(linha) {
  linhas.value = emOrdemDeImpressao([...linhas.value, linha]);
}
function adicionarProduto() {
  if (produtoEscolhido.value) adicionar({ tipo: "produto", produto: String(produtoEscolhido.value) });
  produtoEscolhido.value = null;
}
function adicionarTitulo() {
  const nome = tituloValido(titulo.value);
  if (!nome || bloqueado.value) return;
  adicionar({ tipo: "texto", nome });
  titulo.value = "";
}

async function carregar() {
  if (!restauranteId.value) return;
  carregando.value = true;
  erro.value = "";
  try {
    const opcoes = { skipRestaurantScope: true };
    const [restaurante, cardapio] = await Promise.all([
      api.get(`/restaurants/${restauranteId.value}/`, opcoes),
      api.get("/menu/products/", { ...opcoes, params: { restaurant: restauranteId.value, is_active: true, page_size: 300 } }),
    ]);
    produtos.value = cardapio.data.results || cardapio.data || [];
    linhas.value = linhasDaApi(restaurante.data.linhas_da_comanda);
    original.value = JSON.stringify(linhas.value);
  } catch (err) {
    erro.value = normalizeApiError(err).message;
  } finally {
    carregando.value = false;
  }
}

async function salvar() {
  salvando.value = true;
  erro.value = "";
  try {
    await api.patch(`/restaurants/${restauranteId.value}/`, { linhas_da_comanda: linhas.value }, { skipRestaurantScope: true });
    original.value = JSON.stringify(linhas.value);
    toast.add({ severity: "success", summary: "Linhas da comanda salvas", life: 3000 });
    emit("update:visible", false);
  } catch (err) {
    erro.value = normalizeApiError(err).message;
  } finally {
    salvando.value = false;
  }
}

watch(() => props.visible, async (aberto) => {
  if (!aberto) return;
  if (!escopo && !restaurantes.value.length) {
    const { data } = await api.get("/restaurants/", { params: { is_active: true, page_size: 200 }, skipRestaurantScope: true });
    restaurantes.value = data.results || data || [];
    if (restaurantes.value.length === 1) restauranteId.value = restaurantes.value[0].id;
  }
  await carregar();
}, { immediate: true });
</script>

<style scoped>
.cl-ajuda { margin: 0 0 12px; color: var(--text-muted); font-size: 13px; }
.cl-erro { margin: 8px 0; color: var(--red-600, #c62828); font-size: 13px; }
.cl-select { width: 100%; height: var(--control-h); margin-bottom: 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
.cl-acoes { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.cl-produto { flex: 1 1 220px; }
.cl-lista { margin: 0; padding: 0; list-style: none; }
.cl-linha { display: flex; align-items: center; gap: 10px; padding: 4px 0; border-bottom: 1px dashed var(--border); }
/* O nome é cortado e os quadrados ficam fixos: como no papel. */
.cl-nome { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.cl-traco { flex: 0 0 90px; height: 16px; border-bottom: 1.5px solid var(--text-body); }
.cl-traco--cheio { flex: 1 1 0; }
.cl-quadros { display: flex; flex: 0 0 auto; gap: 4px; }
.cl-quadros i { width: 18px; height: 18px; border: 1.5px solid var(--text-body); }
</style>
