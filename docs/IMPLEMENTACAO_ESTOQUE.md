# Implementação do Estoque

> Especificação funcional e técnica para evolução do estoque do StarChef.
>
> Este documento descreve a implementação proposta. A existência de um item
> neste documento não significa que ele já esteja implementado.

## 1. Objetivo

Evoluir o estoque atual para um controle de insumos adaptável a restaurantes,
com:

- cadastro central de insumos;
- estoque mínimo por insumo;
- entradas e saídas manuais agrupadas;
- lotes, datas de entrada e validade;
- impressão de etiquetas após a entrada;
- saída assistida por leitura de etiqueta;
- escolha automática de lotes por um único critério configurado: validade mais
  próxima ou entrada mais antiga;
- baixa automática na venda de produtos com receita;
- consumo de insumos usados como adicionais;
- preparação de receitas orientada pelos lotes que devem ser usados;
- controle quantitativo ou estimado por duração;
- histórico completo de entradas, saídas, perdas, ajustes e reversões;
- relatórios de saldo, estoque mínimo e validade.

O desenho deve reutilizar os módulos existentes de cardápio, pedidos, estoque,
impressão, auditoria, multi-tenancy e operação offline do PDV.

## 2. Princípios do domínio

O sistema deve separar claramente três conceitos:

1. **Produto** é aquilo que pode ser vendido no PDV.
2. **Insumo** é aquilo que existe fisicamente no estoque.
3. **Receita e adicional** determinam como os insumos são consumidos.

Exemplos:

| Conceito | Exemplo | Controla saldo físico? |
| --- | --- | --- |
| Produto | X-Salada | Não diretamente, salvo vínculo com um insumo |
| Insumo | Queijo muçarela | Sim |
| Receita | X-Salada usa 30 g de queijo | Não; gera o consumo do insumo |
| Adicional | Queijo extra por R$ 4,00 | Não; consome o insumo vinculado |
| Lote | Queijo recebido em 30/08, validade 08/09 | Sim |

O saldo não deve ser alterado diretamente. Toda alteração deve gerar uma
movimentação auditável.

## 3. O que já existe e será reutilizado

O StarChef já possui:

- `menu.Ingredient`, que será apresentado como **Insumo**;
- `menu.Recipe` e `menu.RecipeItem` para fichas técnicas;
- `menu.ProductAddon` e seu vínculo com produtos;
- `stock.StockLocation` para locais físicos;
- `stock.StockMovement` para movimentações;
- baixa de receita no pagamento ou envio para cozinha;
- `printers.Printer` e `printers.PrintJob`;
- agente local Flutter para entrega física de impressões;
- QR Code e Code 128 no transporte ESC/POS;
- auditoria, idempotência, multi-tenancy e sincronização offline-first.

Essas estruturas devem ser evoluídas sem criar um segundo estoque paralelo.

## 4. Limitações que precisam ser corrigidas

Antes de ampliar o estoque, o motor atual precisa corrigir os seguintes pontos:

- a baixa percorre o pedido inteiro e pode ser chamada mais de uma vez;
- a baixa não considera os adicionais selecionados;
- o rendimento da receita não é considerado no consumo;
- a unidade do item da receita não é convertida para a unidade do insumo;
- não existe escolha de lote pela validade mais próxima ou pela entrada mais
  antiga;
- não existe reversão de estoque ligada ao cancelamento ou estorno;
- a composição usada não é congelada, permitindo que uma alteração posterior
  na receita mude retroativamente a baixa de uma venda;
- produtos com `controls_stock` sem receita não possuem um vínculo operacional
  com um insumo;
- o custo médio atual precisa ser recalculado sem contar a nova entrada duas
  vezes;
- os testes do estoque atual são apenas básicos e não cobrem esses cenários.

Essas correções são pré-requisitos para que lotes e validades sejam confiáveis.

## 5. Configuração geral do estoque

Criar `StockSettings`, preferencialmente uma configuração por filial.

Campos propostos:

| Campo | Tipo | Regra |
| --- | --- | --- |
| `branch` | FK | Uma configuração ativa por filial |
| `default_location` | FK | Local padrão de entradas e baixas automáticas |
| `picking_strategy` | choice | `oldest_expiry` ou `oldest_entry` |
| `expiry_control_enabled` | boolean | Ativa o controle obrigatório de validade |
| `expiry_warning_days` | inteiro | Antecedência padrão dos alertas |
| `block_expired_stock` | boolean | Deve ser verdadeiro por padrão |
| `allow_negative_stock` | boolean | Deve ser falso por padrão |
| `require_label_scan_on_manual_exit` | boolean | Exige conferência do lote sugerido |
| `stock_deduction_timing` | choice | Pagamento ou envio para cozinha |
| `default_label_template` | FK | Modelo padrão de etiqueta |
| `default_label_printer` | FK | Impressora padrão de estoque |

### 5.1 Critério de escolha do lote

A configuração `picking_strategy` define **um único critério ativo**. Os dois
critérios não são aplicados ao mesmo tempo:

- **Validade mais próxima** (`oldest_expiry`, tecnicamente FEFO): utiliza
  primeiro o lote válido com a data de validade mais próxima;
- **Entrada mais antiga** (`oldest_entry`, tecnicamente FIFO): utiliza primeiro
  o lote com a data de entrada mais antiga.

O administrador escolhe qual dos dois comportamentos a filial utilizará. Ter o
controle de vencimento ativo não muda essa escolha automaticamente; ele apenas
torna a data de validade obrigatória e habilita bloqueios e relatórios de
vencimento.

Regras adicionais:

- lotes bloqueados, esgotados ou descartados não participam da seleção;
- lotes vencidos não podem ser sugeridos automaticamente;
- na prioridade por validade, lotes sem validade devem ficar depois dos lotes válidos com
  validade, salvo outra regra explícita no futuro;
- empates de validade são resolvidos pela data de entrada mais antiga;
- empates de entrada são resolvidos pela criação do lote e pelo UUID;
- uma saída pode consumir mais de um lote até completar a quantidade pedida.

### 5.2 Validade obrigatória

Quando `expiry_control_enabled` estiver ativo:

- `expires_at` será obrigatório em toda linha de entrada;
- a API recusará a confirmação da entrada se algum item não possuir validade;
- não bastará validar somente na interface;
- importações e operações offline deverão seguir a mesma regra;
- a validade não poderá ser anterior à data de entrada;
- lotes vencidos só poderão sair como perda, descarte ou ajuste autorizado.

Além disso, selecionar `oldest_expiry` como critério exige que
`expiry_control_enabled` esteja ativo. A API deve recusar uma configuração que
priorize validade enquanto o controle de vencimento estiver desativado.

Quando o controle estiver desativado, a validade continuará disponível, mas
será opcional.

## 6. Cadastro de insumos

O modelo técnico `Ingredient` pode permanecer com esse nome para evitar uma
migração desnecessária de tabela e API, mas toda a interface deverá usar o
termo **Insumo**.

Campos necessários:

| Campo | Descrição |
| --- | --- |
| `name` | Nome do insumo |
| `internal_code` | Código interno único na conta |
| `description` | Descrição opcional |
| `base_unit` | `unit`, `g` ou `ml` |
| `minimum_stock` | Estoque mínimo do insumo |
| `average_cost` | Custo médio calculado |
| `tracking_mode` | Quantidade ou duração estimada |
| `estimated_duration_value` | Valor da duração, quando aplicável |
| `estimated_duration_unit` | Hora, dia, semana ou mês |
| `is_active` | Situação cadastral |

### 6.1 Estoque mínimo

Todo insumo controlado deve possuir `minimum_stock` informado.

Regras:

- não pode ser negativo;
- é armazenado na unidade base do insumo;
- pode ser `0` para indicar que o cadastro não deseja alerta antecipado, mas o
  campo continua obrigatório;
- o alerta deve considerar o saldo disponível, descontando reservas quando
  elas forem implementadas;
- o relatório deve diferenciar saldo abaixo do mínimo, saldo zerado e saldo
  negativo.

Durante a migração, insumos existentes sem valor receberão `0`. Depois da
migração, a API passará a exigir o campo em novos cadastros e edições.

## 7. Unidades e conversões

As quantidades internas devem ser normalizadas:

- peso em gramas;
- volume em mililitros;
- itens discretos em unidades.

A interface pode continuar mostrando kg e litros.

Exemplo:

```text
Entrada: 2 pacotes de 5 kg
Conversão: 2 × 5.000 g
Quantidade em estoque: 10.000 g
Consumo da receita: 120 g
Saldo: 9.880 g
```

Cada item de entrada poderá informar:

- unidade de compra, como pacote, caixa, fardo, kg ou litro;
- quantidade de embalagens;
- conteúdo por embalagem;
- fator de conversão para a unidade base.

Conversões entre grandezas incompatíveis devem ser recusadas. Por exemplo, não
é possível converter litros em gramas sem uma conversão específica cadastrada.

## 8. Adicionais como consumo de insumos

`ProductAddon` continuará existindo como uma oferta comercial, preservando:

- nome mostrado no PDV;
- preço;
- setor de produção;
- vínculo com os produtos que permitem o adicional.

Ele passará a possuir:

- `ingredient`: insumo consumido;
- `consumption_quantity`: quantidade consumida por unidade vendida;
- opcionalmente uma unidade de apresentação, convertida para a unidade base.

Exemplo:

```text
Insumo: Bacon
Unidade base: g
Adicional: Bacon extra
Preço: R$ 4,00
Consumo: 30 g
```

Se a quantidade variar por produto, criar uma tabela intermediária
`ProductAddonAvailability` com:

- produto;
- adicional;
- quantidade de consumo padrão ou sobrescrita;
- preço padrão ou sobrescrito;
- situação.

Na migração, adicionais existentes poderão receber um novo insumo com o mesmo
nome. O operador deverá revisar unidade e quantidade antes de ativar a baixa.

## 9. Produtos vendidos diretamente

Produtos que representam uma unidade física, como refrigerante em lata, podem
ser vendidos sem receita e ainda assim baixar estoque.

Adicionar ao produto:

- `stock_ingredient`: insumo correspondente;
- `stock_consumption_quantity`: quantidade consumida por unidade vendida.

Exemplo:

```text
Produto: Refrigerante lata 350 ml
Insumo: Refrigerante lata 350 ml
Consumo por venda: 1 unidade
```

O tipo de produto `input` existente deve ser revisado. Não se deve usar
simultaneamente um produto do tipo insumo e um `Ingredient` independente para o
mesmo saldo físico.

## 10. Modelo de dados do estoque

### 10.1 `StockEntry`

Cabeçalho de uma entrada manual agrupada:

- conta, restaurante e filial;
- local de destino;
- fornecedor opcional;
- número de documento ou nota;
- data efetiva da entrada;
- observações;
- operador;
- situação: `draft`, `posted` ou `cancelled`;
- data e usuário da confirmação;
- data e usuário do cancelamento.

### 10.2 `StockEntryItem`

Cada entrada poderá conter vários insumos:

- entrada;
- insumo;
- quantidade comprada;
- unidade de compra;
- conteúdo por embalagem;
- quantidade convertida para unidade base;
- custo unitário e custo total;
- lote do fornecedor;
- data de fabricação opcional;
- data de validade;
- quantidade de etiquetas desejada;
- observação da linha.

Cada combinação de insumo, lote e validade deve ocupar uma linha distinta.

### 10.3 `StockLot`

Representa o lote físico disponível:

- insumo;
- local;
- item de entrada de origem;
- código interno imutável;
- lote do fornecedor;
- data da entrada;
- fabricação;
- validade;
- quantidade inicial;
- saldo atual ou saldo materializado;
- custo unitário;
- situação: disponível, esgotado, bloqueado, vencido ou descartado;
- data de abertura, para controles por duração.

O livro de movimentações continua sendo a fonte de verdade. Um saldo armazenado
no lote será uma materialização atualizada na mesma transação para melhorar a
consulta e o bloqueio concorrente.

### 10.4 `StockExit`

Cabeçalho de uma saída manual agrupada:

- conta, restaurante e filial;
- local de origem;
- data efetiva da saída;
- tipo: consumo manual, perda, descarte, transferência, uso interno ou outro;
- critério aplicado: validade mais próxima ou entrada mais antiga;
- motivo obrigatório;
- operador;
- situação: `draft`, `posted` ou `cancelled`;
- opção de conferência por leitura de etiqueta.

### 10.5 `StockExitItem`

- saída;
- insumo;
- quantidade solicitada;
- quantidade atendida;
- unidade base;
- observação;
- alocações de lotes sugeridas.

### 10.6 `StockAllocation`

Registra como uma entrada, saída, venda ou preparação foi distribuída entre
lotes:

- origem do consumo;
- lote;
- quantidade sugerida;
- quantidade confirmada;
- código de etiqueta conferido;
- usuário e data da conferência;
- indicação de substituição manual do lote sugerido;
- justificativa da substituição.

### 10.7 `StockMovement`

O modelo existente será ampliado e tratado como imutável:

- insumo;
- lote;
- local de origem e/ou destino;
- quantidade com sinal;
- custo unitário e total;
- tipo de movimento;
- entrada, saída, pedido, item de pedido ou preparação de origem;
- operador;
- data efetiva;
- motivo;
- movimento original, quando for reversão;
- chave idempotente da origem.

Tipos mínimos:

- entrada;
- saída manual;
- venda;
- preparação;
- adicional vendido;
- perda;
- vencimento/descarte;
- transferência de entrada e saída;
- inventário;
- ajuste;
- reversão.

## 11. Fluxo de entrada manual

1. O operador cria uma entrada em rascunho.
2. Escolhe filial, local, data e documento.
3. Adiciona vários insumos à lista.
4. Informa quantidade, embalagem, custo, lote e validade de cada linha.
5. O sistema valida conversões e a obrigatoriedade da validade.
6. O operador confirma a entrada.
7. Em uma transação única, o backend cria lotes e movimentos positivos.
8. A tela apresenta o resumo dos lotes criados.
9. O operador pode imprimir todas as etiquetas ou escolher linhas e cópias.

Uma entrada confirmada não poderá ser editada ou apagada. Seu cancelamento
deverá criar movimentos inversos. Se o lote já tiver sido consumido, o
cancelamento integral deverá ser recusado e o operador será orientado a fazer
um ajuste justificado.

## 12. Impressão de etiquetas na entrada

Após a confirmação da entrada, devem existir as ações:

- `Imprimir todas as etiquetas`;
- `Selecionar etiquetas`;
- `Reimprimir etiquetas`;
- escolher quantidade de cópias;
- escolher impressora e modelo, se o usuário tiver permissão.

Cada etiqueta identifica ao menos:

- nome do insumo;
- código interno do lote;
- lote do fornecedor, quando existir;
- data de entrada;
- data de validade, quando existir;
- quantidade ou embalagem;
- local de estoque;
- QR Code ou código de barras.

O código impresso deve apontar para o identificador imutável do lote. Não deve
usar somente o nome do insumo nem um número sequencial ambíguo.

## 13. Configuração de etiquetas

Criar `StockLabelTemplate` com:

- nome;
- largura e altura em milímetros;
- margens;
- orientação;
- espaço entre etiquetas;
- quantidade por linha, quando aplicável;
- tipo do código: QR Code ou Code 128;
- campos visíveis;
- tamanho de fonte;
- texto personalizado;
- impressora padrão;
- driver/formato: sistema, PDF/imagem, ESC/POS, ZPL ou TSPL;
- situação.

Criar um novo tipo de `PrintJob`: `stock_label`.

A fila e o agente local atuais podem ser reutilizados. Entretanto, impressão
com altura e largura exatas exige PDF/imagem pelo driver do sistema ou suporte
nativo a linguagens de impressora de etiquetas, como ZPL e TSPL. O fluxo atual
de texto ESC/POS é suficiente para QR Code e Code 128, mas não garante layouts
adesivos arbitrários.

## 14. Fluxo de saída manual

1. O operador cria uma saída em rascunho.
2. Escolhe o local e informa um motivo.
3. Adiciona um ou vários insumos e suas quantidades.
4. O backend executa exclusivamente o critério configurado: validade mais
   próxima ou entrada mais antiga.
5. O sistema apresenta os lotes escolhidos e as quantidades de cada um.
6. Se a conferência por etiqueta estiver ativa, a tela abre o modo de leitura.
7. O operador lê as etiquetas dos lotes indicados.
8. O sistema confirma que os códigos lidos correspondem aos lotes sugeridos.
9. Depois da conferência, a saída é confirmada e os movimentos negativos são
   criados de forma atômica.

A saída também poderá ser realizada sem leitor, quando a configuração e a
permissão permitirem. Nesse caso, o operador confirma manualmente os lotes
sugeridos.

### 14.1 Saída assistida por etiqueta

A opção `Conferir por leitura de etiqueta` deverá:

- exibir o insumo e a quantidade pendente;
- exibir qual lote deve ser retirado fisicamente;
- mostrar entrada, validade, saldo e código esperado;
- manter foco contínuo no campo do leitor;
- aceitar scanner serial/USB-CDC e digitação controlada;
- marcar cada alocação como conferida;
- impedir leitura duplicada indevida;
- alertar se a etiqueta estiver vencida, bloqueada, esgotada ou pertencer a
  outro local;
- impedir a confirmação enquanto faltar quantidade ou conferência obrigatória.

Se o operador ler um lote diferente do sugerido:

- o sistema deve mostrar qual lote deveria ser utilizado;
- a troca não deve ocorrer silenciosamente;
- um usuário autorizado poderá substituir a sugestão;
- a substituição exigirá justificativa e ficará na auditoria.

Na prioridade por entrada, a indicação usa o lote com entrada mais antiga. Na
prioridade por validade, usa o lote válido mais próximo do vencimento. Somente
um desses critérios é aplicado em cada filial.

## 15. Baixa automática por venda

Produtos vendidos com receita terão saída automática dos insumos.

Fórmula:

```text
consumo do insumo = quantidade na receita
                    ÷ rendimento da receita
                    × quantidade vendida
```

Exemplo:

```text
Receita rende 10 porções
Usa 1.000 g de macarrão
Venda de 3 porções
Baixa: 1.000 ÷ 10 × 3 = 300 g
```

O serviço de venda deverá:

1. Congelar um snapshot da composição usada.
2. Calcular o consumo considerando o rendimento.
3. Converter todas as unidades para a unidade base.
4. Incluir os adicionais selecionados.
5. Incluir produtos de venda direta vinculados a insumos.
6. Selecionar lotes usando exclusivamente o critério configurado.
7. Criar um movimento por lote consumido.
8. Usar uma chave única por item, componente e evento.
9. Impedir baixa duplicada.
10. Gerar reversões auditáveis quando a regra operacional determinar devolução.

O momento continuará configurável:

- no envio para cozinha; ou
- na confirmação do pagamento.

Para restaurantes, o envio para cozinha costuma representar melhor o consumo
real. Um item já preparado e depois cancelado normalmente deve virar perda ou
consumo, e não retornar silenciosamente ao estoque.

## 16. Preparação de receitas e indicação de uso

Criar uma ordem de preparação para responder à pergunta: **o que será
preparado?**

O operador informa:

- receita ou produto;
- quantidade de porções;
- local de origem;
- local de destino, quando houver produto preparado armazenável.

O sistema expande a receita e seleciona os lotes pelo critério configurado.

Exemplo:

```text
Preparar 20 porções de macarrão

Macarrão: 2.000 g
  Usar lote MAC-004 — entrada 20/08 — vence 02/09 — 1.200 g
  Usar lote MAC-007 — entrada 25/08 — vence 08/09 —   800 g

Molho: 1.500 ml
  Usar lote MOL-011 — entrada 22/08 — vence 01/09 — 1.500 ml
```

A preparação poderá usar o mesmo modo de conferência por etiqueta da saída
manual.

Receitas precisam declarar um modo:

- `consume_on_sale`: insumos são baixados conforme a venda;
- `consume_on_preparation`: insumos são baixados na preparação.

Uma receita de produção em lote não pode baixar os mesmos insumos novamente na
venda. Para produtos preparados armazenáveis, uma preparação poderá gerar um
lote de saída acabada, que será consumido posteriormente pelas vendas.

## 17. Controle por duração estimada

Alguns insumos não possuem medição constante confiável. Para esses casos,
`tracking_mode` poderá ser:

- `quantity`: controle exato por unidade, peso ou volume;
- `estimated_duration`: controle estimado por tempo.

No modo de duração, registrar:

- data e hora de abertura/ativação;
- duração prevista;
- previsão de término;
- data real de término ou substituição;
- operador responsável.

O sistema deverá apresentar esse resultado como **estimativa**, nunca como
saldo físico exato.

## 18. Histórico e auditoria

O histórico deve permitir filtrar por:

- período;
- filial e local;
- insumo;
- lote;
- tipo de movimento;
- entrada ou saída;
- pedido;
- preparação;
- operador;
- origem manual ou automática.

Movimentos confirmados não serão editados nem apagados. Correções serão feitas
com movimentos de reversão ou ajuste, sempre com motivo e usuário.

## 19. Tela de estoque

A área de logística deverá possuir:

1. **Visão geral**
   - saldo atual;
   - valor do estoque;
   - abaixo do mínimo;
   - zerado ou negativo;
   - vencido e próximo do vencimento.
2. **Insumos**
   - cadastro, unidade, estoque mínimo e modo de controle.
3. **Entradas**
   - rascunhos, confirmações, cancelamentos e etiquetas.
4. **Saídas**
   - saída manual, critério de separação e leitura de etiquetas.
5. **Lotes e validades**
   - saldo por lote, local, entrada e validade.
6. **Preparações**
   - planejamento, separação e confirmação de consumo.
7. **Movimentações**
   - livro completo e imutável.
8. **Relatórios**
   - validade, perdas, consumo e estoque mínimo.
9. **Configuração**
   - prioridade por validade ou entrada, validade, saldo negativo e etiquetas.

## 20. Relatórios

### 20.1 Validade

- vencidos;
- vencem hoje;
- vencem em até 3, 7, 15 ou 30 dias;
- lotes sem validade, quando permitidos;
- valor financeiro em risco;
- quantidade descartada por vencimento.

### 20.2 Estoque mínimo

- abaixo do mínimo;
- zerado;
- negativo;
- consumo médio;
- previsão de término;
- quantidade sugerida de reposição.

### 20.3 Movimentação e consumo

- entradas e saídas por período;
- consumo automático por venda;
- consumo por preparação;
- consumo de adicionais;
- perdas e ajustes;
- custo médio e CMV por produto.

## 21. API proposta

Rotas sugeridas:

```text
GET/PATCH  /api/v1/stock/settings/

GET/POST   /api/v1/stock/entries/
GET/PATCH  /api/v1/stock/entries/{id}/
POST       /api/v1/stock/entries/{id}/post/
POST       /api/v1/stock/entries/{id}/cancel/
POST       /api/v1/stock/entries/{id}/print-labels/

GET/POST   /api/v1/stock/exits/
GET/PATCH  /api/v1/stock/exits/{id}/
POST       /api/v1/stock/exits/{id}/suggest-lots/
POST       /api/v1/stock/exits/{id}/scan-label/
POST       /api/v1/stock/exits/{id}/post/
POST       /api/v1/stock/exits/{id}/cancel/

GET        /api/v1/stock/lots/
GET        /api/v1/stock/lots/lookup/?code=...
POST       /api/v1/stock/lots/{id}/block/
POST       /api/v1/stock/lots/{id}/unblock/

GET        /api/v1/stock/balances/
GET        /api/v1/stock/movements/
GET        /api/v1/stock/reports/expiry/
GET        /api/v1/stock/reports/minimum/

GET/POST   /api/v1/stock/preparations/
POST       /api/v1/stock/preparations/{id}/suggest-lots/
POST       /api/v1/stock/preparations/{id}/scan-label/
POST       /api/v1/stock/preparations/{id}/confirm/

GET/POST   /api/v1/stock/label-templates/
```

As ações de confirmação devem aceitar `Idempotency-Key` e executar dentro de
`transaction.atomic` com bloqueio dos lotes envolvidos.

## 22. Concorrência e integridade

Ao confirmar uma saída, venda ou preparação:

1. bloquear os lotes candidatos com `select_for_update`;
2. recalcular o saldo dentro da transação;
3. reaplicar o único critério de separação configurado;
4. validar validade e situação;
5. impedir saldo negativo, salvo configuração explícita;
6. criar alocações e movimentos;
7. atualizar o saldo materializado;
8. confirmar a origem;
9. liberar a transação.

Restrições importantes:

- uma linha de consumo não pode ser aplicada duas vezes;
- uma reversão só pode referenciar um movimento existente;
- a soma das alocações deve ser igual à quantidade atendida;
- um lote e seu insumo/local devem pertencer à mesma conta e filial da
  operação;
- etiquetas devem identificar apenas um lote;
- entradas e saídas confirmadas devem ser imutáveis.

## 23. Offline e PDV Flutter

Atualmente o catálogo local do PDV não sincroniza insumos, receitas, lotes ou
movimentações. Para suportar baixa e leitura de etiquetas offline, incluir no
SQLite somente os dados operacionais necessários:

- insumos ativos;
- receitas e composições vigentes;
- vínculos de adicionais;
- configuração do critério de separação e do controle de validade;
- lotes disponíveis com saldo;
- modelos e impressoras de etiqueta necessários;
- operações pendentes de consumo.

O histórico completo não deverá fazer parte da carga inicial. Ele será
consultado sob demanda no backend.

Na topologia principal/secundário:

- o Caixa Principal mantém a cópia operacional e sincroniza com a nuvem;
- o secundário encaminha a operação ao principal;
- operações offline usam chaves idempotentes;
- conflitos de saldo devem gerar revisão, nunca uma segunda baixa silenciosa.

A tela administrativa de entrada pode começar online na retaguarda web. A
operação offline de estoque deve ser adicionada ao Flutter em uma etapa própria
depois que o motor transacional do backend estiver estável.

## 24. Permissões

O código atual `stock.manage` é amplo demais. Separar, mantendo compatibilidade:

- `stock.view`;
- `stock.entry.create`;
- `stock.entry.post`;
- `stock.exit.create`;
- `stock.exit.post`;
- `stock.adjust`;
- `stock.override-picking`;
- `stock.label.print`;
- `stock.reports.view`;
- `stock.settings.manage`.

Alterar um lote sugerido, permitir vencido, gerar ajuste ou reverter movimento
deve exigir permissão específica e justificativa.

## 25. Migração dos dados existentes

Ordem proposta:

1. Criar configurações, entradas, saídas, lotes, alocações e etiquetas.
2. Adicionar novos campos de insumo, produto, adicional e receita como
   opcionais.
3. Preencher `minimum_stock=0` nos insumos antigos sem valor.
4. Normalizar unidades compatíveis.
5. Criar um lote inicial por combinação de insumo e local com saldo existente.
6. Marcar esse lote como originado da migração/inventário inicial.
7. Criar insumos correspondentes aos adicionais antigos.
8. Exigir revisão da quantidade de consumo antes de ativar a baixa do adicional.
9. Vincular produtos diretos aos insumos quando aplicável.
10. Ativar as novas validações de obrigatoriedade.
11. Manter IDs e endpoints antigos enquanto frontend e Flutter são atualizados.

Não se deve inventar validade para estoque legado. Se a filial ativar validade
obrigatória, os lotes migrados sem validade deverão ficar em revisão ou exigir
um inventário assistido antes de serem liberados para consumo.

## 26. Etapas de implementação

### Fase 0 — Correção do motor atual — **implementada**

- rendimento da receita — `_recipe_components` divide o consumo pelo
  `yield_quantity` antes de multiplicar pela quantidade vendida;
- conversões de unidade — `apps/menu/units.py`; grandezas incompatíveis são
  recusadas no cadastro (serializers) e ignoradas na venda, para não travar um
  fechamento por causa de cadastro torto;
- custo médio — `update_ingredient_average_cost` desconta a entrada já gravada
  antes de ponderar, e consulta com filtro de conta explícito;
- idempotência por item — `StockMovement.source_key`
  (`sale:{item}:{componente}:{id}`) com constraint única por conta;
- adicionais — `ProductAddon.ingredient` / `consumption_quantity` /
  `consumption_unit`;
- produtos diretos — `Product.stock_ingredient` /
  `stock_consumption_quantity` / `stock_consumption_unit`; ignorados quando o
  produto tem ficha técnica ativa, para não baixar o mesmo saldo duas vezes;
- reversões — `revert_order_stock` cria movimentos inversos (tipo `reversal`,
  ligados por `reversal_of`), sem apagar a baixa original. Não é chamada
  automaticamente no cancelamento: com baixa no envio à cozinha o prato já foi
  feito, e item preparado é perda, não retorno ao estoque (§30);
- snapshot — `StockMovement.source_snapshot` congela a composição usada, então
  editar a ficha depois não reescreve o que já saiu;
- testes — `apps/stock/tests/test_stock_engine.py`.

### Fase 1 — Fundação por lotes

- configuração da prioridade por validade ou entrada e do controle de validade;
- estoque mínimo obrigatório;
- entradas agrupadas;
- lotes e saldos;
- movimentações imutáveis;
- migração do saldo legado.

### Fase 2 — Operação manual

- tela de entradas;
- tela de saídas;
- sugestão pelo critério configurado;
- conferência por leitura de etiqueta;
- ajustes, perdas e transferências.

### Fase 3 — Etiquetas e validade

- modelos de etiqueta;
- `PrintJob` de estoque;
- impressão e reimpressão;
- relatórios e alertas de validade;
- bloqueio de vencidos.

### Fase 4 — Automação

- baixa automática completa na venda;
- baixa de adicionais;
- preparação orientada;
- lote de produto preparado;
- CMV por lote.

### Fase 5 — Offline e duração

- cache operacional no Flutter;
- leitura offline de etiquetas;
- fila de consumo idempotente;
- modo de duração estimada;
- relatórios de previsão.

## 27. Testes mínimos

### Entradas

- entrada com vários insumos;
- validade obrigatória quando configurada;
- validade opcional quando desativada;
- conversão de pacote/kg para gramas;
- confirmação idempotente;
- cancelamento antes e depois de consumo;
- geração e reimpressão de etiquetas.

### Saídas

- prioridade por entrada escolhendo a entrada mais antiga;
- prioridade por validade escolhendo a validade mais próxima;
- somente um critério sendo aplicado por operação;
- empate de validade resolvido pela entrada;
- consumo dividido entre dois lotes;
- lote vencido nunca sugerido;
- leitura da etiqueta correta;
- etiqueta de outro insumo ou local recusada;
- substituição de lote com autorização e justificativa;
- concorrência entre duas saídas sobre o mesmo saldo.

### Venda e receita

- rendimento maior que uma porção;
- kg/g e l/ml;
- adicional consumindo insumo;
- produto direto sem receita;
- segunda chamada não duplicando a baixa;
- cancelamento e estorno conforme política;
- mudança posterior na receita sem alterar o snapshot da venda;
- receita preparada não baixando novamente na venda.

### Relatórios

- abaixo do mínimo;
- vencido, vence hoje e faixas de vencimento;
- valor financeiro em risco;
- saldo por insumo, lote e local;
- histórico de reversões.

### Offline e impressão

- entrada/saída pendente sem duplicação ao reconectar;
- sincronização do saldo do Caixa Principal;
- etiqueta com QR Code;
- etiqueta com Code 128;
- falha e retentativa de impressão sem recriar a entrada;
- confirmação do papel impresso separada da confirmação da entrada.

## 28. Critérios de aceite principais

A primeira versão operacional estará pronta quando:

1. Todo insumo possuir unidade base e estoque mínimo.
2. Uma entrada puder cadastrar vários insumos e gerar lotes.
3. Validade for obrigatória na entrada quando a configuração estiver ativa.
4. A entrada confirmada permitir impressão e reimpressão de etiquetas.
5. Uma saída manual puder listar vários insumos.
6. O sistema selecionar lotes exclusivamente pela validade mais próxima ou
   pela entrada mais antiga, conforme a configuração.
7. A saída assistida indicar o lote e validar sua etiqueta.
8. Produtos com receita baixarem insumos automaticamente sem duplicidade.
9. Adicionais baixarem o insumo e a quantidade configurados.
10. O estoque impedir lotes vencidos e saldo negativo conforme as regras.
11. O histórico explicar toda alteração de saldo.
12. Os relatórios mostrarem estoque mínimo e validade por lote.

## 29. Arquivos principais que serão afetados

Backend:

- `backend/apps/menu/models.py`;
- `backend/apps/menu/serializers.py`;
- `backend/apps/menu/services.py`;
- `backend/apps/orders/services.py`;
- `backend/apps/payments/services.py`;
- `backend/apps/stock/models.py`;
- `backend/apps/stock/serializers.py`;
- `backend/apps/stock/services.py`;
- `backend/apps/stock/views.py`;
- `backend/apps/printers/models.py`;
- `backend/apps/printers/services.py`;
- `backend/config/urls.py`;
- permissões, migrations e testes relacionados.

Frontend web:

- configuração dos recursos de insumos;
- novas telas de entradas, saídas, lotes, preparação, relatórios e configuração;
- componentes de lista de itens;
- componente de leitura/conferência de etiqueta;
- navegação e central de ajuda.

Flutter PDV:

- catálogo de entidades locais;
- banco operacional;
- sincronização de insumos, receitas, lotes e configurações;
- leitura de etiqueta;
- novo documento `stock_label`;
- transporte de impressão para o formato escolhido;
- testes offline, de fila e de idempotência.

Documentação:

- `docs/BACKEND.md`;
- `docs/FRONTEND.md`;
- `docs/FLUTTER_DESKTOP.md`;
- `docs/FLUTTER_PDV_TECNICO.md`;
- `docs/PDV_OFFLINE_SCALE_ARCHITECTURE.md`, caso o contrato offline seja
  ampliado.

## 30. Decisões recomendadas como padrão

- exigir a escolha explícita entre prioridade por validade e prioridade por
  entrada na configuração inicial da filial;
- permitir prioridade por validade somente quando o controle de vencimento
  estiver ativo;
- bloquear estoque vencido;
- bloquear saldo negativo;
- tornar o estoque mínimo obrigatório, permitindo valor zero;
- baixar produtos preparados no envio para cozinha;
- exigir justificativa para substituir o lote sugerido;
- não retornar automaticamente ao estoque um item que já foi preparado;
- usar QR Code como padrão para etiquetas internas e Code 128 quando o
  equipamento ou o processo exigir código de barras linear;
- manter movimentos confirmados imutáveis e corrigi-los somente por reversão.
