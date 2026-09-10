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
