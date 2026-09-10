import { describe, expect, it } from "vitest";
import { AxiosHeaders } from "axios";

import { prepareMultipartHeaders } from "./multipart";

describe("prepareMultipartHeaders", () => {
  it("remove o JSON de um envio FormData", () => {
    const config = {
      data: new FormData(),
      headers: { "Content-Type": "application/json", Accept: "application/json" },
    };
    prepareMultipartHeaders(config);
    expect(config.headers).toEqual({ Accept: "application/json" });
  });

  it("mantem o Content-Type de corpos JSON", () => {
    const config = { data: { name: "Produto" }, headers: { "Content-Type": "application/json" } };
    prepareMultipartHeaders(config);
    expect(config.headers["Content-Type"]).toBe("application/json");
  });

  it("remove o JSON do objeto de headers usado pelo Axios", () => {
    const headers = new AxiosHeaders({ "Content-Type": "application/json" });
    prepareMultipartHeaders({ data: new FormData(), headers });
    expect(headers.has("Content-Type")).toBe(false);
  });
});
