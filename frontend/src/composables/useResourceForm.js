import { computed, reactive, ref, unref } from "vue";

import { api } from "../services/api";
import { applyTenantDefaults } from "../utils/tenantDefaults";
import { normalizeApiError } from "../utils/apiError";

/**
 * Presenter (MVP) da pagina unica de recurso, nos tres modos: ver / criar / editar.
 *
 * Cuida de: carregar o registro, montar o estado do formulario, enviar (POST/PATCH),
 * traduzir os erros de validacao do backend e carregar opcoes de dropdowns remotos.
 * A View apenas renderiza e decide para onde navegar apos salvar.
 *
 * @param {object} options
 * @param {import("../services/ResourceService").ResourceService} options.service
 * @param {Array}  [options.formFields]  Definicao dos campos do formulario.
 * @param {import("vue").Ref<string>} options.mode  "view" | "create" | "edit".
 * @param {import("vue").Ref<string>} options.recordId  Id do registro (ausente no create).
 */
export function useResourceForm({ service, formFields = [], mode, recordId, sharedAcrossRestaurants = false }) {
  const isCreate = computed(() => unref(mode) === "create");
  const isEdit = computed(() => unref(mode) === "edit");
  const isView = computed(() => unref(mode) === "view");
  const isForm = computed(() => isCreate.value || isEdit.value);

  const record = ref(null);
  const fetching = ref(false);
  const fetchError = ref("");
  const saving = ref(false);
  const saveError = ref("");
  const fieldErrors = ref({});
  const remoteOptions = reactive({});

  /** Valores iniciais do formulario a partir dos defaults declarados nos campos. */
  function buildInitialData() {
    const data = {};
    for (const field of formFields) {
      if (field.default !== undefined) data[field.name] = field.default;
      else if (field.type === "boolean") data[field.name] = true;
      else if (field.type === "remote-multiselect") data[field.name] = [];
      else data[field.name] = "";
    }
    return data;
  }

  const formData = reactive(buildInitialData());

  /** Restaura o estado ao trocar de registro/modo (reuso da mesma instancia de View). */
  function reset() {
    Object.assign(formData, buildInitialData());
    record.value = null;
    fetchError.value = "";
    saveError.value = "";
    fieldErrors.value = {};
  }

  /** Carrega o registro (view e edit) e preenche o formulario. */
  async function fetchRecord() {
    const id = unref(recordId);
    if (isCreate.value || !id) return;
    fetching.value = true;
    fetchError.value = "";
    try {
      const data = await service.retrieve(id);
      record.value = data;
      for (const field of formFields) {
        const value = field.name.includes(".") ? getDeep(data, field.name) : data[field.name];
        if (value !== undefined) formData[field.name] = value;
      }
    } catch {
      fetchError.value = "Nao foi possivel carregar o registro.";
    } finally {
      fetching.value = false;
    }
  }

  /** Grava `value` em `target` no caminho `a.b.c` (aninha objetos quando há ponto). */
  function setDeep(target, path, value) {
    const parts = path.split(".");
    let node = target;
    for (let i = 0; i < parts.length - 1; i += 1) {
      if (typeof node[parts[i]] !== "object" || node[parts[i]] === null) node[parts[i]] = {};
      node = node[parts[i]];
    }
    node[parts[parts.length - 1]] = value;
  }

  /** Lê um caminho `a.b.c` de um objeto (undefined se algum nível faltar). */
  function getDeep(source, path) {
    return path.split(".").reduce((acc, key) => (acc == null ? undefined : acc[key]), source);
  }

  /** Converte o formulario no payload, aplicando os casts numericos declarados. */
  function buildPayload() {
    const payload = {};
    for (const field of formFields) {
      let value = formData[field.name];
      const filled = value !== "" && value !== null && value !== undefined;
      if (field.type === "number" && filled) value = parseInt(value, 10);
      else if (field.type === "decimal" && filled) value = parseFloat(value);
      else if (field.type === "json") {
        if (!filled) value = {};
        else if (typeof value === "string") {
          try {
            value = JSON.parse(value);
          } catch {
            fieldErrors.value[field.name] = "Informe um JSON válido.";
            throw new Error(`JSON inválido em ${field.label}`);
          }
        }
      }
      // FK vazio vai como null (e não ""), para o backend limpar o vínculo
      // (ex.: categoria "Sem categoria") ou preencher no servidor (restaurante).
      else if (field.type === "remote-dropdown" && !filled) value = null;
      // Nomes com ponto (ex.: "profile.profile_type") viram objeto aninhado.
      setDeep(payload, field.name, value);
    }
    return payload;
  }

  /**
   * Salva (cria ou atualiza) e devolve o registro persistido.
   * Em caso de erro de validacao, popula fieldErrors/saveError e devolve null.
   */
  async function save() {
    saving.value = true;
    saveError.value = "";
    fieldErrors.value = {};
    try {
      let payload;
      try {
        payload = buildPayload();
      } catch {
        saveError.value = "Revise as configurações avançadas antes de salvar.";
        return null;
      }
      // Recursos compartilhados não recebem restaurante/filial automáticos —
      // pertencem à conta (a todos os restaurantes).
      if (isCreate.value && !sharedAcrossRestaurants) {
        applyTenantDefaults(payload, { skip: formFields.map((field) => field.name) });
      }
      const saved = isEdit.value
        ? await service.update(unref(recordId), payload)
        : await service.create(payload);
      return saved;
    } catch (err) {
      applyServerErrors(err);
      return null;
    } finally {
      saving.value = false;
    }
  }

  // Campos de tenant preenchidos automaticamente (não aparecem no formulário).
  // Quando o backend reclama deles, damos um rótulo e uma orientação clara em vez
  // de um "Este campo é obrigatório" solto que não aponta para nenhum campo visível.
  const TENANT_FIELD_LABELS = { restaurant: "Restaurante", branch: "Filial", account: "Conta" };
  const TENANT_FIELDS = new Set(["restaurant", "branch", "account"]);

  function labelFor(key) {
    const field = formFields.find((item) => item.name === key);
    return field?.label || TENANT_FIELD_LABELS[key] || key;
  }

  /** Traduz o corpo de erro do DRF em mensagens por campo + mensagem geral (STC-014). */
  function applyServerErrors(err) {
    const normalized = normalizeApiError(err);
    // Só mapeia para campos que existem no formulário; erros de campos que não
    // estão no form (ex.: restaurante/filial injetados automaticamente) recebem
    // rótulo na mensagem geral para o usuário saber exatamente o que falta.
    const known = new Set(formFields.map((field) => field.name));
    const mapped = {};
    const orphanMessages = [];
    let tenantScopeIssue = false;
    for (const [key, message] of Object.entries(normalized.fieldErrors)) {
      if (known.has(key)) {
        mapped[key] = message;
      } else {
        orphanMessages.push(`${labelFor(key)}: ${message}`);
        if (TENANT_FIELDS.has(key)) tenantScopeIssue = true;
      }
    }
    fieldErrors.value = mapped;
    const parts = [normalized.message, ...orphanMessages];
    if (tenantScopeIssue) {
      parts.push("Selecione um restaurante no seletor do topo antes de salvar.");
    }
    saveError.value = parts.filter(Boolean).join(" ");
  }

  // Tipos de campo cujas opcoes vem de um endpoint remoto (dropdown simples ou multiplo).
  const REMOTE_OPTION_TYPES = ["remote-dropdown", "remote-multiselect"];

  /** Carrega as opcoes dos dropdowns remotos — necessario tanto no form quanto no modo
   * "ver" (a view reusa o mesmo form desabilitado e precisa dos rotulos, nao so dos ids). */
  async function loadRemoteOptions() {
    for (const field of formFields) {
      if (!REMOTE_OPTION_TYPES.includes(field.type) || !field.endpoint) continue;
      try {
        // globalScope: ignora o filtro automático por restaurante (ex.: o próprio
        // seletor de restaurante deve listar todos, não só o do escopo atual).
        const res = await api.get(field.endpoint, { params: { page_size: 200 }, skipRestaurantScope: !!field.globalScope });
        const rows = res.data.results || res.data || [];
        remoteOptions[field.name] = rows.map((row) => ({
          label: String(row[field.optionLabel ?? "name"] ?? row.id),
          value: row[field.optionValue ?? "id"],
          // Rótulo do grupo (usado por campos `grouped`, ex.: catálogo de permissões).
          group: row[field.optionGroup ?? "group"] ?? "",
          description: String(row.description ?? ""),
        }));
      } catch {
        remoteOptions[field.name] = [];
      }
    }
  }

  return {
    // modos
    isCreate, isEdit, isView, isForm,
    // estado
    record, formData, fetching, fetchError, saving, saveError, fieldErrors, remoteOptions,
    // acoes
    reset, fetchRecord, save, loadRemoteOptions,
  };
}
