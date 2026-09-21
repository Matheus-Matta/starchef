<template>
  <div class="pdv-page">
    <p v-if="erro" class="pdv-notice pdv-notice--error" role="alert">{{ erro }}</p>

    <div class="menu__grade">
      <MenuProductGrid
        :produtos="produtos"
        :categorias="categorias"
        :carregando="carregando"
        @pick="rascunho.adicionar"
      />
      <DraftCartPanel
        :itens="rascunho.itens.value"
        :comandas="rascunho.comandas.value"
        :mesa="rascunho.mesa.value"
        :total="rascunho.total.value"
        :quantidade="rascunho.quantidadeDeItens.value"
        :ocupado="rascunho.materializando.value"
        @attach="anexar"
        @detach="rascunho.soltarComanda"
        @quantity="mudarQuantidade"
        @remove="(item) => rascunho.remover(item._id)"
        @kitchen="abrirPedido({ paraCozinha: true })"
        @pay="abrirPedido({ paraCozinha: false })"
      />
    </div>
  </div>
</template>

<script setup>
/**
 * A tela de Venda: o cardápio à esquerda, o carrinho à direita.
 *
 * É o padrão de um PDV de mercado, adaptado ao salão. Passar produtos **não
 * abre nada**: o carrinho vive na memória da tela até alguém de fora precisar
 * do pedido — a cozinha, para imprimir um ticket, ou o caixa, para anexar um
 * recebimento.
 *
 * A comanda é um ATRIBUTO desse rascunho, e não um gesto que cria pedido.
 * Antes, escolher a comanda 13 disparava `open-command` na hora, e desistir
 * deixava o cartão ocupado com um pedido vazio que alguém tinha de cancelar
 * depois.
 *
 * Aberto o pedido, a tela entrega para `/pdv`, que é quem sabe receber, emitir
 * e imprimir. Esta aqui não duplica nada disso.
 */
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import DraftCartPanel from "../components/pdv/DraftCartPanel.vue";
import MenuProductGrid from "../components/pdv/MenuProductGrid.vue";
import { useOrderDraft } from "../composables/useOrderDraft";
import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const rascunho = useOrderDraft();

const produtos = ref([]);
const categorias = ref([]);
const carregando = ref(false);
const erro = ref("");

async function carregarCardapio() {
  carregando.value = true;
  erro.value = "";
  try {
    const [produtosRes, categoriasRes] = await Promise.all([
      api.get("/menu/products/", { params: { is_active: true, page_size: 500 } }),
      api.get("/menu/categories/", { params: { is_active: true, page_size: 100 } }),
    ]);
    produtos.value = produtosRes.data?.results || produtosRes.data || [];
    categorias.value = categoriasRes.data?.results || categoriasRes.data || [];
  } catch (exc) {
    erro.value = exc?.response?.data?.detail || "Não foi possível carregar o cardápio.";
  } finally {
    carregando.value = false;
  }
}

function anexar(comanda) {
  // A mesa vem da COMANDA: é ela que decide a ocupação do salão, e o pedido
  // guarda a mesa só como histórico.
  rascunho.anexarComanda(comanda, comanda?.current_table ? { id: comanda.current_table } : null);
}

function mudarQuantidade(item, delta) {
  rascunho.mudarQuantidade(item._id, Number(item.quantity || 0) + delta);
}

/**
 * A única porta que abre pedido no servidor.
 *
 * O rascunho NÃO é limpo antes da navegação dar certo: se a tela do pedido
 * falhasse ao carregar, o operador perderia o carrinho inteiro e teria de
 * digitar tudo de novo com o cliente na frente.
 */
async function abrirPedido({ paraCozinha }) {
  if (rascunho.vazio.value) return;
  erro.value = "";
  try {
    const pedido = await rascunho.materializar(auth.user?.restaurant_id || null);
    if (paraCozinha) await api.post(`/orders/${pedido.id}/send-to-kitchen/`);
    rascunho.limpar();
    router.push({ name: "pdv", query: { order: pedido.id } });
  } catch (exc) {
    erro.value =
      exc?.response?.data?.detail || exc?.message || "Não foi possível abrir o pedido.";
  }
}

onMounted(carregarCardapio);
</script>

<style scoped>
.menu__grade {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 380px);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

@media (max-width: 1100px) {
  .menu__grade {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
