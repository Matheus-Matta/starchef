# Código do operador e campos adicionais

Escrito para: quem for mexer em lançamento de item, nos dois PDVs ou no backend.

## O problema

Um totem no salão, com o app do garçom aberto e **uma sessão só**. Quem lança o
item não é o usuário logado — são vários garçons usando o mesmo aparelho. Sem
mais nada, todo lançamento do dia fica no nome do mesmo login, e a pergunta
**"quem anotou isso?"** deixa de ter resposta.

## O que o código É, e o que não é

| | |
| --- | --- |
| **É** | atribuição. A linha do item passa a dizer quem a registrou. |
| **Não é** | autenticação. Qualquer número passa, e quem sabe o do colega pode usá-lo. |
| **Não é** | autorização. Nenhuma regra de cancelamento, desconto ou caixa olha este código. |

Ele **não é conferido contra cadastro nenhum**, de propósito: a política é interna
do restaurante (matrícula, número do crachá, o que eles decidirem), e exigir
cadastro transformaria uma medida de rastro em mais um cadastro para manter — e no
dia em que o garçom novo entrasse, ele não poderia lançar.

**Só dígitos.** Letra e acento num código digitado às pressas viram dois registros
para a mesma pessoa ("Joao" e "João"), e o relatório mostra os dois.

---

## `metafields`: onde ele mora

Campo `JSONField` em cinco lugares:

| Model | Para que |
| --- | --- |
| `Command` | o código de quem **abriu o cartão** |
| `Order` | o código de quem **abriu a conta** |
| `OrderItem` | o código de quem **lançou aquele item** |
| `CommandItem` | idem, na anotação da comanda |

`OrderItem` e `CommandItem` recebem o campo de `ConsumptionItem`, a base
abstrata dos dois — a pergunta é a mesma nos dois, e o aparelho compartilhado
lança em ambos.

**O item é o único lugar onde o código serve de verdade.** Num pedido de uma hora,
três garçons anotam; um código só no cabeçalho atribuiria tudo ao primeiro.

### A porta é estreita porque o cliente escreve nela

`apps/core/metafields.py` normaliza tudo que entra:

- dicionário **raso** — lista e objeto aninhado são recusados;
- chaves em `a-z0-9_`, no máximo 40 caracteres, normalizadas para caixa baixa;
- valores escalares guardados como **texto**, no máximo 120 caracteres;
- no máximo 20 chaves por registro.

Sem isso, um `JSONField` escrito por um app é lugar para gravar megabytes,
estrutura que nenhum relatório consegue agrupar, e chave com espaço que quebra
todo agrupamento. Valor sempre como texto porque o mesmo campo recebe `"12"` de um
cliente e `12` de outro — guardar como vem faria a consulta por igualdade achar
metade dos registros.

### A herança

```
Command.metafields  ──herda──▶  Order.metafields  ──herda──▶  OrderItem.metafields
```

`apps.core.metafields.herdar(destino, origem)` copia de `origem` o que falta em
`destino`, **sem sobrescrever**. O que está no destino é mais recente e mais
específico: sobrescrever trocaria o rastro de quem fechou a conta pelo de quem
abriu o cartão.

O cartão é aberto no salão e o pedido só nasce no caixa, horas depois. Sem a
herança, o rastro do atendimento inteiro sumiria justamente no registro que fica.

---

## Como ligar

`Restaurant.require_operator_code` — **nasce desligado**. Uma exigência nova que
nasce ligada tranca o lançamento no dia do deploy, com o salão cheio e ninguém
sabendo que código digitar.

No frontend: cadastro do restaurante → seção **Operação** → "Pedir código do
operador no app do garçom".

Ligado, `apps.orders.operator_code.exigir()` cobra o código em:

- `create_order` — "abrir pedido"
- `add_order_item` — "lançar item"
- `launch_item` (comanda) — "lançar item na comanda"

A conferência vem **antes** das outras validações: barrar por falta de código
depois de resolver peso, variação e adicional gastaria as consultas para nada.

---

## No app do garçom

**A flag viaja com a SESSÃO** (`require_operator_code` no payload de login e de
`/me/`), e não por uma consulta ao cadastro do restaurante: o app precisa da
resposta antes do primeiro lançamento, e perguntar ao `/restaurants/` exigiria dar
ao garçom leitura do cadastro inteiro só para descobrir se deve pedir um número.
Muda no próximo login ou na revalidação da sessão — ligar a opção no meio do
serviço não interrompe quem está atendendo.

### O código vale por ATENDIMENTO

`OperatorCodeKeeper` guarda um código por pedido/comanda aberto. É a decisão de
desenho que mais importa aqui:

- **por item** seria o registro mais fiel, e inutilizável: dez pratos numa mesa são
  dez digitações, e a décima vira "1111" para acabar logo — um rastro que mente é
  pior do que nenhum;
- **por sessão** não serve num aparelho compartilhado: o segundo garçom lançaria no
  código do primeiro sem perceber.

Então: pergunta uma vez ao entrar no atendimento, esquece ao sair. Quem assume o
aparelho depois informa o seu.

A folha (`operator_code_sheet.dart`) abre **antes do cardápio**. Pedir depois faria
o garçom escolher o prato, configurar variação e adicional, e só então descobrir
que precisa de um código que talvez não saiba — com o cliente esperando. Ela não
tem "cancelar e lançar assim": o restaurante ligou a exigência porque quer o
rastro, e uma saída pela lateral faria metade dos lançamentos não ter código.

**O código viaja com o ITEM**, no corpo da requisição, e por isso sobrevive à fila
offline: a operação enfileirada sobe horas depois, quando quem lançou pode nem
estar mais no turno.

---

## Onde o código aparece

`Order.operator_label` é a fonte única — `"Maria Silva - 4821"`. Propriedade porque
**três** lugares imprimem a mesma linha, e montada em cada um a primeira mudança de
formato faria os três discordarem sobre quem atendeu a mesma venda.

| Onde | O que mostra |
| --- | --- |
| Cupom de texto (`printers/services.py`) | `Operador: Maria Silva - 4821` |
| Recibo HTML (`printers/templates/.../receipt.html`) | idem |
| PDV desktop, resumo do pagamento | linha `Operador` |
| PDV web, resumo do pagamento | linha `Operador` |

O PDV desktop **não monta cupom**: ele pede a nota ao servidor
(`/orders/{id}/print/`), então a linha sai de um lugar só nos dois.

O código aparece quando **existe**, e não quando o restaurante o exige: uma venda
registrada com código continua imprimindo o rastro dela depois que alguém desligar
a opção — que é justamente quando o rastro é pedido.

---

## Sincronização

`metafields` e `require_operator_code` são campos novos em entidades que já
sincronizam (`command`, `order`, `order_item`, `command_item`, `restaurant`), então
viajam sem mudança no catálogo. Vale o mesmo aviso de sempre: `deserialize()`
descarta em silêncio campo que o model local não conhece, então nuvem e loja sobem
**na mesma tag** — uma loja atrasada gravaria o item sem o código e ninguém veria
erro nenhum.
