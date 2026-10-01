bool deveExibirRecusaFiscal(
  Map<String, dynamic> resposta, {
  required bool silenciarSemConfiguracao,
}) {
  // Sem `id`, o backend nem criou nota: e o restaurante que nao usa emissao.
  // Com `id`, houve uma tentativa real e o operador precisa corrigir a causa.
  return !silenciarSemConfiguracao || resposta['id'] != null;
}
