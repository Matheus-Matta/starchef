import { api } from "./api";

function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const dataExchangeService = {
  async exportCsv({ filename, columns, rows }) {
    const response = await api.post(
      "/data-exchange/export/",
      { filename, columns, rows },
      { responseType: "blob" },
    );
    download(response.data, filename);
  },

  async parseCsv(file) {
    const body = new FormData();
    body.append("file", file);
    const { data } = await api.post("/data-exchange/parse/", body, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },
};
