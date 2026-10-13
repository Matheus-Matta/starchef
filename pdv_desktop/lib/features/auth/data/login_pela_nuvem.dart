import 'package:http/http.dart' as http;

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/cloud_fallback.dart';

/// O login do PDV: são DOIS logins.
///
/// 1. Na NUVEM (fixa, o "IP server nuvem"), só para ler `/pdv/config/`: o IP
///    server local do restaurante e a nuvem informada (o `API_URL` dela). O
///    token desse login é descartado ali mesmo, e usuário e senha só existem
///    na memória durante o login — nada é gravado além da config.
/// 2. No IP SERVER LOCAL, o que vale: é a sessão dele que o PDV usa, e é o
///    erro dele que o caixa vê. Sem IP local, o padrão é a própria nuvem.
///
/// A config é um extra, nunca a porta de entrada: nuvem fora, recusando o
/// usuário (uma nuvem que não o conhece) ou com erro → fica o que já estava
/// guardado. Antes era o contrário, e um usuário que a nuvem não conhecia não
/// entrava nem com a loja respondendo. Loja fora do ar → entra na nuvem.
class LoginPelaNuvem {
  LoginPelaNuvem({
    this.somenteNuvem = _nunca,
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
  /// O terminal está em "só nuvem" (`LocalPreferences.somenteNuvem`)?
  final bool Function() somenteNuvem;
  static bool _nunca() => false;

  Future<Map<String, dynamic>> entrar({
    required String usuario,
    required String senha,
  }) async {
    final config = await _config(usuario, senha);
    if (config != null) {
      await salvarIpServerLocal(config.ipLocal.isEmpty ? null : config.ipLocal);
    }
    // "Só nuvem" no terminal: nem o IP da config nem o guardado valem.
    final ipLocal = somenteNuvem()
        ? ''
        : config?.ipLocal ?? (lerIpServerLocal() ?? '');
    final nuvem = (config?.nuvem ?? '').isEmpty ? ipServerNuvem : config!.nuvem;
    // A sessão da nuvem vai JUNTO com a da loja: é com ela que o desvio fala
    // com a nuvem (`api_client_nuvem.dart`).
    final daNuvem = {
      'cloud_access': config?.sessao['access'] ?? '',
      'cloud_refresh': config?.sessao['refresh'] ?? '',
    };

    if (ipLocal.isNotEmpty) {
      try {
        final naLoja = await _login(ipLocal, usuario, senha);
        await principal.updateBaseUrl(ipLocal);
        return {...naLoja, ...daNuvem};
      } on ApiException catch (erro) {
        // Senha recusada é a resposta do login: aparece. Só a loja FORA do
        // ar cai para a nuvem.
        if (!erro.isConnectivity) rethrow;
      }
    }
    final naNuvem = await _login(nuvem, usuario, senha);
    await principal.updateBaseUrl(nuvem);
    // Logado NA nuvem: a sessão principal já é a dela.
    return {
      ...naNuvem,
      'cloud_access': naNuvem['access'] ?? '',
      'cloud_refresh': naNuvem['refresh'] ?? '',
    };
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

  /// O primeiro login: (IP server local, nuvem informada) da `/pdv/config/`,
  /// ou null quando a nuvem não deu a config — e aí fica o padrão guardado.
  Future<({String ipLocal, String nuvem, Map<String, dynamic> sessao})?>
  _config(String usuario, String senha) async {
    try {
      final sessao = await _login(ipServerNuvem, usuario, senha);
      final config = await _com(
        ipServerNuvem,
        (api) =>
            api.get('/pdv/config/', accessToken: '${sessao['access'] ?? ''}'),
      );
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
