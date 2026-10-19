import '../../../core/data/local_id.dart';

/// O identificador de UM prato pesado, o mesmo em todas as tentativas.
///
/// Ele nascia dentro de cada tentativa de lançamento. A rede caía depois de o
/// servidor gravar, o operador tocava "Tentar de novo" (ou relia a comanda) e
/// ia um identificador novo: o servidor via outro prato — dois no cartão, ou o
/// prato numa segunda comanda automática. Com o mesmo, ele reconhece a
/// repetição (`pesagem_por_uuid.py`) e devolve o lançamento que já fez.
///
/// O prato é reconhecido pela IDENTIDADE do objeto da pesagem (o mesmo
/// `WeighedItem` retido na máquina entre as tentativas). Lançado com sucesso,
/// [esquecer]: o mesmo peso de novo ("Pesar de novo") é um prato novo.
class IdDaPesagem {
  Object? _prato;
  String? _id;

  String para(Object prato) {
    if (!identical(_prato, prato) || _id == null) {
      _prato = prato;
      _id = LocalId.uuid();
    }
    return _id!;
  }

  void esquecer() {
    _prato = null;
    _id = null;
  }
}
