import js from "@eslint/js";
import vue from "eslint-plugin-vue";

export default [
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
      "vue/html-self-closing": "off",
      "vue/max-attributes-per-line": "off",
      "vue/multi-word-component-names": "off",
      "vue/no-v-html": "off",
      "vue/no-v-model-argument": "off",
      "vue/singleline-html-element-content-newline": "off",
    },
  },
];
