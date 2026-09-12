/// Parametros da execucao e os perfis prontos de intensidade.
///
/// Chegam por `--dart-define`, porque `flutter test` nao repassa argumentos
/// livres para o codigo do teste.
library;

class PerfilCarga {
  const PerfilCarga({
    required this.nome,
    required this.vendas,
    required this.itensPorVenda,
    required this.leituras,
    required this.pesagens,
    required this.cupons,
    required this.terminais,
    required this.registrosPorTipo,
  });

  final String nome;
  final int vendas;
  final int itensPorVenda;
  final int leituras;
  final int pesagens;
  final int cupons;
  final int terminais;
  final int registrosPorTipo;

  static const fumaca = PerfilCarga(
    nome: 'fumaca',
    vendas: 10,
    itensPorVenda: 3,
    leituras: 40,
    pesagens: 10,
    cupons: 20,
    terminais: 2,
    registrosPorTipo: 50,
  );

  static const leve = PerfilCarga(
    nome: 'leve',
    vendas: 60,
    itensPorVenda: 4,
    leituras: 300,
    pesagens: 40,
    cupons: 120,
    terminais: 3,
    registrosPorTipo: 300,
  );

  static const medio = PerfilCarga(
    nome: 'medio',
    vendas: 250,
    itensPorVenda: 5,
    leituras: 1200,
    pesagens: 150,
    cupons: 400,
    terminais: 4,
    registrosPorTipo: 1500,
  );

  static const pesado = PerfilCarga(
    nome: 'pesado',
    vendas: 800,
    itensPorVenda: 6,
    leituras: 4000,
    pesagens: 500,
    cupons: 1200,
    terminais: 6,
    registrosPorTipo: 5000,
  );

  static const extremo = PerfilCarga(
    nome: 'extremo',
    vendas: 2500,
    itensPorVenda: 8,
    leituras: 12000,
    pesagens: 1500,
    cupons: 4000,
    terminais: 10,
    registrosPorTipo: 20000,
  );

  static const todos = <String, PerfilCarga>{
    'fumaca': fumaca,
    'leve': leve,
    'medio': medio,
    'pesado': pesado,
    'extremo': extremo,
  };
}

/// Configuracao efetiva, montada a partir dos `--dart-define`.
class ConfigCarga {
  ConfigCarga({
    required this.perfil,
    required this.proporcaoCaos,
    required this.fases,
    required this.semente,
    required this.destino,
    required this.detalhado,
  });

  factory ConfigCarga.doAmbiente() {
    const nomePerfil = String.fromEnvironment('PERFIL', defaultValue: 'leve');
    const caos = String.fromEnvironment('CAOS', defaultValue: '0.3');
    const fases = String.fromEnvironment('FASES', defaultValue: 'todas');
    const semente = int.fromEnvironment('SEMENTE', defaultValue: 20260910);
    // `flutter test` roda com o cwd em `flutter/`; o `..` coloca o relatorio
    // do PDV ao lado do da suite Python, em um lugar so.
    const destino = String.fromEnvironment(
      'RELATORIO',
      defaultValue: '../artifacts/loadtest/pdv',
    );
    const detalhado = bool.fromEnvironment('DETALHADO');
    return ConfigCarga(
      perfil: PerfilCarga.todos[nomePerfil] ?? PerfilCarga.leve,
      proporcaoCaos: double.tryParse(caos) ?? 0.3,
      fases: fases == 'todas'
          ? const <String>[]
          : fases.split(',').map((f) => f.trim()).where((f) => f.isNotEmpty).toList(),
      semente: semente,
      destino: destino,
      detalhado: detalhado,
    );
  }

  final PerfilCarga perfil;
  final double proporcaoCaos;
  final List<String> fases;
  final int semente;
  final String destino;
  final bool detalhado;

  bool rodaFase(String nome) => fases.isEmpty || fases.contains(nome);

  Map<String, Object?> paraJson() => {
    'perfil': perfil.nome,
    'vendas': perfil.vendas,
    'itens_por_venda': perfil.itensPorVenda,
    'leituras': perfil.leituras,
    'pesagens': perfil.pesagens,
    'cupons': perfil.cupons,
    'terminais': perfil.terminais,
    'registros_por_tipo': perfil.registrosPorTipo,
    'proporcao_caos': proporcaoCaos,
    'fases': fases.isEmpty ? 'todas' : fases.join(','),
    'semente': semente,
  };
}
