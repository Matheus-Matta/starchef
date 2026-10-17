// Ver `home_page.dart` para o motivo deste ignore na biblioteca.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O CPF/CNPJ DIGITADO e não aplicado entra na nota antes do recebimento.
///
/// O operador digitava o CPF e ia direto em "Adicionar pagamento": sem o ✓ o
/// documento ficava para trás e a nota saía sem nome. Inválido, ou recusado
/// pelo servidor, o recebimento não é lançado: cobrar com um CPF que o cliente
/// pediu e não entrou é pior do que parar e mostrar o erro. A regra de quando
/// aplicar está em `documentoPendente`.
mixin _PaymentDocumentSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  List<Map<String, dynamic>> get registeredPayments;
  TextEditingController get paymentDocument;
  String get adjustError;
  set adjustError(String value);
  Future<void> _ajustarDocumento(String digitos);

  /// O CPF ou CNPJ que o pedido já leva (só dígitos).
  String get _documentoDoPedido {
    final pedido = activeOrder ?? const {};
    final cpf = cpfDigits(pedido['fiscal_customer_cpf']);
    return cpf.isNotEmpty ? cpf : cnpjDigits(pedido['fiscal_customer_cnpj']);
  }

  /// `false` = o pagamento não pode seguir (o erro já está na tela).
  Future<bool> _aplicarDocumentoPendente() async {
    final decisao = documentoPendente(
      texto: paymentDocument.text,
      aplicado: _documentoDoPedido,
      travado: registeredPayments.isNotEmpty,
    );
    switch (decisao) {
      case SemDocumentoPendente():
        return true;
      case DocumentoPendenteInvalido():
        setState(
          () => adjustError =
              'CPF ou CNPJ inválido: confira os dígitos (CPF tem 11, CNPJ '
              '14). O pagamento não foi adicionado.',
        );
        return false;
      case AplicarDocumento(:final digitos):
        await _ajustarDocumento(digitos);
        return mounted && adjustError.isEmpty && _documentoDoPedido == digitos;
    }
  }
}
