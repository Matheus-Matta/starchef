<template>
  <div class="pdv-page">
    <header class="pdv-page__top">
      <div>
        <h1 class="pdv-page__title">Comandas</h1>
        <p class="pdv-page__subtitle">
          O que cada cartão tem agora, o que ele já teve, e a conferência para o cliente.
        </p>
      </div>
      <button class="pdv-btn pdv-btn--ghost" type="button" @click="voltar">
        Voltar à venda
      </button>
    </header>

    <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>
    <p v-if="recado" class="pdv-notice pdv-notice--ok" role="status">{{ recado }}</p>

    <div class="comandas__grade">
      <section class="comandas__coluna">
        <CommandScannerInput
          ref="scanner"
          :disabled="carregando"
          hint="Passe o cartão para abrir a comanda direto."
          @scan="abrirPorCodigo"
        />

        <input
          v-model="busca"
          class="pdv-field"
          type="text"
          placeholder="Filtrar por número, código ou cliente…"
        />

        <CommandPickerList
          :comandas="visiveis"
          :selecionada-id="selecionada?.id || null"
          :carregando="carregando"
          :vazio="comandas.length ? 'Nenhuma comanda encontrada.' : 'Nenhuma comanda cadastrada.'"
          @pick="selecionar"
        />
      </section>

      <aside class="comandas__detalhe">
        <CommandItemsPanel
          v-if="selecionada"
          :key="selecionada.id"
          :command="selecionada"
          :restaurant-id="selecionada.restaurant"
          @printed="avisarImpressao"
          @table-changed="recarregarSelecionada"
        />
        <p v-else class="pdv-empty">
          Escolha uma comanda à esquerda, ou passe o cartão no leitor.
        </p>
      </aside>
    </div>
  </div>
</template>

<script setup>
/**
 * A tela das comandas no PDV.
 *
 * Nasce como rota própria dentro do `PdvLayout`, igual à conta agrupada: o
 * trilho, a barra de estado e as medidas vêm da casca, e quem alterna entre a
 * web e o desktop durante o turno não sente a troca.
 *
 * Ela existe porque duas perguntas do balcão não tinham onde ser respondidas:
 *
 * - **"o que tem nesta comanda?"** — e a resposta precisa continuar certa
 *   depois da conta agrupada, quando os itens passam a viver no pedido
 *   consolidado e só `OrderItem.command` sabe de quem cada um é;
 * - **"me dá a conta da comanda 13"** — a conferência em papel, que não é
 *   documento fiscal e por isso nunca saiu pelo caminho do cupom.
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import CommandItemsPanel from "../components/pdv/CommandItemsPanel.vue";
import CommandPickerList from "../components/pdv/CommandPickerList.vue";
import CommandScannerInput from "../components/pdv/CommandScannerInput.vue";
import { api } from "../services/api";
import { findCommandByCode } from "../services/commandService";

const router = useRouter();
const scanner = ref(null);

const comandas = ref([]);
const selecionada = ref(null);
const busca = ref("");
const carregando = ref(false);
const erro = ref("");
const recado = ref("");

const visiveis = computed(() => {
  const termo = busca.value.trim().toLowerCase();
  if (!termo) return comandas.value;
  return comandas.value.filter((comanda) =>
    [comanda.number, comanda.code, comanda.customer_name]
      .filter(Boolean)
      .some((campo) => String(campo).toLowerCase().includes(termo)),
  );
});

async function carregar() {
  carregando.value = true;
  erro.value = "";
  try {
    const { data } = await api.get("/commands/", { params: { page_size: 200, is_active: true } });
    comandas.value = data?.results || data || [];
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || "Não foi possível carregar as comandas.";
  } finally {
    carregando.value = false;
  }
}

/**
 * Relê a lista e reapresenta o MESMO cartão, com a mesa nova.
 *
 * Só atualizar o campo em memória deixaria a lista da esquerda dizendo uma
 * coisa e o detalhe outra — e é a lista que o operador usa para achar o
 * cartão da mesa 12.
 */
async function recarregarSelecionada() {
  const id = selecionada.value?.id;
  await carregar();
  if (id) selecionada.value = comandas.value.find((item) => item.id === id) || null;
  recado.value = "Mesa atualizada.";
}

function selecionar(comanda) {
  selecionada.value = comanda;
  recado.value = "";
}

/**
 * O leitor é um teclado: ele digita o código e manda Enter.
 *
 * Resolve pelo `by-code` e não filtra a lista em memória de propósito — o
 * cartão pode ser de uma comanda que a página ainda não carregou.
 */
async function abrirPorCodigo(codigo) {
  carregando.value = true;
  erro.value = "";
  recado.value = "";
  try {
    const comanda = await findCommandByCode(codigo);
    selecionada.value = comanda;
    if (!comandas.value.some((item) => item.id === comanda.id)) await carregar();
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || `Comanda "${codigo}" não encontrada.`;
  } finally {
    carregando.value = false;
    scanner.value?.focus();
  }
}

function avisarImpressao() {
  recado.value = "Conferência enviada para a impressora.";
}

function voltar() {
  router.push({ name: "pdv-venda" });
}

onMounted(carregar);
</script>

<style scoped>
/* Só a GRADE desta página. O resto do vocabulário visual (moldura, cartão,
   selo, aviso, vazio) vive em `styles/pdv-panels.css`, compartilhado com as
   outras telas do posto. */
.comandas__grade {
  display: grid;
  grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.comandas__coluna {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.comandas__detalhe {
  min-height: 0;
}

@media (max-width: 900px) {
  .comandas__grade {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
