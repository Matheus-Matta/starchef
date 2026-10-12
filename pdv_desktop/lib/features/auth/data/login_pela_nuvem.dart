import 'package:http/http.dart' as http;

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/cloud_fallback.dart';

/// O login que pega na NUVEM o IP do server local do restaurante.
///
/// O IP da loja era digitado em cada terminal, e mudar o servidor era refazer
/// isso caixa por caixa. Agora o login passa primeiro pela nuvem — fixa, o
/// "IP server nuvem" —, pergunta `/pdv/config/` onde fica a loja do
/// restaurante do usuário e entra nela com o MESMO usuário e senha, que só
/// existem na memória durante este login (nada é gravado além do IP).
///
/// Ninguém fica sem entrar por causa disso:
///
/// * nuvem fora (loja sem internet) → entra direto no IP guardado;
/// * loja fora, ou recusando → fica na nuvem, como o desvio de sempre;
/// * restaurante sem server local → fica na nuvem e esquece o IP antigo.
class LoginPelaNuvem {
  LoginPelaNuvem({
    required this.principal,
    required this.ipServerNuvem,
    required this.lerIpServerLocal,
    required this.salvarIpServerLocal,
    this.httpClient,
  });

  /// O cliente que o PDV inteiro usa: só é apontado no FIM, para quem
  /// respondeu.
  final ApiClient principal;
  final String ipServerNuvem;
  final String? Function() lerIpServerLocal;
  final Future<void> Function(String? ip) salvarIpServerLocal;

  /// Só nos testes; no app cada ida usa a sua conexão.
  final http.Client? httpClient;

  /// Faz o login e devolve a resposta do servidor que vai atender o PDV.
  Future<Map<String, dynamic>> entrar({
    required String usuario,
    required String senha,
  }) async {
    final Map<String, dynamic> naNuvem;
    String ipLocal;
    try {
      naNuvem = await _login(ipServerNuvem, usuario, senha);
      ipLocal = await _ipDaLoja(naNuvem);
    } on ApiException catch (erro) {
      if (!erro.isConnectivity) rethrow;
      // Nuvem fora: a loja guardada da última vez continua atendendo.
      final guardado = lerIpServerLocal() ?? '';
      if (guardado.isEmpty) rethrow;
      final naLoja = await _login(guardado, usuario, senha);
      await principal.updateBaseUrl(guardado);
      return naLoja;
    }

    await salvarIpServerLocal(ipLocal.isEmpty ? null : ipLocal);
    if (ipLocal.isNotEmpty) {
      try {
        final naLoja = await _login(ipLocal, usuario, senha);
        await principal.updateBaseUrl(ipLocal);
        return naLoja;
      } on ApiException {
        // Loja fora, ou o usuário ainda não chegou nela pela sincronização:
        // a sessão da nuvem atende enquanto isso.
      }
    }
    await principal.updateBaseUrl(ipServerNuvem);
    return naNuvem;
  }

  /// Um cliente para UM servidor, SEM o desvio automático para a nuvem.
  ///
  /// O cliente do PDV desvia sozinho para api.starchef.com.br quando a loja
  /// não responde: usado aqui, o "login na loja" fora do ar entrava na nuvem
  /// de produção e parecia ter entrado na loja. Quem decide o servidor é o
  /// login.
  Future<T> _com<T>(String base, Future<T> Function(ApiClient api) uso) async {
    final api = ApiClient(
      baseUrl: base,
      client: httpClient,
      cloudFallback: CloudFallback(enabled: false),
    );
    try {
      return await uso(api);
    } finally {
      // A conexão injetada (testes) é de quem a criou.
      if (httpClient == null) await api.dispose();
    }
  }

  Future<Map<String, dynamic>> _login(
    String base,
    String usuario,
    String senha,
  ) => _com(
    base,
    (api) async => Map<String, dynamic>.from(
      await api.post(
        '/auth/login/',
        // App nativo usa token Bearer, não os cookies do navegador.
        body: {
          'username': usuario.trim(),
          'password': senha,
          'no_cookie': true,
        },
      ),
    ),
  );

  /// O IP do server local na nuvem; sem a config, segue só a nuvem.
  Future<String> _ipDaLoja(Map<String, dynamic> sessao) async {
    try {
      final config = await _com(
        ipServerNuvem,
        (api) =>
            api.get('/pdv/config/', accessToken: '${sessao['access'] ?? ''}'),
      );
      return '${config['ip_server_local'] ?? ''}'.trim();
    } on ApiException catch (erro) {
      if (erro.isConnectivity) rethrow;
      return '';
    }
  }
}
