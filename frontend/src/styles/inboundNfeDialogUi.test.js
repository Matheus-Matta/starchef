import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const dialogStyles = readFileSync(
  resolve("src/styles/inbound-nfe-dialogs.css"),
  "utf8",
);
const resourceList = readFileSync(
  resolve("src/views/ResourceListViewPro.vue"),
  "utf8",
);

describe("UX dos modais da NF-e de entrada", () => {
  it("mantem espaco no topo e padding coerente no conteudo", () => {
    expect(dialogStyles).toMatch(
      /\.rpro__inbound-dialog \.p-dialog-content,[\s\S]*?padding:\s*var\(--dialog-content-inset\)\s+var\(--space-6\)/,
    );
  });

  it("usa os tokens dos controles e foco visivel", () => {
    expect(dialogStyles).toMatch(/min-height:\s*var\(--control-h-lg\)/);
    expect(dialogStyles).toMatch(/focus-visible[\s\S]*?outline:\s*2px solid var\(--ring\)/);
  });

  it("limita nomes extensos sem esconder o texto completo", () => {
    expect(dialogStyles).toMatch(/\.rpro__inbound-link-badge[\s\S]*?text-overflow:\s*ellipsis/);
    expect(dialogStyles).toMatch(/\.inbound-map__item-name[\s\S]*?text-overflow:\s*ellipsis/);
    expect(resourceList).toMatch(/:title="prod\.name"/);
    expect(resourceList).toMatch(/class="rpro__inbound-link-badge"/);
  });

  it("deixa a lista de vinculo utilizavel pelo teclado", () => {
    expect(resourceList).toMatch(/role="listbox"/);
    expect(resourceList).toMatch(/role="option"/);
    expect(resourceList).toMatch(/@keydown\.enter="selectTargetProduct\(prod\)"/);
  });
});
