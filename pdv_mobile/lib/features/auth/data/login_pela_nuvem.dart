import 'package:http/http.dart' as http;

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/cloud_fallback.dart';

/// O login que pega na NUVEM o IP do server local do restaurante.
///
/// O IP da loja era digitado em cada celular, e mudar o servidor era refazer
/// isso aparelho por aparelho. Agora o login passa primeiro pela nuvem — fixa,
/// o "IP server nuvem" —, pergunta `/pdv/config/` onde fica a loja do
/// restaurante do garçom e entra nela com o MESMO usuário e senha, que só
/// existem na memória durante este login (nada é gravado além do IP).
///
/// Ninguém fica sem entrar por causa disso:
///
/// * nuvem fora (loja sem internet) → entra direto no IP guardado;
/// * loja fora, ou recusando → fica na nuvem;
/// * restaurante sem server local → fica na nuvem.
///
/// Mesma regra do PDV desktop (`pdv_desktop/.../login_pela_nuvem.dart`).
class LoginPelaNuvem {
  LoginPelaNuvem({
    required this.ipServerNuvem,
    required this.lerIpServerLocal,
    required this.usarServidor,
    this.httpClient,
  });

  final String ipServerNuvem;

  /// Só nos testes; no app cada ida usa a sua conexão.
  final http.Client? httpClient;

  /// Um cliente para UM servidor, SEM o desvio automático para a nuvem.
  ///
  /// O cliente do app desvia sozinho para api.starchef.com.br quando a loja
  /// não responde: usado aqui, o "login na loja" fora do ar entrava na nuvem
  /// de produção e parecia ter entrado na loja. O login decide o servidor;
  /// o cliente do app só é apontado no fim (`usarServidor`).
  ApiClient cliente(String base) => ApiClient(
    baseUrlProvider: () => base,
    httpClient: httpClient,
    cloudFallback: CloudFallback(enabled: false),
  );
  final String? Function() lerIpServerLocal;

  /// Grava o servidor que o app passa a usar (`ApiSettings`).
  final Future<void> Function(String url) usarServidor;

  Future<Map<String, dynamic>> entrar({
    required String usuario,
    required String senha,
    Map<String, dynamic> extras = const {},
  }) async {
    Future<Map<String, dynamic>> login(String base) async =>
        Map<String, dynamic>.from(
          await cliente(base).post(
            '/auth/login/',
            body: {
              'username': usuario.trim(),
              'password': senha,
              'no_cookie': true,
              ...extras,
            },
          ),
        );

    final Map<String, dynamic> naNuvem;
    final String ipLocal;
    final String nuvemInformada;
    try {
      naNuvem = await login(ipServerNuvem);
      (ipLocal, nuvemInformada) = await _config(naNuvem);
    } on ApiException catch (erro) {
      if (!erro.isConnectivity) rethrow;
      // Nuvem fora: a loja guardada da última vez continua atendendo.
      final guardado = lerIpServerLocal() ?? '';
      if (guardado.isEmpty) rethrow;
      await usarServidor(guardado);
      return login(guardado);
    }

    if (ipLocal.isNotEmpty) {
      try {
        final naLoja = await login(ipLocal);
        await usarServidor(ipLocal);
        return naLoja;
      } on ApiException {
        // Loja fora, ou o garçom ainda não chegou nela pela sincronização:
        // a sessão da nuvem atende, e o próximo login tenta a loja de novo.
      }
    }
    // Sem loja: direto para a nuvem — a que ela mesma informou (o `API_URL`
    // do .env dela), ou a fixa deste build.
    await usarServidor(nuvemInformada.isEmpty ? ipServerNuvem : nuvemInformada);
    return naNuvem;
  }

  /// (IP server local, IP server nuvem) que a nuvem informa.
  Future<(String, String)> _config(Map<String, dynamic> sessao) async {
    try {
      final config = await cliente(
        ipServerNuvem,
      ).get('/pdv/config/', accessToken: '${sessao['access'] ?? ''}');
      return (
        '${config['ip_server_local'] ?? ''}'.trim(),
        '${config['ip_server_nuvem'] ?? ''}'.trim(),
      );
    } on ApiException catch (erro) {
      if (erro.isConnectivity) rethrow;
      return ('', '');
    }
  }
}
