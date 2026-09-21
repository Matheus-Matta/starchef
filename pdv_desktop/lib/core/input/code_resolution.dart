/// O que um código lido virou: uma comanda, um produto, ou nada.
///
/// Fica separado das consultas porque é o que ATRAVESSA a fronteira: as telas
/// recebem isto, e não o serviço. Quem for ler "o que a leitura me devolve"
/// abre um arquivo de 60 linhas em vez do de buscas.
library;


/// O que um código lido representa, depois de consultado.
class CodeResolution {
  const CodeResolution._({
    required this.kind,
    this.command,
    this.product,
    this.matchedField = '',
  });

  const CodeResolution.none() : this._(kind: CodeResolutionKind.none);

  const CodeResolution.command(Map<String, dynamic> value, {String field = ''})
    : this._(
        kind: CodeResolutionKind.command,
        command: value,
        matchedField: field,
      );

  const CodeResolution.product(Map<String, dynamic> value, {String field = ''})
    : this._(
        kind: CodeResolutionKind.product,
        product: value,
        matchedField: field,
      );

  final CodeResolutionKind kind;
  final Map<String, dynamic>? command;
  final Map<String, dynamic>? product;

  /// Campo que casou (`ean`, `internal_code`, `code`, `number`).
  final String matchedField;

  bool get found => kind != CodeResolutionKind.none;

  String get matchedFieldLabel => switch (matchedField) {
    'ean' => 'código de barras',
    'internal_code' => 'código interno',
    'code' => 'código da comanda',
    'number' => 'número da comanda',
    _ => 'código',
  };
}

enum CodeResolutionKind { none, command, product }
