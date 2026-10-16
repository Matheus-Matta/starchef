import 'api_exception.dart';
import 'sondas_da_loja.dart';
import 'veredito_da_loja.dart';

export 'server_origin.dart';

/// A nuvem como SEGUNDO SERVIDOR, quando o backend da loja não responde.
///
/// A loja roda o próprio backend, e é ele quem atende. Se a máquina desliga, o
/// cabo sai ou o serviço morre, o terminal perde a tela inteira — cardápio,
/// comandas, mesas, pedidos — e o salão para de atender. Esta classe é a
/// resposta a isso: a requisição que não chegou ao servidor da loja é
/// repetida contra a nuvem.
///
/// ## Quando cai
///
/// Só quando a requisição **não chegou ao backend**:
///
/// * conexão recusada, DNS, TLS — ninguém recebeu nada;
/// * 502, 503 e 504 — o proxy responde, o backend atrás dele não.
///
/// Um **500 puro não cai**, e essa distinção importa: 500 é defeito de UM
/// endpoint, não "o backend caiu". Cair nele mandaria o terminal inteiro para
/// a nuvem por causa de uma rota com bug — e lá ele encontraria o mesmo bug,
/// porque é o mesmo código.
///
/// ## Loja instável: cai rápido
///
/// O garçom anda pelo salão e o Wi-Fi oscila. Esperar três sondas (até ~20 s)
/// antes de desviar deixava o app parado no meio do atendimento; agora UMA
/// sonda sem resposta basta, e **tempo esgotado na loja já é queda** — loja que
/// não responde em 8 s (`ApiClient.timeoutLoja`) não serve para lançar. Caiu,
/// fica 5 minutos na nuvem ([VereditoDaLoja]).
///
/// ## Escrita com tempo esgotado: só com identidade
///
/// A `Idempotency-Key` vive no banco de CADA backend: repetir na nuvem uma
/// escrita que a loja JÁ GRAVOU executaria de novo. Conexão recusada é segura
/// (ninguém recebeu nada). Tempo esgotado só desvia quando o corpo leva `id`
/// (UUID do aparelho — anotação de comanda, recebimento): os dois servidores
/// gravam a MESMA linha e a sincronização junta. Sem `id`, espera na fila.
///
/// ## Os dois emissores
///
/// Duas pontas escrevendo são duas fontes de numeração, e cada uma tem um
/// remédio diferente:
///
/// * **número do pedido** — faixas separadas por nó, no backend
///   (`orders/sequence_ranges.py`). A loja numera de 1; a nuvem, de um milhão.
///   Nunca se encontram, e o número alto denuncia sozinho que aquele pedido
///   nasceu durante uma queda.
/// * **fiscal e caixa** — não desviam. Ver [caminhosQueNuncaDesviam].
class CloudFallback {
  CloudFallback({
    String? baseUrl,
    this.enabled = true,
    VereditoDaLoja? veredito,
    this.sondasAntesDeDesviar = 1,
    this.intervaloEntreSondas = const Duration(seconds: 2),
  }) : baseUrl = baseUrl ?? enderecoDaNuvem,
       veredito = veredito ?? VereditoDaLoja();

  /// O endereço da nuvem, fixo em COMPILAÇÃO.
  ///
  /// Não vem de configuração de propósito: é o último recurso quando a loja
  /// está fora, e um endereço que o técnico pode digitar errado no cadastro
  /// não serve como último recurso. HTTPS obrigatório — é a internet aberta,
  /// não a rede do salão.
  static const enderecoDaNuvem = 'https://api.starchef.com.br/api/v1';

  final String baseUrl;

  /// Desligável para o terminal que não deve sair da loja nunca (rede
  /// fechada, exigência do cliente). O padrão é ligado.
  final bool enabled;

  /// O que NUNCA desvia, nem com a loja comprovadamente fora — a resposta
  /// certa é ESPERAR a loja voltar.
  ///
  /// **Fiscal:** o número da nota é sequencial dentro da SÉRIE; dois nós na
  /// mesma série emitem duas notas com o mesmo número. **Caixa:** sessão
  /// aberta na nuvem com a loja tendo a dela dá dois saldos para o mesmo
  /// turno. A comparação é por PREFIXO: rota nova debaixo de `/invoices/`
  /// nasce protegida.
  static const caminhosQueNuncaDesviam = [
    '/invoices/',
    '/cash-register/',
    '/cash-registers/',
  ];

  /// Os códigos em que o proxy respondeu mas o backend atrás dele não.
  ///
  /// 500 fica FORA: ele significa que o backend recebeu, executou e quebrou —
  /// o servidor está de pé, e o problema é da rota.
  static const statusSemBackend = {502, 503, 504};

  /// Quanto tempo o terminal fica na nuvem depois de a loja cair.
  final VereditoDaLoja veredito;

  /// A loja está confirmadamente fora AGORA?
  bool get localForaDoAr => veredito.localForaDoAr;

  /// A loja respondeu. Esquece o veredito e volta a atender por ela.
  void localRespondeu() => veredito.localRespondeu();

  /// Com a loja confirmadamente fora, esta requisição vai DIRETO à nuvem?
  ///
  /// Tudo vai, inclusive fechar comanda: dentro da janela o terminal está na
  /// nuvem, e o restaurante inteiro de um lado só é o que evita a venda
  /// espalhada pelos dois servidores. Só fiscal e caixa ficam na loja.
  bool irDiretoParaANuvem(String path) =>
      enabled && localForaDoAr && !nuncaDesvia(path);

  /// Vencida a janela de 5 minutos, o ping decide se o terminal volta.
  ///
  /// Respondeu: volta para a loja. Não respondeu: mais 5 minutos na nuvem.
  /// Várias requisições ao mesmo tempo esperam o MESMO ping.
  Future<void> conferirSeVenceu(Future<bool> Function() sonda) {
    if (!veredito.precisaConferir) return Future.value();
    return _conferindo ??= () async {
      try {
        if (await sonda()) {
          veredito.voltou();
        } else {
          veredito.marcarForaDoAr();
        }
      } finally {
        _conferindo = null;
      }
    }();
  }

  Future<void>? _conferindo;

  /// Esta falha justifica tentar a nuvem? Escrita que pode ter sido executada
  /// (`reachedServer`) só cai com [comIdentidade] — ver o topo da classe.
  bool deveTentar(
    String method,
    String path,
    ApiException erro, {
    bool comIdentidade = false,
  }) {
    if (!enabled) return false;
    if (!_naoChegouAoBackend(erro)) return false;
    // Fiscal e caixa não desviam NEM para leitura: ler o próximo número da
    // nota na nuvem já daria ao terminal um número que a loja vai reemitir.
    if (nuncaDesvia(path)) return false;
    if (_ehLeitura(method) || comIdentidade) return true;
    return !erro.reachedServer;
  }

  /// Esta rota está na lista do que nunca sai da loja?
  bool nuncaDesvia(String path) => caminhosQueNuncaDesviam.any(path.startsWith);

  /// A loja está fora? [lenta] (tempo esgotado) já é queda, sem sonda; senão
  /// [sondasAntesDeDesviar] sondas ao `/health/`. Confirmado, vale por
  /// [VereditoDaLoja.janela] e as seguintes vão direto.
  Future<bool> confirmarQuedaDoLocal(
    Future<bool> Function() sonda, {
    bool lenta = false,
  }) async {
    if (localForaDoAr) return true;
    if (lenta && enabled) {
      veredito.marcarForaDoAr();
      return true;
    }
    final vivo = await lojaRespondeuAlguma(
      sonda,
      vezes: sondasAntesDeDesviar,
      intervalo: intervaloEntreSondas,
    );
    if (vivo) {
      localRespondeu();
      return false;
    }
    veredito.marcarForaDoAr();
    return true;
  }

  /// Sondas SEGUIDAS sem resposta para desviar, e a pausa entre elas.
  final int sondasAntesDeDesviar;
  final Duration intervaloEntreSondas;

  bool _naoChegouAoBackend(ApiException erro) =>
      erro.isConnectivity || statusSemBackend.contains(erro.statusCode);

  bool _ehLeitura(String method) {
    final normalizado = method.toUpperCase();
    return normalizado == 'GET' || normalizado == 'HEAD';
  }

  /// O mesmo caminho, apontando para a nuvem.
  Uri enderecoPara(String path, Map<String, dynamic>? query) => Uri.parse(
    '$baseUrl$path',
  ).replace(queryParameters: query?.map((k, v) => MapEntry(k, '$v')));
}
