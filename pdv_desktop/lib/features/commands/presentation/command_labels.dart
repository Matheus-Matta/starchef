/// As regras das etiquetas de comanda, sem tela: o que imprimir e o que avisar.
library;

/// Máximo por lote: uma faixa digitada errado ("1 a 100000") não pode
/// travar a impressora a tarde inteira.
const maximoDeEtiquetasPorLote = 1000;

/// O trabalho de impressão de UMA etiqueta, no formato que o agente do
/// terminal já imprime (o mesmo dos trabalhos que vêm do servidor).
///
/// O valor do QR e das barras é o mesmo do recibo da comanda: o código, ou o
/// número quando ela não tem código — é o que o leitor do PDV reconhece.
Map<String, dynamic> trabalhoDeEtiqueta(Map<String, dynamic> comanda) {
  final numero = '${comanda['number'] ?? ''}'.trim();
  final codigo = '${comanda['code'] ?? ''}'.trim();
  final valor = codigo.isEmpty ? numero : codigo;
  return {
    'job_type': 'command_label',
    'payload': {
      'payload_version': 2,
      'text_content': numero,
      'barcode': {'symbology': 'CODE128', 'value': valor},
      'qr_data': valor,
    },
  };
}

/// Números da faixa que não têm comanda cadastrada (ativa).
List<int> numerosSemCadastro(
  int de,
  int ate,
  List<Map<String, dynamic>> comandas,
) {
  final cadastrados = {
    for (final c in comandas) int.tryParse('${c['number']}'),
  };
  return [
    for (var n = de; n <= ate; n++)
      if (!cadastrados.contains(n)) n,
  ];
}

/// A faixa digitada, validada — ou a mensagem do que está errado.
({int de, int ate})? faixaValida(
  String de,
  String ate,
  void Function(String) erro,
) {
  final inicio = int.tryParse(de.trim());
  final fim = int.tryParse(ate.trim());
  if (inicio == null || fim == null || inicio < 1 || fim < 1) {
    erro('Informe números inteiros a partir de 1.');
    return null;
  }
  if (inicio > fim) {
    erro('O número inicial é maior que o final.');
    return null;
  }
  if (fim - inicio + 1 > maximoDeEtiquetasPorLote) {
    erro('No máximo $maximoDeEtiquetasPorLote etiquetas por vez.');
    return null;
  }
  return (de: inicio, ate: fim);
}

/// "13, 14, 15 e mais 9" — para o aviso não virar um parágrafo.
String listaCurta(List<int> numeros, {int mostrar = 8}) {
  if (numeros.length <= mostrar) return numeros.join(', ');
  return '${numeros.take(mostrar).join(', ')} e mais ${numeros.length - mostrar}';
}
