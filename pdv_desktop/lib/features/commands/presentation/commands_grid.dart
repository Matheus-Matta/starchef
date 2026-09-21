import 'package:flutter/material.dart';

import 'commands_grid_card.dart';

/// O salão de comandas: um cartão por comanda, como o mapa de mesas.
///
/// É a PRIMEIRA tela — antes de qualquer produto. O operador chega aqui para
/// escolher o cartão, e só depois vê o catálogo e o que há nele. Abrir direto
/// no catálogo obrigava a escolher a comanda numa coluna estreita ao lado dos
/// produtos, que é a ordem inversa do gesto: primeiro o cliente, depois o que
/// ele pediu.
///
/// A cor é a primeira coisa que se lê num salão cheio — antes da palavra.
/// Verde = livre; laranja = ocupada. "Ocupada" é DERIVADO de ter anotação
/// pendente, e não de um campo de estado: o cartão é um bloco de notas, e o que
/// decide se ele tem dono é ter o que cobrar.
class CommandsGrid extends StatelessWidget {
  const CommandsGrid({
    super.key,
    required this.comandas,
    required this.carregando,
    required this.controladorDaBusca,
    required this.controladorDoLeitor,
    required this.focoDoLeitor,
    required this.onBuscaMudou,
    required this.onLeitura,
    required this.onAbrir,
  });

  final List<Map<String, dynamic>> comandas;
  final bool carregando;
  final TextEditingController controladorDaBusca;
  final TextEditingController controladorDoLeitor;
  final FocusNode focoDoLeitor;
  final VoidCallback onBuscaMudou;
  final VoidCallback onLeitura;
  final ValueChanged<Map<String, dynamic>> onAbrir;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Os dois campos têm a MESMA estrutura de decoração — rótulo em cima,
          // ajuda embaixo. Um `TextField` com rótulo e ajuda é mais alto que um
          // só com `hint`, e misturar os dois numa `Row` desalinha as caixas e
          // as linhas de base: eles ficam visivelmente tortos lado a lado.
          //
          // `CrossAxisAlignment.start` completa o acerto: com o padrão
          // (`center`), o campo mais baixo flutuaria no meio do mais alto.
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: controladorDoLeitor,
                  focusNode: focoDoLeitor,
                  autofocus: true,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.qr_code_scanner_rounded),
                    labelText: 'Passe o cartão',
                    helperText: 'O leitor digita o código e manda Enter.',
                    isDense: true,
                  ),
                  onSubmitted: (_) => onLeitura(),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: controladorDaBusca,
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search_rounded),
                    labelText: 'Filtrar',
                    helperText: 'Número, código ou nome do cliente.',
                    isDense: true,
                  ),
                  onChanged: (_) => onBuscaMudou(),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Expanded(
            child: comandas.isEmpty
                ? Center(
                    child: Text(
                      carregando
                          ? 'Carregando…'
                          : 'Nenhuma comanda encontrada.',
                      style: TextStyle(color: scheme.onSurfaceVariant),
                    ),
                  )
                : GridView.builder(
                    gridDelegate:
                        const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 170,
                          childAspectRatio: 1.05,
                          crossAxisSpacing: 12,
                          mainAxisSpacing: 12,
                        ),
                    itemCount: comandas.length,
                    itemBuilder: (_, indice) => CommandFloorCard(
                      comanda: comandas[indice],
                      onTap: () => onAbrir(comandas[indice]),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
