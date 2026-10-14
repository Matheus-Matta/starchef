import 'package:flutter/material.dart';

/// Um cálculo do total por vez, e a resposta velha nunca vence.
///
/// Cupom, desconto, taxa e CPF/CNPJ vão ao servidor, que devolve o total
/// refeito. Antes, cada um tinha a sua trava: um cupom e um desconto podiam
/// estar no ar ao mesmo tempo, e a resposta que chegasse por último ganhava —
/// às vezes a mais antiga. E nada impedia o caixa de registrar o pagamento
/// sobre o total que ainda ia mudar.
///
/// Aqui é um só: enquanto calcula, a tela de pagamento inteira espera
/// (`emCurso`), um segundo pedido é recusado (duplo clique) e `descartar`
/// invalida o que estiver no ar quando o caixa sai da tela.
class CalculoDoTotal {
  int _rodada = 0;
  bool _emCurso = false;

  bool get emCurso => _emCurso;

  /// Roda `calcular` e entrega o resultado a `aplicar`, ou o erro a `falhar`.
  ///
  /// Devolve `false` quando foi recusado (já havia um em curso) ou quando a
  /// resposta chegou velha: aí nem `aplicar` nem `falhar` são chamados.
  /// A trava cai ANTES de `falhar`, para quem quiser tentar de novo dali
  /// (o desconto que pede a senha do gerente) não ser recusado.
  Future<bool> rodar<T>({
    required Future<T> Function() calcular,
    required void Function(T valor) aplicar,
    required void Function(Object erro) falhar,
  }) async {
    if (_emCurso) return false;
    _emCurso = true;
    final minha = ++_rodada;
    try {
      final valor = await calcular();
      if (minha != _rodada) return false;
      _emCurso = false;
      aplicar(valor);
      return true;
    } catch (erro) {
      if (minha != _rodada) return false;
      _emCurso = false;
      falhar(erro);
      return false;
    }
  }

  /// O caixa saiu da tela: o que estiver no ar não vale mais.
  void descartar() {
    _rodada++;
    _emCurso = false;
  }
}

/// "Adicionar pagamento" e "Concluir pedido": enquanto o total é calculado,
/// dizem isso e não aceitam clique.
class BotaoDoPagamento extends StatelessWidget {
  const BotaoDoPagamento({
    super.key,
    required this.calculando,
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final bool calculando;
  final IconData icon;
  final String label;

  /// `null` desliga o botão pelo motivo de quem o monta (falta valor).
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    height: 40,
    child: FilledButton.icon(
      onPressed: calculando ? null : onPressed,
      icon: calculando
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Icon(icon, size: 18),
      label: Text(
        calculando ? 'Calculando total...' : label,
        style: const TextStyle(fontSize: 13),
      ),
    ),
  );
}
