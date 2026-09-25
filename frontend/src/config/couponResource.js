/**
 * O cadastro do cupom de desconto.
 *
 * Separado da promoção porque é outro assunto, e não outra intensidade do mesmo:
 * promoção muda o preço da vitrine para todo mundo sem ninguém pedir, cupom é um
 * direito de UMA pessoa, que precisa ser reconhecida e contada. Daí os campos
 * que só existem aqui — limite, CPF, grupo.
 *
 * A IDENTIDADE É O CPF da nota. Não existe "cliente selecionado" à parte: no
 * caixa, o que a pessoa informa é o CPF, e é por ele que grupo e cliente são
 * conferidos.
 */
import {
  COUPON_KIND_LABELS,
  COUPON_KIND_OPTIONS,
  ORDER_TYPE_OPTIONS_FOR_COUPON,
} from "./enums";

export const couponResource = {
  name: "cupons",
  title: "Cupons de desconto",
  endpoint: "/promotions/coupons/",
  columns: [
    { key: "code", label: "Codigo" },
    { key: "discount_kind", label: "Tipo", type: "status", map: COUPON_KIND_LABELS },
    { key: "discount_value", label: "Valor", align: "right" },
    { key: "minimum_order_value", label: "Minimo", type: "money", align: "right" },
    { key: "usage_count", label: "Usos", align: "right" },
    { key: "ends_at", label: "Vence em", type: "date" },
    { key: "is_enabled", label: "Ligado", type: "boolean" },
  ],
  formFields: [
    {
      name: "code",
      label: "Codigo do cupom",
      type: "text",
      maxlength: 40,
      required: true,
      section: "Identificacao",
      hint: "Guardado em MAIUSCULAS e sem espacos: o cliente dita por telefone e o caixa digita.",
    },
    { name: "name", label: "Nome interno", type: "text", maxlength: 140, section: "Identificacao" },
    {
      name: "description",
      label: "Descricao",
      type: "text",
      maxlength: 255,
      full: true,
      section: "Identificacao",
    },

    {
      name: "discount_kind",
      label: "Tipo de desconto",
      type: "dropdown",
      options: COUPON_KIND_OPTIONS,
      default: "percent",
      required: true,
      section: "Desconto",
    },
    {
      name: "discount_value",
      label: "Valor do desconto",
      type: "decimal",
      section: "Desconto",
      hint: "Percentual: 10 = 10%. Em reais: 10 = R$ 10. Entrega gratis ignora este campo.",
    },
    {
      name: "max_discount_amount",
      label: "Teto do desconto (R$)",
      type: "decimal",
      section: "Desconto",
      hint: "So para percentual. 20% sem teto num pedido de mil reais sao duzentos reais que ninguem aprovou.",
    },
    // O MINIMO NAO CONTA TAXA DE SERVICO NEM ENTREGA, e o hint diz isso porque
    // e a pergunta que quem cadastra faz em voz alta.
    {
      name: "minimum_order_value",
      label: "Compra minima (R$)",
      type: "decimal",
      section: "Desconto",
      hint: "Conta so PRODUTOS: sem taxa de servico e sem entrega. Um pedido de R$ 44 de comida que chega a 50 pelo frete nao libera o cupom de R$ 50.",
    },

    { name: "starts_at", label: "Comeca em", type: "datetime", section: "Validade" },
    {
      name: "ends_at",
      label: "Vence em",
      type: "datetime",
      section: "Validade",
      hint: "Vazio = nao expira.",
    },
    { name: "is_enabled", label: "Ligado", type: "boolean", default: true, section: "Validade" },

    {
      name: "usage_limit",
      label: "Limite total de usos",
      type: "number",
      default: 0,
      section: "Limites",
      hint: "0 = ilimitado.",
    },
    {
      name: "usage_limit_per_customer",
      label: "Usos por cliente",
      type: "number",
      default: 0,
      section: "Limites",
      hint: "0 = ilimitado. Contado por CPF.",
    },
    {
      name: "single_use_per_customer",
      label: "Compra unica por cliente",
      type: "boolean",
      section: "Limites",
      hint: "Equivale a 1 uso por CPF.",
    },
    {
      name: "first_purchase_only",
      label: "So na primeira compra",
      type: "boolean",
      section: "Limites",
      hint: "Vale para quem ainda nao tem pedido PAGO.",
    },

    // A IDENTIDADE E O CPF. Nao existe "cliente selecionado" a parte: no caixa,
    // o que a pessoa informa e o CPF, e e por ele que grupo e cliente sao
    // conferidos.
    {
      name: "requires_document",
      label: "Exige CPF na nota",
      type: "boolean",
      section: "Quem pode usar",
      hint: "O CPF do pedido e a identidade do cupom. Cupom restrito a grupo ou a cliente exige CPF mesmo com isto desmarcado: sem ele nao existe a quem comparar.",
    },
    {
      name: "customer_groups",
      label: "Grupos de clientes",
      type: "remote-multiselect",
      endpoint: "/customers/groups/",
      optionLabel: "name",
      optionValue: "id",
      full: true,
      section: "Quem pode usar",
      hint: "Vazio = todos os grupos.",
    },
    {
      name: "customers",
      label: "Clientes especificos",
      type: "remote-multiselect",
      endpoint: "/customers/",
      optionLabel: "name",
      optionValue: "id",
      full: true,
      section: "Quem pode usar",
      hint: "Vazio = todos os clientes.",
    },
    {
      name: "order_types",
      label: "Tipos de pedido aceitos",
      type: "multiselect",
      options: ORDER_TYPE_OPTIONS_FOR_COUPON,
      full: true,
      section: "Quem pode usar",
      hint: "Vazio = todos os tipos.",
    },
    {
      name: "combines_with_promotions",
      label: "Acumula com promocao",
      type: "boolean",
      default: true,
      section: "Quem pode usar",
      hint: "Desligado, o cupom e recusado em pedido que ja tem item em promocao.",
    },
  ],
};
