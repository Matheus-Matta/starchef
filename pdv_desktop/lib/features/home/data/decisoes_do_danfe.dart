import 'dart:convert';
import 'dart:io';

import '../../../core/storage/app_paths.dart';

/// "Imprimir a NFC-e?" respondido pelo caixa, para UM pedido.
class DecisaoDoDanfe {
  const DecisaoDoDanfe({
    required this.pedidoId,
    required this.sequencia,
    required this.imprimir,
    required this.quando,
  });

  final String pedidoId;

  /// O número que o caixa vê (`#123`), para conferir sem abrir o pedido.
  final String sequencia;
  final bool imprimir;
  final DateTime quando;

  Map<String, dynamic> toJson() => {
    'pedido': pedidoId,
    'sequencia': sequencia,
    'imprimir': imprimir,
    'quando': quando.toIso8601String(),
  };

  static DecisaoDoDanfe? fromJson(Object? json) {
    if (json is! Map) return null;
    final quando = DateTime.tryParse('${json['quando']}');
    final pedido = '${json['pedido'] ?? ''}';
    if (quando == null || pedido.isEmpty) return null;
    return DecisaoDoDanfe(
      pedidoId: pedido,
      sequencia: '${json['sequencia'] ?? ''}',
      imprimir: json['imprimir'] == true,
      quando: quando,
    );
  }
}

/// As respostas do DANFE DESTE terminal, a mais nova primeiro.
///
/// A pergunta sai junto com a venda e o DANFE só sai quando a SEFAZ autoriza
/// — segundos ou minutos depois, com o caixa já em outro cliente. Guardar a
/// resposta com o número do pedido é o que diz, depois, qual venda era para
/// imprimir e qual não era, mesmo com o PDV reaberto no meio.
///
/// Arquivo próprio, e não as preferências do terminal: é registro de operação,
/// não configuração, e cresce a cada venda.
class DecisoesDoDanfe {
  DecisoesDoDanfe({File? arquivo})
    : _arquivo = arquivo ?? AppPaths.dataFile('danfe_decisoes.json');

  /// A do terminal: uma só, para duas gravações não disputarem o arquivo.
  static final doTerminal = DecisoesDoDanfe();

  static const maximo = 50;

  final File _arquivo;
  List<DecisaoDoDanfe>? _lidas;

  /// Ler, trocar e gravar, UM de cada vez. Com só a gravação em fila, três
  /// respostas seguidas liam o arquivo antes de a anterior gravar e cada uma
  /// sobrescrevia as outras: ficava só a última (caixa rápido, em teste).
  Future<void> _fila = Future.value();

  Future<List<DecisaoDoDanfe>> ler() => _fila.then((_) => _carregar());

  /// `null` quando o caixa não respondeu nada para este pedido.
  Future<bool?> imprimir(String pedidoId) async {
    for (final decisao in await ler()) {
      if (decisao.pedidoId == pedidoId) return decisao.imprimir;
    }
    return null;
  }

  Future<void> registrar(DecisaoDoDanfe decisao) {
    final vez = _fila.then((_) async {
      final lista = [
        decisao,
        ...(await _carregar()).where((d) => d.pedidoId != decisao.pedidoId),
      ].take(maximo).toList();
      _lidas = lista;
      await _gravar(jsonEncode([for (final d in lista) d.toJson()]));
    });
    return _fila = vez;
  }

  /// Só dentro da fila: fora dela, uma leitura do disco em andamento podia
  /// voltar DEPOIS de uma resposta nova e trocá-la pelo arquivo antigo.
  Future<List<DecisaoDoDanfe>> _carregar() async => _lidas ??= await _doDisco();

  Future<List<DecisaoDoDanfe>> _doDisco() async {
    try {
      if (!await _arquivo.exists()) return [];
      final json = jsonDecode(await _arquivo.readAsString());
      if (json is! List) return [];
      return json
          .map(DecisaoDoDanfe.fromJson)
          .whereType<DecisaoDoDanfe>()
          .toList();
    } catch (_) {
      // Arquivo estragado não para o caixa: o registro recomeça vazio.
      return [];
    }
  }

  Future<void> _gravar(String texto) async {
    try {
      await _arquivo.parent.create(recursive: true);
      final temporario = File('${_arquivo.path}.tmp');
      await temporario.writeAsString(texto, flush: true);
      await temporario.rename(_arquivo.path);
    } catch (_) {
      // Disco cheio ou só leitura: a resposta continua valendo em memória.
    }
  }
}
