import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/config/api_settings.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/order_dialogs.dart';

/// "Perguntar mesa" liga e desliga por aparelho.
///
/// Em casa que não trabalha com mesa (balcão, praça de alimentação), a
/// pergunta a cada comanda era um toque a mais em todo atendimento.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('vem ligada e a escolha sobrevive a fechar o app', () async {
    FlutterSecureStorage.setMockInitialValues({});
    final antes = await ApiSettings.load();
    expect(antes.askTable, isTrue);

    await antes.setAskTable(false);
    final depois = await ApiSettings.load();

    expect(depois.askTable, isFalse);
  });

  test('desligada, a comanda sem mesa não recebe a sugestão', () {
    final comandaSemMesa = {'command': 'c1', 'table': null};

    expect(shouldSuggestTable(comandaSemMesa), isTrue);
    expect(shouldSuggestTable(comandaSemMesa, perguntar: false), isFalse);
  });
}
