/**
 * Os cadastros de promoção e cupom.
 *
 * Fora de `resources.js` porque são recursos densos de regra, e porque o
 * arquivo principal já passa de duas mil linhas — quem vem entender "como o
 * desconto é cadastrado" acha tudo aqui, junto.
 *
 * Duas telas aqui: a TABELA agrupa o que vale junto, e a REGRA diz o que
 * desconta. O cupom mora em `couponResource.js` — é outro assunto, não outra
 * intensidade do mesmo.
 */
import { couponResource } from "./couponResource";
import {
  PROMOTION_KIND_LABELS,
  PROMOTION_KIND_OPTIONS,
  PROMOTION_TARGET_LABELS,
  PROMOTION_TARGET_OPTIONS,
} from "./enums";

export const discountTableResource = {
  name: "tabelas-de-desconto",
  title: "Tabelas de desconto",
  endpoint: "/promotions/discount-tables/",
  columns: [
    { key: "name", label: "Tabela" },
    {
      key: "status_label",
      label: "Situacao",
      type: "status",
      map: { Ativa: "Ativa", Agendada: "Agendada", Encerrada: "Encerrada", Desligada: "Desligada" },
    },
    { key: "rule_count", label: "Regras", align: "right" },
    { key: "starts_at", label: "Inicio", type: "date" },
    { key: "ends_at", label: "Fim", type: "date" },
    { key: "is_enabled", label: "Ligada", type: "boolean" },
  ],
  formFields: [
    {
      name: "name",
      label: "Nome da tabela",
      type: "text",
      maxlength: 140,
      required: true,
      full: true,
      hint: "Unico por conta. E o nome que aparece no aviso de preco do produto.",
    },
    { name: "description", label: "Descricao", type: "text", maxlength: 255, full: true },
    // A JANELA E DA TABELA de proposito: ela e o interruptor que uma pessoa
    // apressada consegue achar quando o preco sai errado no caixa.
    {
      name: "starts_at",
      label: "Comeca em",
      type: "datetime",
      hint: "Vazio = vale desde agora.",
    },
    {
      name: "ends_at",
      label: "Termina em",
      type: "datetime",
      hint: "Vazio = nao expira. A tabela para de valer no minuto marcado, sem ninguem salvar nada.",
    },
    {
      name: "restaurant",
      label: "Restaurante (opcional)",
      type: "remote-dropdown",
      endpoint: "/restaurants/",
      optionLabel: "trade_name",
      optionValue: "id",
      globalScope: true,
      hint: "Vazio = vale na conta inteira. Preenchido = so naquela loja.",
    },
    {
      name: "is_enabled",
      label: "Ligada",
      type: "boolean",
      default: true,
      hint: "Desligue aqui para parar TODAS as regras da tabela de uma vez.",
    },
  ],
};

export const promotionRuleResource = {
  name: "regras-de-desconto",
  title: "Regras de desconto",
  endpoint: "/promotions/rules/",
  columns: [
    { key: "position", label: "#", align: "right" },
    { key: "name", label: "Regra" },
    { key: "table_name", label: "Tabela" },
    { key: "target_type", label: "Aplica em", type: "status", map: PROMOTION_TARGET_LABELS },
    { key: "discount_kind", label: "Tipo", type: "status", map: PROMOTION_KIND_LABELS },
    { key: "discount_value", label: "Valor", align: "right" },
    { key: "is_enabled", label: "Ligada", type: "boolean" },
  ],
  formFields: [
    {
      name: "table",
      label: "Tabela de desconto",
      type: "remote-dropdown",
      endpoint: "/promotions/discount-tables/",
      optionLabel: "name",
      optionValue: "id",
      required: true,
      full: true,
    },
    { name: "name", label: "Nome da regra", type: "text", maxlength: 140, required: true },
    // A POSICAO E A PRIORIDADE. E o unico critario que o gerente confere de
    // relance; ordenar por "maior desconto" exigiria simular cada regra.
    {
      name: "position",
      label: "Prioridade",
      type: "number",
      default: 1,
      hint: "Menor numero ganha. Duas regras da mesma tabela nao podem dividir a posicao.",
    },
    {
      name: "target_type",
      label: "Aplica em",
      type: "dropdown",
      options: PROMOTION_TARGET_OPTIONS,
      default: "products",
      required: true,
    },
    {
      name: "discount_kind",
      label: "Tipo de desconto",
      type: "dropdown",
      options: PROMOTION_KIND_OPTIONS,
      default: "percent",
      required: true,
    },
    {
      name: "discount_value",
      label: "Valor do desconto",
      type: "decimal",
      required: true,
      hint: "Percentual: 10 = 10%. Valor abatido: 5 = R$ 5 a menos. Preco fixo: 9,90 = o produto passa a custar isso.",
    },
    {
      name: "categories",
      label: "Categorias",
      type: "remote-multiselect",
      endpoint: "/menu/categories/",
      optionLabel: "name",
      optionValue: "id",
      full: true,
      hint: "Use quando Aplica em for Categorias. O desconto incide sobre o preco de prateleira, e por isso nunca aumenta um preco.",
    },
    {
      name: "sectors",
      label: "Setores",
      type: "remote-multiselect",
      endpoint: "/tables/sectors/",
      optionLabel: "name",
      optionValue: "id",
      full: true,
      hint: "Use quando Aplica em for Setores.",
    },
    {
      name: "starts_at",
      label: "Comeca em (opcional)",
      type: "datetime",
      hint: "Janela propria, DENTRO da janela da tabela. Vazio = herda a tabela.",
    },
    { name: "ends_at", label: "Termina em (opcional)", type: "datetime" },
    { name: "is_enabled", label: "Ligada", type: "boolean", default: true },
  ],
};

export const promotionResources = [discountTableResource, promotionRuleResource, couponResource];
