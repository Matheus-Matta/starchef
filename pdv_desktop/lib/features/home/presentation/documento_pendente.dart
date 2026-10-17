import '../../../core/formatters/documento_fiscal.dart';

/// O que fazer com o CPF/CNPJ do campo ao adicionar um pagamento.
sealed class DocumentoPendente {
  const DocumentoPendente();
}

/// Nada a aplicar: o campo está vazio, igual ao da nota, ou travado.
class SemDocumentoPendente extends DocumentoPendente {
  const SemDocumentoPendente();
}

/// O texto não é CPF nem CNPJ válido: o pagamento não pode seguir.
class DocumentoPendenteInvalido extends DocumentoPendente {
  const DocumentoPendenteInvalido();
}

/// Documento válido, digitado e ainda não aplicado: vai para a nota antes.
class AplicarDocumento extends DocumentoPendente {
  const AplicarDocumento(this.digitos);
  final String digitos;
}

/// Decide pelo texto do campo e pelo documento que o pedido já leva.
///
/// Campo vazio NÃO remove o documento aplicado: remover é o X do campo, e
/// apagar o texto sem querer não pode tirar o CPF de uma nota. Com
/// recebimento lançado ([travado]) o campo está desabilitado e nada muda.
DocumentoPendente documentoPendente({
  required String texto,
  required String aplicado,
  required bool travado,
}) {
  if (travado) return const SemDocumentoPendente();
  final digitos = documentoDigitos(texto);
  if (digitos.isEmpty || digitos == aplicado) {
    return const SemDocumentoPendente();
  }
  if (!documentoValido(digitos)) return const DocumentoPendenteInvalido();
  return AplicarDocumento(digitos);
}
