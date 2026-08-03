import 'scale_sample.dart';

/// Decodifica o fluxo serial de uma balança em leituras de peso.
///
/// Cada fabricante enquadra e formata o peso de um jeito. As implementações
/// abaixo cobrem o enquadramento documentado mais comum de cada família; o
/// firmware, a configuração do equipamento e o modelo específico ainda podem
/// variar, então cada modelo novo exige homologação física antes de ir para
/// produção. Quando nenhuma delas servir, [GenericNumericProtocol] extrai o
/// último número de cada linha e funciona com a maioria dos equipamentos em
/// modo de transmissão contínua.
abstract class ScaleProtocol {
  ScaleProtocol();

  /// Identificador persistido no cadastro da balança.
  String get id;

  /// Nome exibido na configuração.
  String get label;

  /// Bytes que pedem uma pesagem ao equipamento.
  ///
  /// Muitas balanças saem de fábrica em modo "sob demanda": elas só respondem
  /// quando recebem esta solicitação, e ficam mudas em transmissão contínua.
  /// É esse o caso em que a estação não recebe nada e o operador precisa do
  /// botão de pegar peso.
  ///
  /// `ENQ` (0x05) é o pedido usado pelas três famílias suportadas. O byte
  /// exato ainda varia por modelo e configuração, então uma balança que não
  /// responda a ele precisa ser homologada.
  List<int> get weightRequest => const [0x05];

  final StringBuffer _buffer = StringBuffer();

  static const _maximumFrameLength = 64;

  /// Cria o protocolo a partir do valor gravado em `settings.protocol`.
  factory ScaleProtocol.forId(String? id) => switch (id?.trim().toLowerCase()) {
    'toledo' => ToledoProtocol(),
    'filizola' => FilizolaProtocol(),
    'urano' => UranoProtocol(),
    _ => GenericNumericProtocol(),
  };

  /// Todos os protocolos disponíveis para seleção na interface.
  static List<ScaleProtocol> get available => [
    GenericNumericProtocol(),
    ToledoProtocol(),
    FilizolaProtocol(),
    UranoProtocol(),
  ];

  /// Acumula os bytes recebidos e devolve as leituras já completas.
  List<ScaleSample> decode(List<int> bytes) {
    final samples = <ScaleSample>[];
    for (final byte in bytes) {
      if (_isFrameTerminator(byte)) {
        final frame = _buffer.toString();
        _buffer.clear();
        final sample = _frameToSample(frame);
        if (sample != null) samples.add(sample);
        continue;
      }
      if (_isFrameStart(byte)) {
        // Um novo início descarta um quadro parcial anterior: bytes perdidos
        // não podem contaminar a próxima pesagem.
        _buffer.clear();
        continue;
      }
      if (byte >= 32 && byte <= 126) {
        if (_buffer.length >= _maximumFrameLength) {
          _buffer.clear();
          continue;
        }
        _buffer.writeCharCode(byte);
      }
    }
    return samples;
  }

  void reset() => _buffer.clear();

  bool _isFrameStart(int byte) => byte == 0x02; // STX
  bool _isFrameTerminator(int byte) =>
      byte == 0x03 || byte == 0x0a || byte == 0x0d; // ETX, LF, CR

  ScaleSample? _frameToSample(String frame);

  /// Converte dígitos sem separador assumindo três casas decimais (gramas).
  static double? parseWeight(String digits, {int impliedDecimals = 3}) {
    final normalized = digits.replaceAll(',', '.').trim();
    if (normalized.isEmpty) return null;
    if (normalized.contains('.')) return double.tryParse(normalized);
    final value = int.tryParse(normalized);
    if (value == null) return null;
    return value / _pow10(impliedDecimals);
  }

  static double _pow10(int exponent) {
    var result = 1.0;
    for (var index = 0; index < exponent; index++) {
      result *= 10;
    }
    return result;
  }
}

/// Extrai o último número de cada linha recebida.
///
/// É o comportamento mais tolerante e serve como padrão para equipamentos em
/// transmissão contínua cujo enquadramento exato não foi homologado. Não há bit
/// de estabilidade, então quem decide é o leitor por repetição.
class GenericNumericProtocol extends ScaleProtocol {
  @override
  String get id => 'generic';

  @override
  String get label => 'Genérico (numérico contínuo)';

  @override
  ScaleSample? _frameToSample(String frame) {
    final matches = RegExp(r'-?\d+(?:[.,]\d+)?').allMatches(frame).toList();
    if (matches.isEmpty) return null;
    final raw = matches.last.group(0)!.replaceAll(',', '.');
    var weight = double.tryParse(raw);
    if (weight == null) return null;
    // Sem separador decimal e com valor alto, o equipamento está transmitindo
    // gramas — a leitura de 1500 significa 1,500 kg.
    if (!raw.contains('.') && weight.abs() > 100) weight /= 1000;
    return ScaleSample(
      weightKg: weight.abs(),
      negative: weight < 0,
      raw: frame,
    );
  }
}

/// Toledo (linha Prix / protocolo 9091).
///
/// Os quadros chegam entre STX e ETX com o peso em dígitos e casas decimais
/// implícitas. Um sinal `-` indica peso negativo e o caractere `I`
/// (instável) ou `?` marca leitura em movimento nos modelos que o transmitem.
class ToledoProtocol extends ScaleProtocol {
  @override
  String get id => 'toledo';

  @override
  String get label => 'Toledo (Prix / 9091)';

  @override
  ScaleSample? _frameToSample(String frame) {
    final trimmed = frame.trim();
    if (trimmed.isEmpty) return null;
    final unstable =
        trimmed.contains('I') || trimmed.contains('?') || trimmed.contains('M');
    final negative = trimmed.startsWith('-');
    final digits = RegExp(r'\d+(?:[.,]\d+)?').firstMatch(trimmed)?.group(0);
    if (digits == null) return null;
    final weight = ScaleProtocol.parseWeight(digits);
    if (weight == null) return null;
    return ScaleSample(
      weightKg: weight,
      stable: !unstable,
      negative: negative,
      raw: frame,
    );
  }
}

/// Filizola (linha CS / MF em transmissão contínua).
///
/// O peso vem em gramas, sem separador decimal, terminado por CR. Os modelos
/// que enviam o campo de status usam `S` para estável e `U`/`M` para
/// instável.
class FilizolaProtocol extends ScaleProtocol {
  @override
  String get id => 'filizola';

  @override
  String get label => 'Filizola (CS / MF)';

  @override
  ScaleSample? _frameToSample(String frame) {
    final trimmed = frame.trim();
    if (trimmed.isEmpty) return null;
    final upper = trimmed.toUpperCase();
    final bool? stable = upper.contains('U') || upper.contains('M')
        ? false
        : upper.contains('S')
        ? true
        : null;
    final negative = trimmed.contains('-');
    final digits = RegExp(r'\d+(?:[.,]\d+)?').firstMatch(trimmed)?.group(0);
    if (digits == null) return null;
    final weight = ScaleProtocol.parseWeight(digits);
    if (weight == null) return null;
    return ScaleSample(
      weightKg: weight,
      stable: stable,
      negative: negative,
      raw: frame,
    );
  }
}

/// Urano (linha UDC / POP-S).
///
/// O peso chega já formatado com ponto decimal e sufixo de unidade, por
/// exemplo `+00.500kg`. Quando o sufixo é `g`, o valor é convertido para
/// quilogramas.
class UranoProtocol extends ScaleProtocol {
  @override
  String get id => 'urano';

  @override
  String get label => 'Urano (UDC / POP-S)';

  @override
  ScaleSample? _frameToSample(String frame) {
    final trimmed = frame.trim();
    if (trimmed.isEmpty) return null;
    final match = RegExp(
      r'([+-]?)\s*(\d+(?:[.,]\d+)?)\s*(kg|g)?',
      caseSensitive: false,
    ).firstMatch(trimmed);
    if (match == null) return null;
    final value = double.tryParse(match.group(2)!.replaceAll(',', '.'));
    if (value == null) return null;
    final inGrams = match.group(3)?.toLowerCase() == 'g';
    final upper = trimmed.toUpperCase();
    return ScaleSample(
      weightKg: inGrams ? value / 1000 : value,
      stable: upper.contains('I') || upper.contains('M') ? false : null,
      negative: match.group(1) == '-',
      raw: frame,
    );
  }
}
