import 'package:flutter/material.dart';

import '../data/command_repository.dart';

// As cores de estado da comanda, iguais às da web (`styles/pdv-panels.css`):
// quem alterna entre os dois no turno lê a mesma cor para o mesmo estado.
//
// São os tons MÉDIOS de propósito. O selo não tem fundo próprio — a palavra é
// pintada direto sobre a superfície do cartão —, então um tom escuro sumiria
// no tema escuro e um tom claro sumiria no claro. Estes dois se leem nos dois.
const _verde = Color(0xFF16A34A);
const _laranja = Color(0xFFEA580C);

/// Um cartão de comanda na lista: número, código, cliente e o selo de estado.
///
/// Fica em arquivo próprio porque é ele que carrega a REGRA DE COR, e regra de
/// cor é o que mais muda depois — quem for ajustar um matiz abre este arquivo
/// e não precisa ler a busca, o leitor de código nem a rolagem da lista.
class CommandCard extends StatelessWidget {
  const CommandCard({
    super.key,
    required this.comanda,
    required this.ativo,
    required this.onTap,
  });

  final Map<String, dynamic> comanda;
  final bool ativo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // A cor é a primeira coisa que o operador lê num salão cheio — antes da
    // palavra. Verde = livre; laranja = ocupada.
    //
    // "Ocupada" é DERIVADO de ter anotação pendente, e não de um campo de
    // estado: o cartão é um bloco de notas, e o que decide se ele tem dono é
    // ter o que cobrar.
    final ocupada = comandaTemContaAberta(comanda);
    final (rotulo, corDoEstado) = ocupada
        ? ('OCUPADA', _laranja)
        : ('LIVRE', _verde);
    final contorno = ativo ? scheme.primary : scheme.outlineVariant;
    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        // O contorno é UNIFORME, e precisa continuar sendo: `Border` com um
        // lado de cor diferente dos outros é ilegal junto com `borderRadius`,
        // e o Flutter só descobre isso na hora de PINTAR — a caixa não pinta,
        // os filhos não aparecem, e o cartão fica desenhado e vazio na tela.
        // O analisador não vê, porque o erro não está no tipo. Foi assim que
        // a faixa de estado à esquerda apagou a lista inteira de comandas.
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: contorno, width: ativo ? 2 : 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${comanda['number'] ?? ''}',
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  Text(
                    rotulo,
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.w700,
                      letterSpacing: .4,
                      color: corDoEstado,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${comanda['code'] ?? ''}',
                      style: TextStyle(
                        fontSize: 11,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  Text(
                    '${comanda['customer_name'] ?? '—'}',
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
