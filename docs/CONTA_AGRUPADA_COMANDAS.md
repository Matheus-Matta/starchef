# Conta agrupada: pagar várias comandas num pedido só

Uma mesa com quatro comandas de uma família. O pai paga tudo. O caixa lê as
quatro (ou inclui à mão), os itens das quatro entram **num pedido só**, e ele
cobra uma vez.

Implementa `afazer/PLANO_CONTA_AGRUPADA_COMANDAS.md`.

## O desenho em uma frase

A comanda é **coletor de itens**, não documento financeiro. Durante o serviço
cada comanda tem o pedido de trabalho dela — é o que faz cozinha, KDS e
impressão continuarem funcionando por comanda, como já funcionavam. No
fechamento, os itens das comandas escolhidas são **reparentados para um pedido
novo**, que é o que recebe pagamento, CPF, taxa e nota.

```
serviço:     Comanda 12 → pedido 12     (cozinha/KDS/impressão por comanda)
             Comanda 13 → pedido 13
             Comanda 14 → pedido 14
fechamento:  itens de 12,13,14  ──►  PEDIDO NOVO  ──► 1 pagamento, 1 NFC-e
             pedidos 12..14 ficam `merged` (histórico, sem faturar de novo)
```

Um pedido final mantém **um CPF, um pagamento e uma NFC-e**. Nenhuma FK nova em
`Payment` ou `Invoice`; `Invoice.order` continua sendo OneToOne obrigatório.

## Por que o destino é um pedido NOVO

A tentação é usar o pedido da primeira comanda como destino. Não dá: ela também
precisa preservar o pedido e os lotes de cozinha dela. Tratá-la como origem e
destino ao mesmo tempo duplicaria ou perderia itens e taxa.

O destino nasce como pedido de balcão — sem comanda e sem mesa. Mas ele **não é
uma venda de balcão**, e o recibo não o chama assim: `merged_command_labels()`
lê as comandas de origem e o cupom sai com "CONTA DE COMANDAS" e a lista delas.

## Os modelos

```python
# apps/orders/models_merge.py
class OrderMerge(TenantModel):
    target_order = OneToOne(Order)          # o pedido novo
    status = open | confirmed | paid | cancelled

class OrderMergeSource(TenantModel):
    merge        = FK(OrderMerge, related_name="sources")
    command      = FK(Command)
    source_order = FK(Order)                # nunca é o target_order
    active       = Bool()                   # True até cancelar ou quitar
    # + snapshot de subtotal, taxa, desconto, total e status da origem
```

**Não existe FK de Order para Order.** O vínculo origem → destino é
`OrderMergeSource.source_order → merge.target_order`. Uma FK autorreferente
faria a carga essencial e o replay entregarem a origem antes do destino.

### A defesa contra dois caixas é do BANCO

```python
models.UniqueConstraint(
    fields=["command"], condition=models.Q(active=True),
    name="unique_active_merge_per_command",
)
```

Checar `merge.status` num `if` acontece **antes** do lock do outro caixa. Este
índice acontece no INSERT, e não há como os dois passarem. `add_command_to_merge`
captura o `IntegrityError` e devolve 409.

### O item sabe de quem ele é

```python
# apps/orders/models.py — OrderItem
command           = FK(Command, null=True)   # preenchido no lançamento
origin_order      = FK(Order, null=True)     # de onde veio no merge
command_status    = open | closed            # financeiro, NÃO de produção
command_closed_at = DateTime(null=True)
```

Antes, a comanda se descobria pelo pedido — o que funciona enquanto um pedido
**é** uma comanda. Depois da consolidação todos os itens vivem no mesmo pedido,
e a origem se perderia.

Recuperar pelo lote de cozinha (`item.batch.order.command`) é furado, e o furo é
silencioso: `OrderItem.batch` é nulo para item que ainda não foi à cozinha —
justamente a bebida pedida por último, a que entra na conta sem passar pela
produção.

## `command_status` é um campo NOVO, e o status da cozinha não serve

`OrderItem.status` já existe (`pending → queued → sent → preparing → ready →
delivered`, mais `cancelled` e `comped`) e a tentação é reaproveitá-lo. Não dá,
e o motivo é mais forte do que "são dimensões diferentes":

**o status da cozinha é movido pelas colunas do KDS, que cada restaurante
configura como quiser.** Um restaurante monta "A fazer / Em preparo / Montagem /
Pronto"; outro monta três colunas; outro, oito. A trajetória muda de loja para
loja — e de alguém arrastar um cartão. Amarrar dinheiro nisso faria o fechamento
da conta depender de configuração de tela de cozinha.

E o que já bastaria sozinho: um item pode estar `delivered` — o prato está na
mesa — e continuar **aberto**, porque ninguém pagou. É o caso normal durante a
refeição inteira, não a exceção.

### As duas perguntas

| pergunta | como responder |
| --- | --- |
| **o que a comanda tem AGORA** | `open_items_of_command(id)` — estado aberto **e** no pedido atual/consolidação viva |
| **o que a comanda JÁ teve** | `history_items_of_command(id)` — sem filtro de estado |

`command.items` devolve o **histórico inteiro**, inclusive almoços de semanas
atrás. Nenhuma tela usa o atalho cru: a rota é `GET /commands/{id}/items/`
(`?history=1` para o histórico).

### O que fecha um item

- pagamento total (`close_order`, `register_payment`, `settle_merge_on_payment`);
- cancelamento do item e cortesia — **cancelar na cozinha é outra dimensão**,
  mas um item cancelado precisa sair da comanda também, senão ele fica ocupando
  o cartão para o próximo cliente;
- cancelamento do pedido inteiro.

## Os serviços

| arquivo | o que faz |
| --- | --- |
| `orders/merge_locks.py` | ordem de lock (sempre por UUID) e as consultas de "está em fechamento?" |
| `orders/merge_services.py` | abrir, incluir comanda, retirar comanda, resumo |
| `orders/merge_confirm.py` | **confirmar** e desfazer |
| `orders/merge_settlement.py` | a quitação: fecha itens e libera todas as comandas |
| `orders/merge_refund.py` | **estorno auditado** da venda já paga |
| `orders/merge_expiry.py` | expiração da consolidação abandonada |
| `orders/command_items.py` | abrir/fechar item na comanda |
| `printers/command_receipt.py` | a conferência de UMA comanda, inclusive após o merge |

### `confirm_merge` — a operação que importa

Inteira numa transação:

1. trava destino, origens e comandas, **na ordem do UUID** (dois caixas fechando
   a mesma mesa travam os mesmos pedidos; ordem diferente = deadlock);
2. recusa origem paga, cancelada, com nota ou já consolidada;
3. congela o valor de cada origem **sem zerar desconto ou taxa manual**;
4. guarda o snapshot em `OrderMergeSource`;
5. move `OrderItem.order` para o destino, gravando `origin_order`;
6. marca a origem como `merged` e zera os totais dela (o relatório soma pedidos:
   deixá-los contaria a mesma venda duas vezes);
7. confere `target.total == soma(source.total)` centavo a centavo.

### A taxa é a SOMA das taxas, nunca um percentual novo

Dois pedidos de R$ 10,05 com 10%:

```
10% de 10,05 = 1,005 → 1,01 em CADA comanda → soma 2,02   ✅
10% de 20,10 =                                      2,01   ❌
```

O centavo some, e some sempre do mesmo lado. Por isso o destino recebe
`service_fee_percent = None` (taxa fixada, como uma digitada pelo gerente) e o
valor somado — nenhum recálculo posterior pode reaplicar percentual sobre o
agregado.

### `settle_merge_on_payment` — sem ela, os cartões ficam presos

`register_payment` sabe liberar UMA comanda: `free_command_for_order(order)` lê
`order.command_id`. O destino não tem comanda nenhuma, então essa linha é um
no-op nele. Sem o serviço de quitação, a venda ficaria paga e os quatro cartões
da família ocupados para sempre.

Ele roda **dentro da transação do pagamento**. Liberar num segundo commit criaria
a janela "pago mas preso", que só aparece quando a máquina cai no meio.

A liberação é **por origem**, com a mesa da comanda dela: comandas de mesas
diferentes podem estar na mesma conta, e usar `Order.table` do destino trataria
todas como se fossem da mesma mesa.

## O que ficou bloqueado, e por quê

| ação | resposta | motivo |
| --- | --- | --- |
| lançar item na origem | 409 | **o pior defeito possível**: a comida sai e ninguém cobra |
| fechar/pagar a origem por fora | 409 | a mesma comanda cobrada duas vezes |
| cancelar a origem | 409 | tiraria itens da tela que o caixa está lendo ao cliente |
| `/open-command/` da comanda | 409 "em fechamento" | antes vinha "comanda ocupada", genérico |
| `PATCH status` num pedido `merged` | 400 | reverter ressuscitaria uma venda já cobrada |
| cancelar recebimento de conta agrupada quitada | 400 | reabriria um cartão só; o caminho é `/refund/` |

`Order.is_locked` passou a reconhecer `merged`. "Em fechamento" é **derivado**,
nunca um terceiro estado no banco — um estado a mais seria mais uma coisa a
sincronizar e a divergir.

O cancelamento de um recebimento **parcial** continua permitido: é assim que o
caixa corrige a conta antes de desmembrá-la.

## Cozinha e KDS: a produção lê a ORIGEM

O lote de cozinha **fica no pedido de origem**. Ele registra "o que foi mandado
para a cozinha naquela rodada", e isso aconteceu no pedido da comanda mesmo.
Mover o lote exigiria renumerar `batch_number` e reescreveria o passado.

Consequência: depois do merge, `item.order != item.batch.order`. Tudo que
mostra ou roteia produção passou a ler `item.command` e `item.origin_order`:

- `serialize_kitchen_item` (evento em tempo real) — sem isso, o card do KDS
  mostraria a comanda errada, e item de quatro pessoas apareceria como de uma;
- `OrderItemSerializer.order_command_code` / `order_table_number`;
- `kitchen/rules.py::_context` — `has_command`/`has_table` viriam da origem;
  senão uma regra como "atrasa se for comanda" viraria "é balcão" no instante em
  que o caixa começa a fechar a conta;
- `printers/services.py::production_context` e o cupom de cancelamento.

### Os dois defeitos que isso conserta

**1. O cancelamento não imprimia.** `register_kitchen_item_cancellation_jobs`
procurava o ticket original por `PrintJob.order=item.order`. Depois do merge o
item aponta ao destino e o papel, à origem: a busca não achava nada, em silêncio
— e a cozinha montava o prato. Agora a busca cobre os dois pedidos.

**2. A rodada agendada não baixava estoque.** `dispatch_kitchen_batch` chamava
`deduct_order_stock(order=batch.order)`, e depois do merge esse pedido está
vazio. `deduct_order_stock` ganhou `items=` e o despacho passa `batch.items`: a
baixa é do **lote**, não do pedido.

O KDS também deixou de listar origens `merged` vazias como pedidos de cozinha, e
o despacho avança o `production_status` do destino junto com o da origem.

## A balança pesa para a COMANDA

Hoje a balança com `auto_print` e sem pedido amarrado **cria um pedido de balcão
sozinha** e já o marca `awaiting_payment`. Funciona para balcão; não funciona
para quem vai pesar o prato, sentar, pedir bebida e pagar na saída.

```
cartão lido ──► balança amarra a comanda ──► prato estabiliza
                                              │
                        item por kg no pedido de trabalho da comanda,
                        com `item.command` gravado
                                              │
                        nota de pesagem: comanda, peso, preço/kg e valor
```

`Scale.weighing_mode` é **explícito** (`counter` | `command`), não adivinhado
pelo que estiver preenchido. No modo comanda ela **falha fechado**: sem cartão
válido não há cobrança nem queda para balcão, e a leitura é gravada com
`ScaleReading.notes` dizendo por quê.

### O risco, e ele é de dinheiro

Se a balança continuar amarrada depois da pesagem, o prato do próximo cliente
cai na comanda do anterior: a pessoa vai embora, outra chega, põe o prato sem
passar o cartão — e paga o almoço de um estranho.

Por isso o vínculo **expira na primeira pesagem E por tempo** (60s por padrão),
o que vier antes. `consume_command_binding` pega e solta na mesma transação, sob
lock: uma leitura estável repetida (a balança manda a mesma leitura enquanto o
peso não muda) não lança dois itens.

E a nota de pesagem imprime o **número da comanda** junto do peso e do preço/kg.
É a única barreira que não depende de o operador lembrar de nada.

### Endpoints

```
POST /api/v1/scales/{id}/bind-command/     {"command": "<código lido>"}
POST /api/v1/scales/{id}/release-command/
```

## API

```text
POST   /api/v1/orders/{id}/merge/                 abre com {id} como 1ª origem
POST   /api/v1/orders/merges/{id}/commands/       inclui por código/número/id
DELETE /api/v1/orders/merges/{id}/commands/{cid}/ retira (só antes de confirmar)
GET    /api/v1/orders/merges/{id}/                comandas, itens e total
POST   /api/v1/orders/merges/{id}/confirm/        consolida (Idempotency-Key)
POST   /api/v1/orders/merges/{id}/cancel/         desfaz (antes de pagar)
POST   /api/v1/orders/merges/{id}/refund/         estorna (depois de pagar)
GET    /api/v1/commands/{id}/items/               o que a comanda tem (?history=1)
POST   /api/v1/commands/{id}/receipt/             conferência da comanda (não fiscal)
```

Depois de `confirm`, o recebimento é a rota do destino: `POST /orders/{id}/pay/`.

**400 é entrada inválida, 403 é acesso, 409 é conflito de estado** — e o
conflito aqui é o caso normal, não a exceção: dois caixas lendo o mesmo cartão é
o que acontece numa fila de sábado. Um 409 devolvido como 400 faz o PDV tratar
corrida como erro de digitação e reenviar o mesmo corpo para sempre.

Toda resposta traz o **resumo inteiro** (comandas, itens e total), não só o
registro alterado: a lista que o caixa lê em voz alta para o cliente não pode
ser montada de pedaços de respostas diferentes.

### Permissão

Código novo `orders.merge`, concedido a **caixa → gerente → admin**. O garçom
fica de fora: ele lança pelo aplicativo e não fecha conta de ninguém.

## As interfaces

### Web (`frontend/`)

| arquivo | papel |
| --- | --- |
| `services/orderMergeService.js` | as seis chamadas |
| `composables/useOrderMerge.js` | estado, agrupamento por comanda, idempotência |
| `components/pdv/CommandScannerInput.vue` | o campo do leitor |
| `components/pdv/MergeCommandGroup.vue` | os itens de UMA comanda |
| `views/PdvMergeView.vue` | a tela, em `/pdv/conta-agrupada` |

Rota própria, e não uma aba dentro de `PdvView.vue`: aquele arquivo tem 2800
linhas e a conta agrupada tem ciclo de vida próprio.

**A chave de idempotência nasce ao abrir a conta, não ao clicar.** Um clique
duplo em "Confirmar" reenvia a MESMA chave, e o servidor devolve a consolidação
que já existe em vez de montar outra.

### Desktop (`pdv_desktop/`)

| arquivo | papel |
| --- | --- |
| `features/orders/data/order_merge_repository.dart` | chamadas + `groupMergeItems` |
| `features/orders/presentation/order_merge_panels.dart` | leitor, aviso, lista, resumo |
| `features/orders/presentation/order_merge_dialog.dart` | o diálogo |

Entra por **um ponto só**: o botão "Juntar comandas" no `OrderCartPanel`, ligado
a `_mergeCommands()` em `home_page_order.dart`. Confirmada a conta, a tela troca
para o pedido de destino e segue para o pagamento de sempre.

Foi construído assim de propósito: o desktop está em redesenho, e um arquivo
novo com um único ponto de encaixe não colide com ele.

### Mobile (`pdv_mobile/`)

O garçom **não fecha conta**. O aplicativo só precisa não atrapalhar:

- `ClosingMergeBanner` avisa que a comanda está em fechamento;
- os botões de lançar, enviar e receber saem — tocar num deles diz por quê,
  porque um botão que não responde parece aparelho travado;
- a comanda aparece apagada no seletor, com "em fechamento no caixa".

O aviso precisa chegar **antes** de o garçom escolher o produto, não depois de o
servidor recusar.

## Sincronização

Nada disto está pronto enquanto os dados novos não sincronizarem. É o passo mais
fácil de esquecer porque a tela já funciona sem ele — o defeito só aparece na
loja, dias depois, como "sumiu".

| o que | decisão |
| --- | --- |
| `orders.OrderMerge` | `local_to_cloud`, política LOJA, depende de `order`, `seed_to_local` |
| `orders.OrderMergeSource` | idem, depende de `order_merge`, `order` e `command` |
| `Order.status=merged` | já viaja (é só um valor a mais) |
| `OrderItem.command` | dependência `command` acrescentada ao `order_item` |
| `OrderItem.origin_order` | usa a dependência `order`, já declarada |
| `Scale.active_command` e prazo | **não viajam** (`exclude_fields`) |
| `Scale.weighing_mode` | viaja: é configuração |

O cartão encostado na balança é estado local e efêmero. Sincronizá-lo deixaria o
sync **ressuscitar na loja o cartão de um cliente que já foi embora**.

### `essential_filter_any`: o OU que faltava

`essential_filter` é um `dict`, e um dict só sabe dizer **E**. A conta agrupada
precisa de **OU**: o pedido de origem fica em `merged`, que não está em
`ABERTOS`, mas ele precisa descer mesmo assim — o item do destino aponta para
ele por `origin_order`, e a FK ficaria sem alvo na loja nova, em retentativa
eterna.

Incluir `merged` globalmente em `ABERTOS` carregaria o histórico inteiro. Por
isso a entrada ganhou `essential_filter_any`, e o filtro desce só o que participa
de uma consolidação **viva**:

```python
ORIGENS_VIVAS = {"merge_participations__merge__status__in": ["open", "confirmed"],
                 "merge_participations__active": True}
```

### Ordem de carga

`order_merge` depende de `order` (o destino); `order_merge_source` depende das
três. **Errar a ordem não quebra teste nenhum** — quebra a carga inicial de uma
loja nova, com "ainda não existe aqui" em retentativa eterna. Há um teste só
para isso em `test_conta_agrupada_sincroniza.py`.

### Eventos em lote

O merge muda `OrderItem.order` de muitos itens de uma vez. `QuerySet.update` não
dispara os signals de tempo real, então `merge_confirm._broadcast` publica um
evento de **coleção** (`orders.order`, `orders.orderitem`,
`restaurants.command`) para desktop, web e garçom recarregarem — senão o garçom
lançaria numa comanda que já está sendo paga.

## A migração que não pode ser esquecida

`0010_backfill_item_command_status` faz duas coisas que o `default` do campo não
resolve:

1. **`command`** — copia a comanda do pedido para os itens já lançados. Sem
   isso, "ver detalhes da comanda 13" devolve vazio para tudo que aconteceu
   antes desta entrega.
2. **`command_status`** — fecha os itens de pedidos já pagos, estornados ou
   cancelados, e os itens `cancelled`/`comped`. **Sem o backfill, a comanda
   reutilizada reaparece cheia com o almoço de semanas atrás**: o caixa abre a
   comanda 13 e vê a conta de outro cliente.

A data de fechamento usa o que existir de confiável (`voided_at`, `closed_at`,
`cancelled_at`); sem horário confiável, fica nula — inventar um carimbo seria
pior que não ter nenhum.

A migração usa **literais**, não `Order.STATUS_PAID`: o model histórico que
`apps.get_model` devolve tem só os campos, nunca os atributos de classe.

### A validação campo a campo

`sync_check_registry` reprova um **model** sem decisão. Ele não diz nada sobre
um **campo** novo: um campo barrado pelo filtro global de segredos, ou posto em
`exclude_fields` sem querer, simplesmente não viaja — e o sintoma aparece na
loja dias depois, como "sumiu".

Três arquivos fecham essa porta, e eles medem em vez de supor:

| arquivo | o que prova |
| --- | --- |
| `test_conta_agrupada_campos_sincronizam.py` | monta o payload REAL e confere presença/ausência de cada campo novo |
| `test_conta_agrupada_roundtrip.py` | serializa na loja, apaga a linha, aplica como a nuvem e relê o que chegou |
| `test_estorno_agrupado_sincroniza.py` | as cinco tabelas que o estorno toca têm decisão |
| `test_movimento_de_caixa_sincroniza.py` | as transições do movimento de caixa chegam, e o saldo bate |

O round-trip **apaga o lado da loja antes de aplicar**. Sem isso o teste roda
num banco só, a linha já existe na mesma versão, a resolução de conflito manda
IGNORAR — e o teste passaria sem ter transportado nada.

### O defeito que essa validação achou

`ScaleReading.notes` (o motivo de uma pesagem não ter virado item) era gravado
num **segundo** `save()`, depois do INSERT. Mas `scale_reading` é
`immutable=True`: o destino insere e **nunca** atualiza. O evento de UPDATE era
descartado na nuvem, e a leitura ficava lá com o motivo em branco — para
sempre. Quem fosse investigar "por que o prato deste cliente não foi cobrado?"
não acharia resposta exatamente onde a pergunta é feita.

A correção move a decisão para antes do INSERT (`command_mode_refusal`), e o
teste observa os `save()` de verdade: a nota precisa estar presente já na
gravação em que a linha nasce. As falhas que só aparecem ao lançar o item
(impressora inativa, comanda em fechamento) não cabem no INSERT — essas vão
também para o `AuditLog`, que é append-only e sobe.

### O segundo defeito: o caixa da nuvem não fechava com o da loja

A validação campo a campo levou a um defeito **maior e mais antigo** que a
conta agrupada.

`cash_movement` estava declarado `immutable=True`, com o comentário "movimento
é imutável: a loja insere e nunca reescreve". A frase descreve um livro-razão.
**O model não é um** — ele tem ciclo de vida:

```
pending  ──(o gerente aprova a sangria)──►  approved
approved ──(o recebimento é cancelado)───►  cancelled
```

Com `immutable`, o destino insere e nunca atualiza: as duas setas morriam na
chegada. E o saldo é `Sum(amount)` sobre `status="approved"`, então o efeito
era aritmético — **a nuvem fechava o turno com um valor diferente do da loja,
sempre para o mesmo lado**:

| o que acontecia na loja | o que a nuvem via | efeito no saldo da nuvem |
| --- | --- | --- |
| gerente aprova a sangria de R$ 40 | sangria segue `pending` | R$ 40 **a mais** |
| recebimento em dinheiro é cancelado | venda segue `approved` | o valor da venda **a mais** |
| sessão liberada à força pelo admin | movimentos seguem `approved` | idem |

Uma sangria aprovada acontece todo dia. O defeito não era do estorno agrupado —
`cancel_payment` já fazia igual —, mas o estorno o herdava.

**A correção tem duas partes, e as duas eram necessárias:**

1. **`cash_movement` deixou de ser `immutable`.** O que protege contra
   reescrita não é o flag, é a ordem de versão: `conflicts.decide` IGNORA um
   evento cuja versão seja anterior à local, e a entidade é de mão única
   (`local_to_cloud`), então a nuvem nunca empurra nada para baixo. Há teste
   para o evento atrasado que tenta ressuscitar um movimento cancelado.
2. **O cancelamento deixou de usar `QuerySet.update()`.** A atualização em
   massa não dispara `post_save`, e sem o signal a sincronização não registra
   evento nenhum (ver o docstring de `synchronization/signals.py`) — o flag
   sozinho não teria resolvido. `cancel_cash_movements_of` grava linha a
   linha, e `cancel_payment` e o estorno agrupado usam o **mesmo** serviço: uma
   segunda cópia da linha é como um dos dois deixaria de chegar à nuvem no dia
   em que o outro fosse corrigido.

`test_movimento_de_caixa_sincroniza.py` mede as duas setas de ponta a ponta,
inclusive o saldo em reais: gaveta com venda +100 e sangria −40 aprovada tem de
fechar 60 dos dois lados. Devolvendo `immutable=True` ao catálogo, os cinco
testes falham.

## Como conferir que funcionou

```
python manage.py sync_check_registry    # nenhum model nem M2M sem decisão
python manage.py sync_status            # fila drenando
```

E o teste de verdade, na loja: abrir uma consolidação, pagar, e confirmar na
nuvem que chegaram o `OrderMerge`, os `OrderMergeSource`, os itens com `command`
preenchido e os pedidos de origem em `merged`. Sem isso, o relatório da nuvem
vai contar a venda errado — ou não vai contar.

## Estorno auditado: cancele tudo e esvazie as comandas

Desfazer uma conta **já paga** não é cancelar um recebimento. É desmontar uma
venda que passou por caixa, estoque, nota fiscal e quatro cartões que já
voltaram para a gaveta. `cancel_payment` sabe reabrir UM `order.command` e
estornar estoque de UM pedido — por isso ele recusa esta venda e manda para
`refund_merged_sale`.

O que o estorno faz, numa transação:

1. cancela os recebimentos do destino e os movimentos de caixa deles;
2. cancela a NFC-e — e **não** derruba o estorno se a SEFAZ recusar por prazo:
   a pendência volta no relatório, para resolver no portal. Prender o dinheiro
   do cliente a uma decisão da SEFAZ é pior do que registrar o que ficou;
3. devolve o estoque (`revert_order_stock`, a mesma soma que `cancel_payment`
   usa — duas cópias divergem no dia em que uma ganha um caso novo);
4. cancela os itens **onde eles estão**, no destino: movê-los de volta
   reescreveria a produção que já aconteceu, e a nota autorizada precisa
   continuar batendo com o que foi vendido;
5. tira as origens de `merged` e as põe em `cancelled`;
6. **esvazia todas as comandas** — e, se o cartão já foi reentregue, **cancela
   o pedido do novo cliente junto**.

O passo 6 é a decisão do usuário, e ela tem um custo real: o que o próximo
cliente já consumiu naquele cartão vai junto. Por isso o estorno exige gerente,
exige motivo, e registra o número de cada pedido descartado
(`reused_orders_discarded`) — alguém vai perguntar por ele depois.

**A única recusa que sobrou** é a que não dá para desfazer sozinha: um pedido
novo que já tem recebimento **aprovado**. Descartá-lo deixaria um pagamento
órfão, com o dinheiro de outra pessoa dentro, apontando para um pedido
cancelado. Esse caso para e pede decisão — e a transação inteira volta atrás,
sem desfazer nada pela metade.

O vínculo `OrderMergeSource` **não é apagado**: ele fica inativo. É ele que
responde, semanas depois, quais comandas aquela venda estornada tinha.

## Expiração da consolidação abandonada

O caixa começa a montar a conta da mesa 7, o cliente muda de ideia, e ele sai
da tela. A consolidação fica `open`, e enquanto ela existir as quatro comandas
recusam lançamento, pagamento e reabertura — o salão trava por um gesto que
ninguém completou.

`expire_abandoned_merges` cancela o que está **seguramente** abandonado:

- status `open`. Uma `confirmed` **nunca** expira, mesmo velha: os itens já
  estão no pedido final e o cliente pode estar na fila do caixa;
- parada há mais de `DEFAULT_IDLE_MINUTES` (30). O relógio corre sobre
  `updated_at`, e incluir mais uma comanda o reinicia — mexer na conta é sinal
  de que alguém ainda está ali;
- sem nenhum recebimento aprovado no destino. Isso não deveria existir numa
  conta `open`; se existir, alguém pagou por uma porta que não conhecemos, e
  expirar apagaria a única pista disso — então ela é pulada e auditada.

Cada consolidação é uma transação própria, e o estado é relido **depois** do
lock: entre a consulta que listou os candidatos e o lock, o caixa pode ter
voltado e confirmado a conta.

Três caminhos a acionam, porque uma loja pode não ter Celery:

```
orders.expire_abandoned_merges          # tarefa periódica, a cada 60s
GET /api/v1/orders/merges/              # varredura de leitura
manage.py expire_order_merges [--dry-run]   # à mão, para destravar agora
```

E há um quarto, que é o que mais importa: **`/open-command/` tenta expirar
antes de recusar**. É ali que o operador esbarra no problema, e mandá-lo
esperar a varredura seria travar o salão por meia hora.

## Recibo por comanda depois do merge

O recibo comum sai do pedido. Depois da consolidação o pedido de origem fica sem
itens: mandar imprimi-lo produziria um papel em branco com total zerado —
exatamente quando o cliente pede "me dá a conta da comanda 13" para conferir o
que consumiu dentro de uma conta de quatro pessoas.

`printers/command_receipt.py` não parte do pedido: parte de `OrderItem.command`,
que é um fato gravado no lançamento e que o merge nunca muda. O papel traz:

- os itens **daquela** comanda, com peso e preço/kg quando for por quilo;
- subtotal, taxa (a da comanda, do snapshot quando já consolidada) e total;
- um aviso de que ela faz parte de uma **conta agrupada** — sem ele, o cliente
  vai ao caixa achando que paga só aquele total;
- **"NÃO É DOCUMENTO FISCAL"** em duas linhas. A NFC-e é uma só, do pedido
  consolidado; confundir os dois faria alguém entregar quatro "notas" de uma
  venda que teve uma.

O job é `TYPE_TABLE_BILL` — o documento de conferência que já existia —, nunca
`TYPE_RECEIPT`: aquele é o comprovante da venda, e uma comanda dentro de uma
conta agrupada não tem venda própria.

## O que esta entrega NÃO faz

- **Cozinha automática** (item sair para a produção sem clicar em "enviar"):
  mudança separada, como o plano previa.
- **Estorno parcial** de uma conta agrupada (devolver só uma comanda). O
  estorno é da venda inteira; para tirar uma comanda antes de pagar, o caminho
  continua sendo desfazer e remontar.

## Testes

| arquivo | o que cobre |
| --- | --- |
| `orders/tests/test_order_merge_confirm.py` | consolidação, taxa somada, bloqueio, idempotência, desfazer |
| `orders/tests/test_order_merge_payment.py` | liberação de todos os cartões, mesa, estorno |
| `orders/tests/test_order_merge_kitchen.py` | KDS, ticket, cancelamento e estoque do lote após o merge |
| `orders/tests/test_order_merge_api.py` | rotas, 409 vs 400, permissão do garçom |
| `orders/tests/test_command_items_view.py` | o que a comanda tem × o que ela já teve |
| `orders/tests/test_order_merge_refund.py` | estorno: caixa, estoque, cartões e o pedido reentregue descartado |
| `orders/tests/test_order_merge_expiry.py` | expiração, relógio reiniciado, comando de gestão |
| `orders/tests/test_command_receipt.py` | conferência por comanda antes e depois do merge |
| `orders/tests/test_command_backfill_migration.py` | a migração 0010 |
| `printers/tests/test_scale_command_weighing.py` | balança por comanda, falha fechado, expiração |
| `synchronization/tests/test_conta_agrupada_sincroniza.py` | catálogo, ordem de carga, filtro OU |
| `frontend/src/composables/useOrderMerge.test.js` | agrupamento, idempotência, conflito |
| `frontend/src/components/pdv/CommandScannerInput.test.js` | o leitor devolve o foco |
| `pdv_desktop/test/features/orders/order_merge_repository_test.dart` | agrupamento por comanda |
| `pdv_mobile/test/closing_merge_banner_test.dart` | origem × destino |
