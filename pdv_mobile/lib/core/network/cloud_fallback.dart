import 'api_exception.dart';

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
/// E não basta a falha: antes de desviar, o terminal CONFIRMA que a loja está
/// fora, batendo no `/health/` dela. Um pacote perdido ou um reinício de dois
/// segundos do serviço não podem mudar o servidor do terminal inteiro.
///
/// ## A escrita cai, com UMA exceção: tempo esgotado
///
/// A deduplicação de escrita (`Idempotency-Key`) vive no banco de CADA
/// backend: a nuvem nunca viu a chave que a loja consumiu. Então repetir na
/// nuvem uma escrita que a loja JÁ GRAVOU executa de novo — o cliente paga
/// duas vezes, e o estorno vira uma venda que existe em dois bancos.
///
/// Conexão recusada é segura: ninguém recebeu nada, e não há o que duplicar.
/// **Tempo esgotado não é**: o servidor pode ter gravado e só a resposta ter se
/// perdido. Essa escrita NÃO cai — ela espera na fila offline, que reenvia
/// para a mesma loja com a mesma chave, e lá a deduplicação funciona.
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
  CloudFallback({String? baseUrl, this.enabled = true})
    : baseUrl = baseUrl ?? enderecoDaNuvem;

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

  /// O que NUNCA desvia, nem com a loja comprovadamente fora.
  ///
  /// Nem todo risco se resolve com faixa de numeração. Estes dois não se
  /// resolvem com nada deste lado — a resposta certa é a operação ESPERAR a
  /// loja voltar:
  ///
  /// **Fiscal.** O número da nota (`nNF`) é sequencial dentro de uma SÉRIE, e
  /// a série é justamente o mecanismo legal para separar pontos de emissão.
  /// Dois nós emitindo na mesma série produzem duas notas com o mesmo número
  /// — a SEFAZ rejeita a segunda, ou pior, aceita, e a loja fica com duas
  /// notas idênticas para desfazer no contador. Emitir da nuvem exigiria uma
  /// série própria, cadastrada e habilitada na SEFAZ; enquanto isso não
  /// existir, a emissão é da loja.
  ///
  /// **Caixa.** Abrir ou fechar sessão na nuvem enquanto a loja tem a dela
  /// gera duas sessões para o mesmo turno. A conferência do dia passa a ter
  /// dois saldos de abertura, e nenhum relatório consegue dizer qual vale.
  ///
  /// A comparação é por PREFIXO: uma rota nova debaixo de `/invoices/` nasce
  /// protegida, em vez de precisar ser lembrada aqui.
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

  /// Há quanto tempo o veredito de "a loja está fora" vale sem reconferir.
  ///
  /// Confirmado que caiu, as requisições seguintes vão direto para a nuvem: ir
  /// bater na loja morta a cada chamada custaria o tempo do `timeout` em cada
  /// gesto do operador. Vencida a janela, confere de novo — é assim que o
  /// terminal VOLTA sozinho quando a loja sobe.
  static const janelaDoVeredito = Duration(seconds: 30);

  DateTime? _confirmadoForaEm;

  /// A loja está confirmadamente fora AGORA?
  bool get localForaDoAr {
    final quando = _confirmadoForaEm;
    if (quando == null) return false;
    if (DateTime.now().difference(quando) > janelaDoVeredito) {
      _confirmadoForaEm = null;
      return false;
    }
    return true;
  }

  /// A loja respondeu. Esquece o veredito e volta a atender por ela.
  void localRespondeu() => _confirmadoForaEm = null;

  void _marcarForaDoAr() => _confirmadoForaEm = DateTime.now();

  /// Esta falha justifica tentar a nuvem?
  ///
  /// Leitura cai sempre que o backend não respondeu. Escrita cai também, MENOS
  /// quando a requisição pode ter sido executada (`reachedServer`) — aí ela
  /// espera na fila, porque repetir num outro banco cobraria duas vezes.
  bool deveTentar(String method, String path, ApiException erro) {
    if (!enabled) return false;
    if (!_naoChegouAoBackend(erro)) return false;
    // Fiscal e caixa não desviam NEM para leitura: ler o próximo número da
    // nota na nuvem já daria ao terminal um número que a loja vai reemitir.
    if (nuncaDesvia(path)) return false;
    if (_ehLeitura(method)) return true;
    return !erro.reachedServer;
  }

  /// Esta rota está na lista do que nunca sai da loja?
  bool nuncaDesvia(String path) =>
      caminhosQueNuncaDesviam.any(path.startsWith);

  /// A loja está REALMENTE fora, ou foi uma falha isolada?
  ///
  /// Desviar na primeira falha é o erro clássico: um pacote perdido, um
  /// reinício de dois segundos do serviço, e o terminal inteiro muda de
  /// servidor — passando a escrever num banco que a loja não enxerga, por
  /// causa de um soluço.
  ///
  /// `sonda` é o `/health/` do backend local, com prazo CURTO: aqui não se
  /// espera o `timeout` inteiro, porque a pergunta é "tem alguém aí?", não
  /// "processe isto".
  ///
  /// Confirmado que caiu, o veredito vale por [janelaDoVeredito] — as
  /// requisições seguintes vão direto, sem sondar de novo.
  Future<bool> confirmarQuedaDoLocal(Future<bool> Function() sonda) async {
    if (localForaDoAr) return true;
    final vivo = await sonda();
    if (vivo) {
      localRespondeu();
      return false;
    }
    _marcarForaDoAr();
    return true;
  }

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

/// QUAL SERVIDOR respondeu — a loja ou a nuvem.
///
/// A tela precisa dizer isso ao operador: o que ele está lendo da nuvem pode
/// estar atrás do que a loja tem, e o que ele lançar não aparece ali até a
/// sincronização rodar. Um dado de outra origem sem aviso é pior que tela
/// vazia — ele parece atual.
enum ServerOrigin {
  /// O backend da loja respondeu. É o caminho normal.
  loja,

  /// A loja não respondeu e a nuvem atendeu no lugar.
  nuvem,
}
