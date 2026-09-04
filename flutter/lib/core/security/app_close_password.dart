import 'cash_password.dart';

/// Autorização local para fechar o aplicativo antes de existir uma sessão.
///
/// O binário contém somente este verificador PBKDF2-SHA256 com salt. A senha
/// original não é persistida nem enviada para a API.
abstract final class AppClosePassword {
  static const _encoded =
      r'pbkdf2_sha256$210000$StarChefAppCloseV1$MiumpVD1MvS6yWS4KJND5zLId1u1OUB2sLK36GKq1s0=';

  static Future<bool> verify(String password) =>
      CashPassword.verify(password, _encoded);
}
