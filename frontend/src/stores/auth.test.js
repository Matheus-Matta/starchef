/**
 * @vitest-environment jsdom
 * @vitest-environment-options { "url": "https://app.starchef.com.br/" }
 */
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  loginRequest: vi.fn(),
  refreshAccessToken: vi.fn(),
  api: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../services/api", () => apiMock);

import { SESSION_COOKIE_REJECTED, useAuthStore } from "./auth";

const USER = { id: "1", username: "admin", enabled_modules: ["base"], permissions: ["*"] };

function unauthorized() {
  const error = new Error("Request failed with status code 401");
  error.response = { status: 401 };
  return error;
}

// Cenário do deploy com API em outro host (app.dominio -> api.dominio): o
// backend grava `sc_session` no host da API, invisível para este origin.
describe("auth store: login com API em outro host", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    document.cookie = "sc_session=; Max-Age=0; path=/";
    apiMock.loginRequest.mockResolvedValue({ data: { access: "a", refresh: "r", user: USER } });
  });

  it("grava a flag de sessão neste origin e confirma a sessão pelo cookie", async () => {
    apiMock.api.get.mockResolvedValue({ data: USER });
    const auth = useAuthStore();

    const user = await auth.login({ username: "admin", password: "x" });

    expect(user).toEqual(USER);
    expect(auth.isAuthenticated).toBe(true);
    expect(auth.initialized).toBe(true);
    expect(document.cookie).toContain("sc_session=1");
    expect(apiMock.api.get).toHaveBeenCalledWith("/auth/me/");
    // Com a flag local, um F5 não derruba a sessão só por não enxergar o
    // cookie do backend.
    expect(await auth.validateSession()).toBe(true);
  });

  it("login aceito mas cookie recusado vira erro legível, sem entrar no painel", async () => {
    apiMock.api.get.mockRejectedValue(unauthorized());
    const auth = useAuthStore();

    await expect(auth.login({ username: "admin", password: "x" })).rejects.toMatchObject({
      code: SESSION_COOKIE_REJECTED,
    });

    expect(auth.isAuthenticated).toBe(false);
    expect(auth.user).toBeNull();
    expect(document.cookie).not.toContain("sc_session=1");
  });

  it("senha errada continua chegando como 401 na tela", async () => {
    apiMock.loginRequest.mockRejectedValue(unauthorized());
    const auth = useAuthStore();

    await expect(auth.login({ username: "admin", password: "x" })).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(apiMock.api.get).not.toHaveBeenCalled();
    expect(document.cookie).not.toContain("sc_session=1");
  });
});
