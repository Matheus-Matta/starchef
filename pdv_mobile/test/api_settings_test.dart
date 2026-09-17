import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/config/api_settings.dart';

void main() {
  test('completa o namespace padrão quando a URL não tem caminho', () {
    expect(
      ApiSettings.normalize('https://api.starchef.com.br/'),
      'https://api.starchef.com.br/api/v1',
    );
  });

  test('preserva uma URL de API completa', () {
    expect(
      ApiSettings.normalize('http://192.168.1.10:8000/api/v1/'),
      'http://192.168.1.10:8000/api/v1',
    );
  });

  test('recusa valor sem esquema ou host', () {
    expect(ApiSettings.isValid('api.starchef.com.br'), isFalse);
  });
}
