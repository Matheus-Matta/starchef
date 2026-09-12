import { ref } from "vue";
import { describe, expect, it, vi } from "vitest";

import { useResourceForm } from "./useResourceForm";

describe("useResourceForm multipart", () => {
  it("envia imagens como File e inclui exclusoes da galeria", async () => {
    const service = { create: vi.fn(async () => ({ id: "product-1" })) };
    const fields = [
      { name: "name", type: "text" },
      { name: "logo_p_upload", type: "file" },
      {
        name: "photo_uploads",
        type: "file",
        multiple: true,
        removeField: "photo_remove_ids",
      },
    ];
    const form = useResourceForm({
      service,
      formFields: fields,
      mode: ref("create"),
      recordId: ref(null),
      sharedAcrossRestaurants: true,
    });
    const logo = new File(["logo"], "logo.jpg", { type: "image/jpeg" });
    const photo = new File(["photo"], "photo.png", { type: "image/png" });
    form.formData.name = "Produto";
    form.formData.logo_p_upload = logo;
    form.formData.photo_uploads = [photo];
    form.formData.photo_remove_ids = ["9ee32a43-a323-44e7-9702-321c2dca54cd"];

    await form.save();

    const payload = service.create.mock.calls[0][0];
    expect(payload.get("logo_p_upload")).toBe(logo);
    expect(payload.getAll("photo_uploads")).toEqual([photo]);
    expect(payload.getAll("photo_remove_ids")).toEqual(form.formData.photo_remove_ids);
  });
});

describe("useResourceForm validacao no cliente", () => {
  it("barra antes de chamar a API e aponta o campo", async () => {
    const service = { create: vi.fn(async () => ({ id: "sla-1" })) };
    const fields = [
      { name: "name", type: "text", required: true },
      { name: "target_minutes", type: "number" },
      {
        name: "alert_minutes",
        type: "number",
        notGreaterThan: { field: "target_minutes", message: "alerta > alvo" },
      },
    ];
    const form = useResourceForm({
      service,
      formFields: fields,
      mode: ref("create"),
      recordId: ref(null),
      sharedAcrossRestaurants: true,
    });
    form.formData.name = "";
    form.formData.target_minutes = "10";
    form.formData.alert_minutes = "-5";

    expect(await form.save()).toBeNull();
    expect(service.create).not.toHaveBeenCalled();
    expect(form.fieldErrors.value).toEqual({
      name: "Este campo é obrigatório.",
      alert_minutes: "Não pode ser negativo.",
    });
    expect(form.saveError.value).toMatch(/Corrija os campos/);

    form.formData.name = "Cozinha";
    form.formData.alert_minutes = "12";
    expect(await form.save()).toBeNull();
    expect(form.fieldErrors.value).toEqual({ alert_minutes: "alerta > alvo" });

    form.formData.alert_minutes = "8";
    expect(await form.save()).toEqual({ id: "sla-1" });
    expect(service.create).toHaveBeenCalledTimes(1);
  });
});
