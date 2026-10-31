import { computed, ref, watch } from "vue";

import { api } from "../services/api";
import { getBrowserValue } from "../services/browserPersistence";
import { useAuthStore } from "../stores/auth";

export const PERIODOS = [
  { value: "dia", label: "Dia" },
  { value: "semana", label: "Semana" },
  { value: "mes", label: "Mês" },
];

const TODOS = "";

/**
 * A Visão Geral (`/reports/overview/`): período (o dia, por padrão) e
 * restaurante escolhidos na própria tela.
 *
 * O restaurante começa no que está selecionado no topo do painel. Escolhido
 * aqui, ele vai explícito e sem o escopo global (`skipRestaurantScope`): o
 * cabeçalho do escopo global, mandado junto, contradiria a escolha da tela.
 */
export function useVisaoGeral() {
  const auth = useAuthStore();
  const periodo = ref("dia");
  const restaurante = ref(getBrowserValue("starchef-restaurant-scope") || TODOS);
  const restaurantes = ref([]);
  const dados = ref({});
  const carregando = ref(false);
  const erro = ref("");

  const podeEscolherRestaurante = computed(() => Boolean(
    auth.user?.is_superuser || ["admin", "owner"].includes(auth.user?.profile_type)));

  async function carregar({ silencioso = false } = {}) {
    if (!silencioso) carregando.value = true;
    erro.value = "";
    try {
      const params = { periodo: periodo.value };
      if (restaurante.value) params.restaurant = restaurante.value;
      const config = podeEscolherRestaurante.value ? { params, skipRestaurantScope: true } : { params };
      const { data } = await api.get("/reports/overview/", config);
      dados.value = data || {};
      restaurantes.value = (data?.options?.restaurants || []).map((item) => ({
        value: item.id, label: item.name,
      }));
    } catch {
      erro.value = "Não foi possível carregar a visão geral.";
    } finally {
      carregando.value = false;
    }
  }

  watch([periodo, restaurante], () => carregar());

  return {
    periodo, restaurante, restaurantes, dados, carregando, erro,
    podeEscolherRestaurante, carregar,
  };
}
