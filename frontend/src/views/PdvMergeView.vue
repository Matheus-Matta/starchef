<template>
  <div class="conta">
    <header class="conta__topo">
      <div>
        <h1 class="conta__titulo">Conta agrupada</h1>
        <p class="conta__subtitulo">
          Várias comandas, um pagamento só. Os itens entram num pedido único na hora de confirmar.
        </p>
      </div>
      <button class="conta__sair" type="button" @click="voltar">Voltar à venda</button>
    </header>

    <p v-if="error" class="conta__aviso" :class="{ 'conta__aviso--conflito': conflict }" role="alert">
      {{ error }}
    </p>

    <section v-if="!merge" class="conta__inicio">
      <p class="conta__instrucao">
        Passe o cartão da <strong>primeira comanda</strong> para abrir a conta.
      </p>
      <CommandScannerInput :disabled="loading" @scan="abrir" />
    </section>

    <div v-else class="conta__grade">
      <section class="conta__coluna">
        <CommandScannerInput
          v-if="isOpen"
          ref="scanner"
          :disabled="loading"
          hint="Escanear a mesma comanda de novo não duplica nada."
          @scan="incluir"
        />
        <p v-else-if="isPaid" class="conta__instrucao conta__instrucao--travada">
          Conta paga. Corrigir agora exige o estorno auditado, que desfaz caixa,
          estoque e nota e esvazia todas as comandas.
        </p>
        <p v-else class="conta__instrucao conta__instrucao--travada">
          Conta confirmada. Para corrigir um item, desfaça a consolidação antes de receber.
        </p>

        <div class="conta__grupos">
          <MergeCommandGroup
            v-for="grupo in itemsByCommand"
            :key="grupo.commandId"
            :group="grupo"
            :table-number="mesaDa(grupo.commandId)"
            :removable="isOpen && itemsByCommand.length > 1"
            :disabled="loading"
            @remove="retirar"
            @receipt="conferir"
          />
          <p v-if="!itemsByCommand.length" class="conta__vazio">
            Nenhum item nesta conta ainda.
          </p>
        </div>
      </section>

      <aside class="conta__resumo">
        <h2 class="conta__resumo-titulo">Resumo</h2>
        <dl class="conta__linhas">
          <div><dt>Comandas</dt><dd>{{ sources.length }}</dd></div>
          <div><dt>Itens</dt><dd>{{ items.length }}</dd></div>
          <div><dt>Subtotal</dt><dd>{{ money(subtotal) }}</dd></div>
          <div><dt>Serviço</dt><dd>{{ money(serviceFee) }}</dd></div>
          <div v-if="discount > 0"><dt>Desconto</dt><dd>- {{ money(discount) }}</dd></div>
        </dl>
        <p class="conta__taxa-nota">
          A taxa é a soma das taxas de cada comanda, já arredondadas — não um percentual
          novo sobre o total.
        </p>
        <p class="conta__total">
          <span>Total</span>
          <strong>{{ money(total) }}</strong>
        </p>

        <button
          v-if="isOpen"
          class="conta__acao conta__acao--principal"
          type="button"
          :disabled="loading || !sources.length"
          @click="confirmar"
        >
          Confirmar conta
        </button>
        <button
          v-else-if="isConfirmed"
          class="conta__acao conta__acao--principal"
          type="button"
          :disabled="loading"
          @click="receber"
        >
          Receber pagamento
        </button>

        <button
          v-if="!isPaid"
          class="conta__acao"
          type="button"
          :disabled="loading"
          @click="desfazer"
        >
          Desfazer conta
        </button>
        <!-- Estornar NÃO é desfazer: aqui já entrou dinheiro, e a operação
             cancela os cartões reentregues. Por isso ele só aparece na conta
             paga, com cor de alerta e pedindo o motivo. -->
        <button
          v-else
          class="conta__acao conta__acao--perigo"
          type="button"
          :disabled="loading"
          @click="estornar"
        >
          Estornar venda
        </button>
      </aside>
    </div>
  </div>
</template>

<script setup>
/**
 * A tela em que o caixa monta a conta de várias comandas.
 *
 * Ela nasce como rota própria, e não dentro de `PdvView.vue`, por uma razão
 * prática: aquele arquivo tem 2800 linhas e a conta agrupada tem um ciclo de
 * vida próprio (abrir → incluir → confirmar → receber), com o seu próprio
 * estado de conflito entre dois caixas.
 *
 * O que a tela precisa fazer, e que o modelo sozinho não garante:
 *
 * - **Mostrar os itens, não só o total.** A conferência com o cliente acontece
 *   ali, e é ela que pega o engano antes de virar discussão.
 * - **Mostrar a comanda de cada item.** Com quatro comandas numa conta, "de
 *   quem é isto" é a pergunta que o cliente faz.
 * - **Distinguir conflito de erro de digitação.** Um 409 ("outro caixa já
 *   incluiu esta comanda") não se resolve tentando de novo.
 */
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import CommandScannerInput from "../components/pdv/CommandScannerInput.vue";
import MergeCommandGroup from "../components/pdv/MergeCommandGroup.vue";
import { useOrderMerge } from "../composables/useOrderMerge";
import { api } from "../services/api";

const route = useRoute();
const router = useRouter();
const scanner = ref(null);

const {
  merge,
  loading,
  error,
  conflict,
  sources,
  items,
  itemsByCommand,
  subtotal,
  serviceFee,
  discount,
  total,
  isOpen,
  isConfirmed,
  isPaid,
  targetOrderId,
  start,
  load,
  include,
  exclude,
  confirm,
  discard,
  refund,
  receipt,
} = useOrderMerge();

if (route.query.merge) load(String(route.query.merge));

/** A mesa vem da COMANDA, não do pedido: comandas de mesas diferentes podem
 *  entrar na mesma conta, e o pedido agrupado não tem mesa nenhuma. */
const mesasPorComanda = computed(() => {
  const mapa = {};
  for (const source of sources.value) {
    mapa[source.command] = source.table_number;
  }
  return mapa;
});

function mesaDa(commandId) {
  return mesasPorComanda.value[commandId] || null;
}

function money(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/**
 * Abrir pede o PEDIDO da comanda, não a comanda: a rota é
 * `POST /orders/{id}/merge/`. A primeira leitura resolve o cartão e usa o
 * pedido de trabalho que já está aberto nele.
 */
async function abrir(referencia) {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.get("/commands/by-code/", { params: { code: referencia } });
    if (!data?.current_order_id) {
      error.value = `A comanda ${data?.number ?? referencia} não tem um pedido aberto.`;
      return;
    }
    loading.value = false;
    await start(data.current_order_id);
  } catch (exc) {
    error.value = exc?.response?.data?.detail || "Comanda não encontrada.";
  } finally {
    loading.value = false;
  }
}

async function incluir(referencia) {
  await include(referencia);
  scanner.value?.focus();
}

async function retirar(commandId) {
  await exclude(commandId);
}

async function confirmar() {
  await confirm();
}

async function desfazer() {
  const desfeita = await discard("Desfeita no PDV");
  if (desfeita) router.push({ name: "pdv-venda" });
}

/**
 * Estorna a venda já paga.
 *
 * Confirma com o operador em texto, e não só com um "tem certeza?": ele precisa
 * ler que o cartão já reentregue vai ter o pedido do próximo cliente cancelado
 * junto. É a consequência que não se descobre clicando.
 */
async function estornar() {
  const motivo = window.prompt(
    "Estornar a venda agrupada cancela o pagamento, devolve o estoque, cancela a nota "
      + "e ESVAZIA todas as comandas — inclusive cancelando o pedido de um cartão que já "
      + "tenha sido reentregue a outro cliente.\n\nMotivo do estorno:",
  );
  if (!motivo || !motivo.trim()) return;
  const relatorio = await refund(motivo.trim());
  if (!relatorio) return;
  const descartados = relatorio.reused_orders_discarded || [];
  const aviso = descartados.length
    ? ` Pedidos de cartões reentregues cancelados: ${descartados.map((o) => o.sequence).join(", ")}.`
    : "";
  window.alert(`Venda estornada. ${relatorio.commands_emptied.length} comanda(s) esvaziada(s).${aviso}`);
  router.push({ name: "pdv-venda" });
}

/** Imprime a conferência de uma comanda da conta. Não é nota fiscal. */
async function conferir(commandId) {
  const resultado = await receipt(commandId);
  if (resultado) window.alert("Conferência enviada para a impressora.");
}

/** Depois de confirmada, o recebimento é o de sempre: pela rota do destino. */
function receber() {
  router.push({ name: "pdv", query: { order: targetOrderId.value } });
}

function voltar() {
  router.push({ name: "pdv-venda" });
}
</script>

<style scoped>
.conta {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  height: 100%;
  box-sizing: border-box;
}

.conta__topo {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.conta__titulo {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.conta__subtitulo {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-color-secondary, #6b7280);
}

.conta__sair {
  border: 1px solid var(--surface-border, #e5e7eb);
  background: transparent;
  color: inherit;
  border-radius: 8px;
  padding: 8px 14px;
  cursor: pointer;
  font: inherit;
}

.conta__aviso {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fef3c7;
  color: #92400e;
  font-size: 14px;
}

/* Conflito tem cor própria: "outro caixa já incluiu esta comanda" não se
   resolve tentando de novo, e a tela não pode sugerir que sim. */
.conta__aviso--conflito {
  background: #fee2e2;
  color: #991b1b;
}

.conta__inicio {
  max-width: 560px;
}

.conta__instrucao {
  margin: 0 0 12px;
  font-size: 15px;
}

.conta__instrucao--travada {
  color: var(--text-color-secondary, #6b7280);
}

.conta__grade {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.conta__coluna {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.conta__grupos {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
  min-height: 0;
}

.conta__vazio {
  color: var(--text-color-secondary, #6b7280);
  font-size: 14px;
}

.conta__resumo {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 10px;
  background: var(--surface-card, #fff);
  align-self: flex-start;
}

.conta__resumo-titulo {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.conta__linhas {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
}

.conta__linhas > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.conta__linhas dt,
.conta__linhas dd {
  margin: 0;
}

.conta__linhas dd {
  font-variant-numeric: tabular-nums;
}

.conta__taxa-nota {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-color-secondary, #6b7280);
}

.conta__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin: 4px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--surface-border, #e5e7eb);
  font-size: 15px;
}

.conta__total strong {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}

.conta__acao {
  height: 44px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.conta__acao--principal {
  border-color: transparent;
  background: var(--primary-color, #2563eb);
  color: #fff;
}

.conta__acao--perigo {
  border-color: #dc2626;
  color: #b91c1c;
}

.conta__acao:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .conta__grade {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
