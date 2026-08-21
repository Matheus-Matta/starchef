import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/security/cash_password.dart';

void main() {
  const djangoHash =
      r'pbkdf2_sha256$870000$StarChefOfflineTest$'
      'bZ3RYZKo5XBkl+0A6yIQspiUyHBJBAKC60IGdcdgcq0=';

  test('valida senha contra hash PBKDF2 gerado pelo Django 5.1', () async {
    expect(await CashPassword.verify('1234', djangoHash), isTrue);
    expect(await CashPassword.verify('senha-incorreta', djangoHash), isFalse);
  });

  test('rejeita formatos e algoritmos não suportados', () async {
    expect(await CashPassword.verify('1234', 'invalido'), isFalse);
    expect(
      await CashPassword.verify(
        '1234',
        r'argon2$argon2id$v=19$m=102400,t=2,p=8$hash',
      ),
      isFalse,
    );
  });

  test('gera verificador local sem armazenar a senha em texto puro', () async {
    final encoded = await CashPassword.encode(
      'segredo-offline',
      iterations: 1000,
    );

    expect(encoded, startsWith(r'pbkdf2_sha256$1000$'));
    expect(encoded, isNot(contains('segredo-offline')));
    expect(await CashPassword.verify('segredo-offline', encoded), isTrue);
    expect(await CashPassword.verify('outra-senha', encoded), isFalse);
  });
}
