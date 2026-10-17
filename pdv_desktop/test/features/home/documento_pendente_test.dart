import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/documento_pendente.dart';

/// O operador digitava o CPF e ia direto em "Adicionar pagamento": sem o ✓ o
/// documento ficava para trás e a nota saía sem nome.
void main() {
  test('CPF digitado e não aplicado é aplicado antes do pagamento', () {
    final decisao = documentoPendente(
      texto: '529.982.247-25',
      aplicado: '',
      travado: false,
    );
    expect(decisao, isA<AplicarDocumento>());
    expect((decisao as AplicarDocumento).digitos, '52998224725');
  });

  test('CNPJ válido também é aplicado', () {
    final decisao = documentoPendente(
      texto: '11.222.333/0001-81',
      aplicado: '',
      travado: false,
    );
    expect((decisao as AplicarDocumento).digitos, '11222333000181');
  });

  test('documento inválido trava o pagamento', () {
    expect(
      documentoPendente(texto: '529.982.247-26', aplicado: '', travado: false),
      isA<DocumentoPendenteInvalido>(),
    );
    expect(
      documentoPendente(texto: '1234', aplicado: '', travado: false),
      isA<DocumentoPendenteInvalido>(),
    );
  });

  test('o mesmo documento que a nota já leva não chama o servidor de novo', () {
    expect(
      documentoPendente(
        texto: '529.982.247-25',
        aplicado: '52998224725',
        travado: false,
      ),
      isA<SemDocumentoPendente>(),
    );
  });

  test('campo vazio não tira o documento aplicado: remover é o X', () {
    expect(
      documentoPendente(texto: '', aplicado: '52998224725', travado: false),
      isA<SemDocumentoPendente>(),
    );
  });

  test('com recebimento lançado o campo está travado e nada muda', () {
    expect(
      documentoPendente(texto: '529.982.247-26', aplicado: '', travado: true),
      isA<SemDocumentoPendente>(),
    );
  });
}
