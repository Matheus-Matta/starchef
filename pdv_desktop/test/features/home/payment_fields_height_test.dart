import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/coupon_select.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/payment_adjustments.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/payment_input_style.dart';

/// Cupom, forma de pagamento, CPF/CNPJ e desconto com a MESMA altura.
///
/// Com a fonte real (Segoe UI) o campo com ícone ficava mais alto que o sem
/// ícone: o tema dá altura mínima só à caixa do ícone. A fonte dos testes não
/// mostra essa diferença, então o que se confere aqui é o CONTRATO: todo campo
/// da tela tem a altura fixa `alturaDoCampo` — um campo montado sem
/// `campoDoPagamento` volta ao padrão do tema e reprova.
void main() {
  testWidgets('todo campo da tela de pagamento tem a altura comum', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body: Column(
            children: [
              CouponSelect(
                api: ApiClient(
                  baseUrl: 'http://loja.local/api/v1',
                  client: MockClient((_) async => http.Response('{}', 200)),
                ),
                accessToken: 't',
                aplicado: 'NATAL10',
                busy: false,
                erro: '',
                onAplicar: (_) {},
                onRemover: () {},
              ),
              PaymentAdjustments(
                cobrarTaxa: true,
                rotuloTaxa: '10%',
                documento: '52998224725',
                descontoCentavos: 250,
                maxDescontoCentavos: 1000,
                busy: false,
                bloqueado: false,
                erro: '',
                onTaxa: (_) {},
                onDocumento: (_) {},
                onDesconto: (_) {},
              ),
            ],
          ),
        ),
      ),
    );

    for (final chave in [
      'payment-coupon',
      'payment-document',
      'payment-discount',
    ]) {
      expect(
        tester.getSize(find.byKey(Key(chave))).height,
        alturaDoCampo,
        reason: chave,
      );
    }
  });
}
