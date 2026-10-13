import 'package:http/http.dart' as http;

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/cloud_fallback.dart';

/// O login do app do garçom: são DOIS logins.
///
/// 1. Na NUVEM (fixa, o "IP server nuvem"), só para ler `/pdv/config/`: o IP
///    server local do restaurante e a nuvem informada (o `API_URL` dela). O
///    token desse login é descartado ali mesmo, e usuário e senha só existem
///    na memória durante o login.
/// 2. No IP SERVER LOCAL, o que vale: é a sessão dele que o app usa, e é o
///    erro dele que o garçom vê. Sem IP local, o padrão é a própria nuvem.
///
/// A config é um extra, nunca a porta de entrada: nuvem fora, recusando o
/// garçom ou com erro → fica o servidor guardado. Loja fora do ar → nuvem.
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

    final config = await _config(login);
    final ipLocal = config?.ipLocal ?? (lerIpServerLocal() ?? '');
    final nuvem = (config?.nuvem ?? '').isEmpty ? ipServerNuvem : config!.nuvem;
    // A sessão da nuvem vai JUNTO com a da loja: é com ela que o desvio fala
    // com a nuvem (`api_client_nuvem.dart`).
    final daNuvem = {
      'cloud_access': config?.sessao['access'] ?? '',
      'cloud_refresh': config?.sessao['refresh'] ?? '',
    };

    if (ipLocal.isNotEmpty) {
      try {
        final naLoja = await login(ipLocal);
        await usarServidor(ipLocal);
        return {...naLoja, ...daNuvem};
      } on ApiException catch (erro) {
        // Senha recusada é a resposta do login: aparece. Só a loja FORA do
        // ar cai para a nuvem.
        if (!erro.isConnectivity) rethrow;
      }
    }
    final naNuvem = await login(nuvem);
    await usarServidor(nuvem);
    // Logado NA nuvem: a sessão principal já é a dela.
    return {
      ...naNuvem,
      'cloud_access': naNuvem['access'] ?? '',
      'cloud_refresh': naNuvem['refresh'] ?? '',
    };
  }

  /// O primeiro login: (IP server local, nuvem informada) da `/pdv/config/`,
  /// ou null quando a nuvem não deu a config — e aí fica o padrão guardado.
  Future<({String ipLocal, String nuvem, Map<String, dynamic> sessao})?>
  _config(Future<Map<String, dynamic>> Function(String base) login) async {
    try {
      final sessao = await login(ipServerNuvem);
      final config = await cliente(
        ipServerNuvem,
      ).get('/pdv/config/', accessToken: '${sessao['access'] ?? ''}');
      return (
        ipLocal: '${config['ip_server_local'] ?? ''}'.trim(),
        nuvem: '${config['ip_server_nuvem'] ?? ''}'.trim(),
        sessao: sessao,
      );
    } on Exception {
      return null;
    }
  }
}
