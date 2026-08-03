import "primeicons/primeicons.css";
import "primevue/resources/themes/aura-light-teal/theme.css";
import "primevue/resources/primevue.min.css";
import "./styles.css";

import { createApp } from "vue";
import { createPinia } from "pinia";
import PrimeVue from "primevue/config";
import ConfirmationService from "primevue/confirmationservice";
import ToastService from "primevue/toastservice";
import Tooltip from "primevue/tooltip";

import App from "./App.vue";
import { router } from "./router";
import { initSentry } from "./sentry";

const app = createApp(App);

app.config.errorHandler = (error, instance, info) => {
  window.dispatchEvent(
    new CustomEvent("app:unhandled-error", {
      detail: { error, component: instance?.$options?.name, info },
    }),
  );

  if (import.meta.env.DEV) {
    console.error(error, info);
  }
};

// Depois do errorHandler acima: o SDK do Sentry encadeia o handler existente
// (chama o nosso depois de capturar), então a ordem de inicialização importa.
initSentry(app, router);

app
  .use(PrimeVue, { ripple: true })
  .use(ConfirmationService)
  .use(ToastService)
  .use(createPinia())
  .use(router)
  .directive("tooltip", Tooltip)
  .mount("#app");
