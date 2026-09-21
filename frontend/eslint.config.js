import js from "@eslint/js";
import vue from "eslint-plugin-vue";

export default [
  {
    // O que NUNCA é nosso código.
    //
    // O bloco `files` abaixo já mira `src/`, mas ele só escolhe onde as regras
    // valem — não impede o ESLint de ABRIR o resto. Sem esta lista, um
    // `npx eslint .` (sem o script do package.json) entra no bundle de
    // produção e devolve centenas de erros de código minificado, que ninguém
    // escreveu e ninguém pode corrigir. Isso treina a equipe a ignorar a
    // saída do lint, que é o pior resultado possível de uma porta de
    // qualidade.
    ignores: ["dist/**", "coverage/**", "node_modules/**", "public/**"],
  },
  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["src/**/*.{js,vue}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        document: "readonly",
        localStorage: "readonly",
        window: "readonly",
      },
    },
    rules: {
      // Permite o padrão `const { omit1, omit2, ...rest } = obj` para descartar chaves.
      "no-unused-vars": ["error", { ignoreRestSiblings: true }],

      // ── O que foi apertado, e por que cada um está aqui ──────────────────
      //
      // O critério é o mesmo do `backend/pyproject.toml`: entra o que aponta
      // DEFEITO; fica de fora o que só discorda de uma escolha. Cada regra
      // abaixo foi medida antes de entrar — todas já estavam limpas, então
      // elas travam a porta sem pedir um mutirão de correção.

      // `==` compara com coerção: `0 == ""` é verdadeiro, e num PDV isso é a
      // diferença entre "sem desconto" e "campo vazio". O modo `smart` deixa
      // passar `x == null`, que é o idioma para "nulo OU indefinido".
      eqeqeq: ["error", "smart"],

      // `var` vaza do bloco e sobe para o topo da função. Não há um único uso
      // legítimo dele neste código — já estava em zero.
      "no-var": "error",

      // Reatribuir por engano uma referência que nunca muda é fonte de bug em
      // composables; `const` faz o erro aparecer na hora.
      "prefer-const": "error",

      // `console.log` esquecido vaza dado de venda no navegador do cliente.
      // `warn`/`error` continuam liberados: eles são diagnóstico de verdade.
      "no-console": ["error", { allow: ["warn", "error"] }],

      // ── O que fica de fora, e por quê ────────────────────────────────────
      //
      // `complexity`: 36 funções passam de 15 hoje, quase todas nas telas
      // grandes de NF-e. Ligar como erro reprovaria quem não as escreveu. Quem
      // cobra tamanho aqui é a catraca (`scripts/check_tamanho_de_arquivo.py`),
      // que não deixa a dívida crescer sem exigir o mutirão agora.

      "vue/html-self-closing": "off",
      "vue/max-attributes-per-line": "off",
      "vue/multi-word-component-names": "off",
      "vue/no-v-html": "off",
      "vue/no-v-model-argument": "off",
      "vue/singleline-html-element-content-newline": "off",
    },
  },
];
