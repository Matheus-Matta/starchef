import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const layoutStyles = readFileSync(resolve("src/styles.css"), "utf8");
const primeVueStyles = readFileSync(resolve("src/styles/primevue-tokens.css"), "utf8");
const formSection = readFileSync(
  resolve("src/components/form/AppFormSection.vue"),
  "utf8",
);
const cashRegister = readFileSync(resolve("src/views/CashRegisterView.vue"), "utf8");
const reportsView = readFileSync(resolve("src/views/ReportsView.vue"), "utf8");
const resourceListView = readFileSync(
  resolve("src/views/ResourceListViewPro.vue"),
  "utf8",
);
const cashReport = readFileSync(
  resolve("src/components/reports/CashMovementsReport.vue"),
  "utf8",
);
const cancellationsReport = readFileSync(
  resolve("src/components/reports/OrdersCancellationsPanel.vue"),
  "utf8",
);
const resourceForm = readFileSync(resolve("src/views/ResourceFormView.vue"), "utf8");
const administrativePages = [
  ["dashboard-view", "src/views/DashboardView.vue"],
  ["cash-statement", "src/views/CashSessionDetailView.vue"],
  ["cosmos-page", "src/views/CosmosConfigView.vue"],
  ["focus-page", "src/views/FocusNfeConfigView.vue"],
  ["rpage", "src/views/ResourceFormView.vue"],
  ["rfiscal", "src/views/RestaurantFiscalConfigView.vue"],
  ["stock-doc", "src/styles/stock-document.css"],
  ["picking", "src/views/StockExitPickingView.vue"],
].map(([className, path]) => [className, readFileSync(resolve(path), "utf8")]);

describe("ritmo vertical do layout", () => {
  it("reserva espaco no topo das paginas", () => {
    expect(layoutStyles).toMatch(
      /\.app-content\s*\{[^}]*padding:\s*var\(--page-inset-y\)\s+var\(--page-inset-x\)/s,
    );
  });

  it("separa o conteudo do cabecalho de modais e paineis", () => {
    expect(primeVueStyles).toMatch(
      /\.p-dialog \.p-dialog-content\s*\{[^}]*padding-top:\s*var\(--dialog-content-inset\)/s,
    );
    expect(primeVueStyles).toMatch(
      /\.p-panel \.p-panel-content\s*\{[^}]*padding-top:\s*var\(--section-content-gap\)/s,
    );
  });

  it("mantem respiro entre o cabecalho e o corpo das secoes", () => {
    expect(formSection).toMatch(
      /\.appsection__body\s*\{[^}]*padding-top:\s*var\(--space-1\)[^}]*gap:\s*var\(--section-content-gap\)/s,
    );
  });

  it("nao duplica o inset da casca nas paginas e nos modais", () => {
    expect(cashRegister).toMatch(
      /\.cash\s*\{[^}]*gap:\s*var\(--page-section-gap\)/s,
    );
    expect(cashRegister).not.toMatch(/\.cash\s*\{[^}]*padding:/s);
    expect(cashRegister).not.toMatch(/\.form\s*\{[^}]*padding-top:/s);
  });

  it("usa o mesmo ritmo em todas as secoes de relatorio", () => {
    for (const styles of [reportsView, cashReport, cancellationsReport]) {
      expect(styles).toMatch(/gap:\s*var\(--page-section-gap\)/);
      expect(styles).not.toMatch(/padding-top:\s*[24]px/);
    }
    expect(reportsView).not.toMatch(/\.reports-view\s*>\s*:not\([^}]+margin-top:/s);
  });

  it("mantem o mesmo intervalo nas paginas administrativas", () => {
    for (const [className, styles] of administrativePages) {
      expect(styles).toMatch(
        new RegExp(`\\.${className}\\s*\\{[^}]*gap:\\s*var\\(--page-section-gap\\)`, "s"),
      );
    }
  });

  it("usa o token de padding nos cards administrativos", () => {
    for (const [, styles] of administrativePages) {
      expect(styles).not.toMatch(/(?:focus-card|rfiscal__card|stock-card|picking__card)\s*\{[^}]*padding:\s*22px/s);
    }
  });

  it("amplia os modais da nota de entrada e do vinculo de produto", () => {
    expect(resourceListView).toMatch(
      /v-model:visible="inboundDetailVisible"[\s\S]*?:style="\{ width: '80vw' \}"/,
    );
    expect(resourceListView).toMatch(
      /v-model:visible="mapItemDialogVisible"[\s\S]*?:style="\{ width: '70vw' \}"/,
    );
  });

  it("mantem as acoes do formulario alinhadas a direita", () => {
    expect(resourceForm).toMatch(
      /\.rpage__footer\s*\{[^}]*justify-content:\s*flex-end/s,
    );
  });

  it("espaça os cartões empilhados dentro dos painéis de relatório", () => {
    // Global: o estilo "scoped" da ReportsView não chegava nos painéis, que são
    // componentes próprios — os cartões ficavam colados um no outro.
    expect(layoutStyles).toMatch(/\.responsive-one-col\s*\{[^}]*gap:/s);
    expect(layoutStyles).toMatch(/\.report-panel\s*\{[^}]*gap:\s*var\(--page-section-gap\)/s);
    expect(reportsView).not.toMatch(/^\.responsive-one-col\s*\{/m);
    for (const painel of ["CouponsReport", "ProductCostsReport"]) {
      const fonte = readFileSync(resolve(`src/components/reports/${painel}.vue`), "utf8");
      expect(fonte).toMatch(/class="[^"]* report-panel"/);
    }
  });

  it("Relatórios tem o atalho para o estoque", () => {
    const rotas = readFileSync(resolve("src/router/index.js"), "utf8");
    const menu = readFileSync(resolve("src/layout/Sidebar.vue"), "utf8");
    expect(rotas).toMatch(/name: "relatorio-estoque", component: StockPositionView/);
    expect(menu).toMatch(/id: "relatorio-estoque"/);
  });
});
