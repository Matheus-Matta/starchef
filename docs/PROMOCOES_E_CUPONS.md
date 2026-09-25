# Promoções e cupons

Escrito para: quem for mexer em preço neste sistema — backend, frontend ou PDV.

Duas coisas diferentes, e o documento existe porque confundi-las é o erro mais
caro possível aqui:

- **Promoção** muda o preço da vitrine, para todo mundo, sem ninguém pedir.
- **Cupom** é um direito de UMA pessoa, que precisa ser reconhecida e contada.

Por isso cupom tem resgate, limite e CPF; promoção não tem nada disso.

---

## 1. O preço do produto não é uma coluna

`Product.sale_price`, `Product.promotional_price` e `Product.current_price` são
**propriedades**. O que está gravado é:

| Coluna                  | O que é                                            |
| ----------------------- | -------------------------------------------------- |
| `base_price`            | o preço cheio cadastrado, que nada altera sozinho  |
| `base_promotional_price`| o promocional do próprio cadastro, sem data        |

E o que se **lê**:

| Propriedade         | Responde                                                    |
| ------------------- | ----------------------------------------------------------- |
| `sale_price`        | `base_price` (referência)                                   |
| `promotional_price` | o promocional em vigor — da promoção ativa, ou do cadastro   |
| `current_price`     | **o que o cliente paga.** Todo preço de venda passa por aqui |
| `compare_at_price`  | o valor riscado, ou `None` quando não há nada a riscar       |
| `active_promotion`  | a `Oferta` que venceu a disputa, com a tabela e a regra      |

Os nomes antigos continuam **graváveis**: existem setters, e o Django aceita
propriedade com setter nos kwargs do construtor. `Product(sale_price=10)` e
`produto.sale_price = 10` escrevem em `base_price`. Sem isso, a renomeação
obrigaria a reescrever cinquenta chamadas em semeadura, testes e desserialização
do sync — cada uma uma chance de deixar um preço zerado para trás.

**O que NÃO funciona** (e é intencional): `filter(sale_price=...)`,
`order_by("sale_price")`, `values("sale_price")`. Use `base_price` no ORM.
Para "quais produtos estão em promoção?", use
`apps.promotions.queries.filtro_de_promocao(account_id, restaurant_id)` — ele
devolve um `Q`, e responde no banco em vez de carregar o catálogo inteiro.

### A API não mudou de forma

O formulário continua com **um campo de valor e um de promocional**, e os dois
gravam o cadastro. O serializer usa `exclude = ("base_price",
"base_promotional_price")` para não expor duas portas para o mesmo número — com
duas, o último valor que chegasse venceria, sem ordem definida.

Entraram três campos **somente de leitura**: `current_price`,
`compare_at_price` e `promotion` (`{id, name, table, table_name, price,
compare_at_price, discount_amount, discount_percent}`).

---

## 2. Tabela de desconto, regra e a disputa

```
DiscountTable  (o que vale junto, ou não vale)
  └── Promotion       (uma regra: alvo + tipo de desconto + posição)
        └── PromotionProduct   (o vínculo, com o "de/por" do encarte)
```

**A validade mora na tabela.** A regra pode ter janela própria, mas a da tabela
é o teto. `is_active` é propriedade em ambas: uma tabela que encerra às 18h tem
de parar de valer às 18h, sem ninguém salvar nada. Um booleano gravado
precisaria de tarefa periódica, e o minuto em que ela atrasa é o minuto em que o
caixa cobra errado.

`is_enabled` (gravado) é o interruptor da mão humana; `is_active` (calculado) é a
resposta do relógio. São coisas diferentes: desligar não apaga a janela.

### Quem ganha

1. **Entre tabelas: a mais antiga** (`created_at`). Foi o que o restaurante
   prometeu primeiro, e voltar atrás numa promessa antiga por causa de uma nova
   é o que o cliente lê como propaganda enganosa.
2. **Dentro da tabela: a do topo** (`position`, menor ganha). É o único critério
   que o gerente confere de relance — ordenar por "maior desconto" ou "mais
   específico" exigiria simular a regra para saber quem venceu.

A primeira regra que alcança o produto vence e a busca para. **Não existe soma
de descontos.**

Duas regras para o mesmo produto na **mesma** tabela são **recusadas no
cadastro**: a segunda nunca venceria e ficaria ali, invisível, parecendo ativa —
quem cadastrou juraria ter dado 30% e o caixa cobraria 10%. Entre tabelas
diferentes o conflito é legítimo e se resolve pela mais antiga.

`POST /promotions/rules/reorder/` recebe **todas** as regras da tabela na ordem
desejada. A posição é única por tabela, então ele desloca tudo por um offset
grande antes de reatribuir 1..N — zerar as posições antes violaria a unicidade na
hora, e atribuir direto colidiria com quem já está no destino.

### O "de/por" do encarte

`PromotionProduct` guarda dois números que o cadastro não tem: `promotional_price`
(o "por" cobrado) e `compare_at_price` (o "de" exibido riscado).

**O "de" pode ser MAIOR que o preço cadastrado.** O produto custa 20 e o encarte
anuncia "de 30 por 15". Guardar isso no cadastro obrigaria a subir o preço real
para 30 — e quem comprasse fora da promoção pagaria 30 de verdade.

Isso só existe na regra que aponta **produto direto**. Categoria e setor não têm
onde digitar dois números, e lá o desconto incide sobre o **preço de
prateleira** (`base_promotional_price` quando existe, senão `base_price`). É essa
escolha que garante que uma promoção **nunca aumente** um preço: 10% sobre um
produto que já estava com promocional de 15 dá 13,50, e não 18.

### Desempenho

`pricing.ofertas_para(produtos)` resolve a disputa da lista inteira em poucas
consultas fixas, e `primar()` pendura a resposta em cada objeto
(`_oferta_resolvida`). O serializer de produto faz isso por página. Sem o lote,
uma grade de trinta produtos custaria trinta vezes a mesma consulta — e o PDV
carrega o catálogo inteiro na abertura do caixa.

---

## 3. Cupom

**A identidade é o CPF da nota** (`Order.fiscal_customer_cpf`) — o mesmo que o
cliente informa no pedido. Não existe "cliente selecionado" à parte: no caixa, o
que a pessoa informa é o CPF. O cliente é *derivado* dele
(`coupon_identity.cliente_por_cpf`), e o resgate grava o CPF além do vínculo, para
quem volta com um cadastro novo continuar sendo a mesma pessoa.

Cupom restrito a grupo ou a cliente **exige CPF por consequência**, mesmo com
`requires_document` desmarcado: sem ele não existe a quem comparar.

### As regras

| Campo                      | O que faz                                              |
| -------------------------- | ------------------------------------------------------ |
| `minimum_order_value`      | mínimo em **produtos** — sem taxa de serviço, sem entrega |
| `usage_limit`              | total de usos (0 = ilimitado)                          |
| `usage_limit_per_customer` | usos por CPF (0 = ilimitado)                           |
| `single_use_per_customer`  | compra única (equivale a 1 por CPF)                    |
| `first_purchase_only`      | só para quem não tem pedido **pago**                   |
| `requires_document`        | exige CPF na nota                                      |
| `customer_groups` / `customers` | vazios = todo mundo                               |
| `order_types`              | tipos aceitos; vazio = todos                           |
| `max_discount_amount`      | teto, só para percentual                               |
| `combines_with_promotions` | desligado, recusa pedido com item em promoção          |

O mínimo **não conta as taxas** porque contá-las liberaria o cupom de "acima de
R$ 50" num pedido de R$ 44 de comida que chegou a 50 por causa do frete — o
restaurante daria desconto sobre uma venda que nunca atingiu o patamar.

### Cada recusa devolve o MOTIVO, não um booleano

No caixa, com o cliente ouvindo, "cupom inválido" faz o operador repetir a
digitação três vezes para um cupom que simplesmente venceu ontem — e na terceira
o cliente já duvidou da loja. `coupon_rules.avaliar()` devolve
`(motivo, desconto, cliente)`, e a ordem das verificações é deliberada: primeiro
o que é do cupom (venceu, esgotou), depois o do pedido (mínimo, tipo), e por
último o da pessoa. Pedir CPF para depois dizer "esse cupom venceu" é o pior dos
roteiros.

A API responde **422 `coupon_rejected`** — e não 400. O corpo está certo e o
código foi digitado certo; o que barra é uma regra. Um 400 faria o PDV tratar
como erro de digitação e pedir o código de novo.

### Ciclo de vida

```
aplicar (close ou apply-coupon)  →  coupon + coupon_code + coupon_discount
recalculate_order                →  REAVALIA e zera o desconto se caiu
pagamento integral               →  CouponRedemption nasce
cancelamento                     →  CouponRedemption é apagado
```

- **O resgate só nasce no pagamento.** Gravado na aplicação, um cupom de compra
  única queimaria num pedido abandonado e o cliente perderia o direito sem ter
  comprado nada. `registrar_resgate` é idempotente porque pagamento se
  reconfirma (fila offline, webhook repetido).
- **O cancelamento apaga o resgate** em vez de decrementar um contador: contador
  perde a conta na primeira condição de corrida, e "quem usou" deixa de ser
  respondível.
- **O cupom é reavaliado a cada recálculo.** Quem aplica um cupom de "acima de
  R$ 50" num pedido de R$ 60 e remove metade dos itens não pode continuar com o
  desconto. O **vínculo** fica: o pedido pode voltar a se qualificar no item
  seguinte, e reaplicar sozinho é melhor do que obrigar o caixa a digitar de novo.
- `coupon_discount` é campo **separado** do `discount`. Um é regra que o cliente
  exerceu, o outro é decisão de um gerente. Somados numa coluna, o recálculo
  apagaria o abatimento dado à mão toda vez que reavaliasse o cupom.

`total = subtotal + service_fee + delivery_fee - discount - coupon_discount`

---

## 4. Rotas

| Rota                                          | O que é                          |
| --------------------------------------------- | -------------------------------- |
| `/promotions/discount-tables/`                | CRUD; traz as regras dentro      |
| `/promotions/discount-tables/{id}/toggle/`    | liga/desliga sem abrir o formulário |
| `/promotions/rules/`                          | CRUD; grava `product_links` no mesmo salvamento |
| `/promotions/rules/reorder/`                  | `{"ids": [...]}` — todas as regras da tabela |
| `/promotions/coupons/`                        | CRUD                             |
| `/promotions/coupons/validate/`               | `{"code", "order"}` → confere **sem** aplicar |
| `/promotions/coupons/{id}/redemptions/`       | quem usou                        |
| `/promotions/coupon-redemptions/`             | leitura; nascem do pagamento     |
| `/orders/{id}/apply-coupon/`                  | `{"code"}`; vazio retira. Serve conta aberta E em pagamento |
| `/orders/{id}/close/`                         | aceita `coupon_code`             |

`validate` existe para o caixa conferir enquanto o cliente fala. Aplicar para
depois desfazer deixaria rastro de cupom em pedido que o cliente desistiu de
fechar — e queimaria o limite de um cupom de uso único.

No `close`, `coupon_code` ausente significa **"não mexe"** e string vazia
significa **"retira"**. São gestos diferentes: fechar de novo para corrigir a
taxa não pode derrubar o cupom que já estava aplicado; e o caixa que apagou o
código de propósito precisa ver o desconto sair.

O código entra **depois** do CPF dentro de `close_order`: as regras de grupo e de
"um por cliente" se resolvem pelo CPF da nota, e avaliar antes de gravá-lo
recusaria quem acabou de informá-lo.

Em `apply-coupon`, `code` **ausente é 400**: não existe "não mexe" numa rota cujo
único propósito é mexer. Ela serve o pedido **aberto** e o pedido **em
pagamento** — o cliente informa o cupom antes de fechar, e informa também no meio
do pagamento, quando lembra.

### As duas guardas (`coupon_guards.py`)

- **venda paga, cancelada ou bloqueada recusa.** Mexer no total de uma venda paga
  criaria diferença de caixa sem contrapartida: o dinheiro que entrou não volta
  por causa de um cupom lembrado depois. Conta **parcialmente** recebida continua
  aceitando — é justamente o caso do cupom entregue no meio do pagamento.
- **o total não pode cair abaixo do já recebido.** Se o cliente pagou R$ 60 de uma
  conta de R$ 60 e o cupom abate R$ 10, o caixa ficaria devendo R$ 10 que nenhum
  troco registrou. A conferência é **depois** do recálculo e **dentro** da
  transação de `mexer_no_cupom`: a recusa desfaz a aplicação, ou o pedido ficaria
  com o desconto que acabou de ser rejeitado.

---

## 5. Sincronização

| Entidade            | Fluxo            | Por quê                                             |
| ------------------- | ---------------- | --------------------------------------------------- |
| `discount_table`    | `cloud_to_local` | preço é decisão do escritório                        |
| `promotion`         | `cloud_to_local` | `products` **não** viaja como m2m (ver abaixo)       |
| `promotion_product` | `cloud_to_local` | é ele que leva o "de/por"                           |
| `coupon`            | `cloud_to_local` | com `customer_groups` e `customers`                 |
| `coupon_redemption` | `both`           | **sobe**: nasce no pagamento, que acontece na loja   |

`cloud_to_local` não é economia de tráfego — é o que impede uma loja de inventar
desconto próprio e a rede descobrir no fechamento do mês.

`Promotion.products` está em `exclude_fields` porque passa por
`PromotionProduct`, que tem campos próprios. Sincronizar o m2m gravaria o vínculo
**sem** esses valores: a promoção chegaria na loja apontando o produto certo com
preço vazio, e o caixa cobraria o preço cheio.

O resgate sobe porque, sem isso, um cupom de uso único usado no balcão ficaria
invisível para a nuvem e a mesma pessoa usaria de novo no delivery.

> **Atenção no deploy desta versão:** `base_price` substitui `sale_price` no
> payload de sincronização, e `deserialize()` descarta em silêncio campo que o
> model local não conhece (§17 de `SINCRONIZACAO.md`). Nuvem e loja precisam subir
> **na mesma tag** — uma loja em versão antiga descartaria atualizações de preço
> sem erro nenhum.

---

## 6. Onde isso aparece para o operador

**Frontend:** `Promoções` no menu (só gerente para cima) → Tabelas de desconto,
Regras de desconto, Cupons. No cadastro do produto, os dois campos de preço
continuam iguais, e **abaixo deles** aparece um aviso quando o cobrado é outro:
ele diz quanto, de quanto, e **nomeia** a tabela e a regra. Nomear é o ponto — "o
sistema está cobrando menos" não diz onde ir para mudar, e sem isso o gerente vê
o cadastro intacto, o PDV cobra outro valor, e conclui que o sistema errou.

**PDV desktop:** a grade mostra o "de" riscado acima do "por"
(`ProductPriceLabel`). O cupom aparece em **dois** lugares:

1. no diálogo de fechamento, junto do CPF — que é a identidade dele. Em telas
   separadas, o caixa digitaria o cupom, ouviria "informe o CPF" e voltaria;
2. no resumo da **tela de pagamento** (`PaymentCouponInput`), com **Aplicar**,
   **Trocar** e **Retirar**. O cliente lembra do cupom quando o caixa fala o
   total — é o caso normal, não a exceção — e sem isto seria preciso desfazer o
   fechamento por causa de um código.

A recusa aparece **no campo**, e não no centro de erros: a frase é sobre o cupom,
e quem precisa lê-la está olhando o que acabou de digitar.

**PDV web (retaguarda):** `PdvCouponField` nos mesmos dois momentos — no painel
de confirmação (ao lado da taxa e do CPF) e no resumo do pagamento. O componente
não guarda total: emite o pedido que o servidor devolveu, já recalculado, e a
tela tira dali o restante e o troco. `orderPreviewTotal` desconta o cupom — sem
isso ele ia como `expected_total` sem o abatimento, e o servidor respondia com
reconciliação a cada venda com cupom.

**PDV mobile:** o picker, a configuração do produto e a **prévia de preço do
garçom** (`expectedUnitPrice`) leem `current_price`. Antes a prévia lia
`sale_price`: mostrava um valor e a venda gravava outro, e a divergência aparecia
depois de o cliente já ter ouvido o total.

**Cardápio digital:** o bloco `Promoções` acha os produtos por
`filtro_de_promocao`. Antes só achava quem tinha promocional digitado no cadastro
— uma tabela de 20% na categoria mudava o preço na vitrine e o bloco continuava
vazio.
