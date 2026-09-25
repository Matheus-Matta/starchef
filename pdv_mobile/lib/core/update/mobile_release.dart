/// O que o `latest-mobile.json` diz sobre a versão publicada.
///
/// Escrito pelo workflow `pdv_mobile.yml` a cada tag, e publicado no MESMO
/// GitHub Release do PDV desktop — que tem manifesto próprio
/// (`latest-desktop.json`). Ler o manifesto errado faria o celular do garçom
/// baixar um ZIP de Windows.
library;

/// Um APK publicado, com o que é preciso para confiar nele antes de instalar.
class MobileApk {
  const MobileApk({
    required this.name,
    required this.url,
    required this.sha256,
    required this.size,
    this.abi = '',
  });

  final String name;
  final Uri url;
  final String sha256;
  final int size;

  /// Vazio no APK universal; preenchido nos por arquitetura.
  final String abi;

  /// Recusa o que não dá para verificar.
  ///
  /// Sem `sha256` e `size` não existe download confiável: um arquivo truncado
  /// pela queda da rede da loja instalaria pela metade, e um APK trocado no
  /// caminho instalaria outra coisa. Preferir falhar a checagem a aceitar um
  /// pacote que não se pode conferir.
  factory MobileApk.fromJson(Map<String, dynamic> json) {
    final url = Uri.tryParse('${json['url'] ?? ''}');
    if (url == null || url.scheme != 'https' || url.host.isEmpty) {
      throw const FormatException('URL do APK inválida');
    }
    final hash = '${json['sha256'] ?? ''}'.trim().toLowerCase();
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(hash)) {
      throw const FormatException('SHA-256 do APK inválido');
    }
    final size = json['size'];
    if (size is! int || size <= 0) {
      throw const FormatException('Tamanho do APK inválido');
    }
    final name = '${json['name'] ?? ''}'.trim();
    // Nome com separador de caminho viraria escrita fora da pasta temporária.
    if (name.isEmpty || name.contains('/') || name.contains(r'\')) {
      throw const FormatException('Nome do APK inválido');
    }
    return MobileApk(
      name: name,
      url: url,
      sha256: hash,
      size: size,
      abi: '${json['abi'] ?? ''}'.trim(),
    );
  }

  /// "69,4 MB" — o número que decide se o garçom baixa agora ou depois.
  String get sizeLabel {
    final mb = size / (1024 * 1024);
    return '${mb.toStringAsFixed(1).replaceAll('.', ',')} MB';
  }
}

/// O release publicado: a versão e os APKs dela.
class MobileRelease {
  const MobileRelease({
    required this.version,
    required this.universal,
    this.perAbi = const [],
    this.notesUrl,
  });

  final String version;

  /// O universal serve qualquer aparelho, e é o único campo que as versões
  /// antigas do app conhecem.
  final MobileApk universal;

  /// Um por arquitetura, ~25 MB em vez dos ~69 MB do universal.
  final List<MobileApk> perAbi;
  final Uri? notesUrl;

  factory MobileRelease.fromJson(Map<String, dynamic> json) {
    final version = '${json['version'] ?? ''}'.trim();
    if (!RegExp(r'^\d+\.\d+\.\d+$').hasMatch(version)) {
      throw const FormatException('Versão publicada inválida');
    }
    final pacote = json['package'];
    if (pacote is! Map) throw const FormatException('Manifesto sem APK');
    final lista = json['packages'];
    return MobileRelease(
      version: version,
      universal: MobileApk.fromJson(Map<String, dynamic>.from(pacote)),
      perAbi: lista is List
          ? [
              for (final item in lista)
                if (item is Map)
                  // Um item corrompido não derruba os outros: o universal
                  // continua servindo, e perder a lista por abi só custa banda.
                  ...(() {
                    try {
                      return [MobileApk.fromJson(Map<String, dynamic>.from(item))];
                    } on FormatException {
                      return const <MobileApk>[];
                    }
                  })(),
            ]
          : const [],
      notesUrl: Uri.tryParse('${json['release_url'] ?? ''}'),
    );
  }

  /// O APK para ESTE aparelho: o da arquitetura dele, ou o universal.
  ///
  /// A diferença é de ~44 MB por atualização, baixados na rede da loja com o
  /// garçom esperando. Quando a arquitetura não está na lista (manifesto antigo,
  /// aparelho incomum), o universal instala em qualquer um.
  MobileApk apkPara(String abi) {
    if (abi.isEmpty) return universal;
    for (final apk in perAbi) {
      if (apk.abi == abi) return apk;
    }
    return universal;
  }
}

/// `true` quando `publicada` é maior que `instalada`.
///
/// Compara só o trio `X.Y.Z`, porque é isso que o manifesto publica — o número
/// de build não viaja nele. Campo não numérico vale zero em vez de derrubar a
/// checagem: um manifesto estranho não pode impedir o app de funcionar.
bool ehMaisNova(String publicada, String instalada) {
  List<int> partes(String texto) => [
    for (final parte in texto.split('.').take(3)) int.tryParse(parte.trim()) ?? 0,
  ];
  final nova = partes(publicada);
  final atual = partes(instalada);
  for (var i = 0; i < 3; i++) {
    final a = i < nova.length ? nova[i] : 0;
    final b = i < atual.length ? atual[i] : 0;
    if (a != b) return a > b;
  }
  return false;
}
