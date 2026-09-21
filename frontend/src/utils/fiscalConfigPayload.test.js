import { describe, expect, it } from "vitest";

import { buildFiscalConfigPayload } from "./fiscalConfigPayload";

describe("configuracao do certificado A1 da SEFAZ", () => {
  it("envia o arquivo e a senha como multipart", () => {
    const certificate = new File(["pfx"], "certificado.pfx", { type: "application/x-pkcs12" });

    const payload = buildFiscalConfigPayload({
      form: {
        provider: "focus_nfe",
        certificate_password: "segredo",
        dfe_ult_nsu: "123",
      },
      editableFields: ["provider", "dfe_ult_nsu"],
      secretFields: ["certificate_password"],
      certificateFile: certificate,
    });

    expect(payload).toBeInstanceOf(FormData);
    expect(payload.get("certificate_file")).toBe(certificate);
    expect(payload.get("certificate_password")).toBe("segredo");
    expect(payload.get("dfe_ult_nsu")).toBe("123");
  });
});
