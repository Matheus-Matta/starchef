import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * A identidade da instalação é o que substitui `navigator.userAgent` como
 * "de onde partiu esta operação". Dois requisitos importam: ela precisa ser
 * estável entre recargas (senão o operador perde a própria sessão a cada F5)
 * e precisa sobreviver a um `localStorage` indisponível (janela anônima
 * restrita) sem derrubar a tela.
 */
async function loadModule() {
  vi.resetModules();
  return import("./terminalIdentity");
}

describe("identidade do terminal", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("gera um UUID e o reutiliza nas próximas leituras", async () => {
    const { terminalInstallationId } = await loadModule();

    const first = terminalInstallationId();
    const second = terminalInstallationId();

    expect(first).toMatch(/^[0-9a-f-]{36}$/i);
    expect(second).toBe(first);
  });

  it("mantém a mesma identidade depois de recarregar a página", async () => {
    const first = (await loadModule()).terminalInstallationId();

    // Novo carregamento do módulo = página recarregada, mesmo perfil.
    const afterReload = (await loadModule()).terminalInstallationId();

    expect(afterReload).toBe(first);
  });

  it("não usa o user agent como identidade", async () => {
    const { terminalPayload } = await loadModule();

    const payload = terminalPayload();

    expect(payload.terminal_installation_id).not.toContain("Mozilla");
    expect(payload.terminal_installation_id).toBe(payload.device_identifier);
    expect(payload.terminal_type).toBe("web");
  });

  it("continua funcionando quando o armazenamento está bloqueado", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("acesso negado ao armazenamento");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("acesso negado ao armazenamento");
    });

    const { terminalInstallationId, terminalName } = await loadModule();
    const id = terminalInstallationId();

    expect(id).toMatch(/^[0-9a-f-]{36}$/i);
    // Sem persistência a identidade vale só nesta aba — mas ela existe, e o
    // caixa não fica impedido de abrir por causa disso.
    expect(terminalName()).toContain(id.slice(0, 6));

    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("usa o nome definido para o terminal quando existe", async () => {
    const { setTerminalName, terminalPayload } = await loadModule();

    setTerminalName("Balcão 01");

    expect(terminalPayload().terminal_name).toBe("Balcão 01");
  });

  it("executa a tarefa mesmo sem Web Locks no navegador", async () => {
    const { withCashLock } = await loadModule();
    const original = navigator.locks;
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true });

    const result = await withCashLock("caixa-1", async () => "executou");

    expect(result).toBe("executou");
    Object.defineProperty(navigator, "locks", { value: original, configurable: true });
  });

  it("serializa duas chamadas concorrentes na mesma chave", async () => {
    const { withCashLock } = await loadModule();
    // jsdom não implementa Web Locks; o dublê reproduz a fila por chave.
    const held = new Map();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: (name, task) => {
          const previous = held.get(name) || Promise.resolve();
          const next = previous.then(task);
          held.set(
            name,
            next.catch(() => {}),
          );
          return next;
        },
      },
    });

    const order = [];
    const slow = withCashLock("caixa-1", async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      order.push("primeira");
    });
    const fast = withCashLock("caixa-1", async () => {
      order.push("segunda");
    });
    await Promise.all([slow, fast]);

    // A segunda aba só entra depois que a primeira soltou a trava — é isso que
    // impede dois POSTs de abertura saírem do mesmo navegador.
    expect(order).toEqual(["primeira", "segunda"]);
  });
});
