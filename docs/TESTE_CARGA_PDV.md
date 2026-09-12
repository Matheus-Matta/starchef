# Teste de carga do PDV Flutter

Suíte manual que exercita o **núcleo do PDV desktop por dentro**, em volume, à
procura de três coisas: bug, erro não tratado e **demora na resposta**.

Não confundir com [`TESTE_CARGA.md`](TESTE_CARGA.md): aquele bate na API pela
rede e simula o protocolo do PDV em Python; este roda o código Dart de verdade —
o mesmo `PdvDatabase`, o mesmo `SyncQueueService`, o mesmo `OfflineFirstGateway`,
a mesma `HandsFreeMachine`, a mesma `PrintQueueService`. Os dois se completam:
um mede o servidor, o outro mede o terminal.

O código vive em [`flutter/loadtest/`](../flutter/loadtest). O que a primeira
rodada encontrou está em [`ANALISE_DE_RISCOS.md`](ANALISE_DE_RISCOS.md).

---

## 1. Como rodar

```powershell
Set-Location flutter
flutter test loadtest/ --dart-define=PERFIL=pesado
```

Fora de `test/` de propósito: `flutter test` sem argumento — o comando do CI —
não alcança esta pasta. Nada aqui roda sozinho.

| `--dart-define` | O que faz |
| --- | --- |
| `PERFIL` | `fumaca`, `leve`, `medio` (padrão `leve`), `pesado`, `extremo` |
| `FASES` | subconjunto: `catalogo,venda,caixa,balanca,impressao,sync` |
| `CAOS` | fração de payloads inválidos (padrão `0.3`) |
| `SEMENTE` | repete a mesma execução |
| `RELATORIO` | pasta de saída (padrão `artifacts/loadtest/pdv`) |

| Perfil | Vendas | Leituras | Pesagens | Cupons | Produtos no catálogo |
| --- | --- | --- | --- | --- | --- |
| `fumaca` | 10 | 40 | 10 | 20 | 50 |
| `leve` | 60 | 300 | 40 | 120 | 300 |
| `medio` | 250 | 1200 | 150 | 400 | 1500 |
| `pesado` | 800 | 4000 | 500 | 1200 | 5000 |
| `extremo` | 2500 | 12000 | 1500 | 4000 | 20000 |

---

## 2. O que ele mede

### 2.1 Orçamento de tempo — a resposta para "está lento?"

Cada operação tem um **orçamento** em `loadtest/src/metrics.dart`: o tempo
máximo aceitável no p95. Os números vêm da natureza da operação, não de
medição — uma escrita local é um `INSERT` mais um `INSERT` na fila, na mesma
transação; uma leitura de detalhe é uma consulta por chave primária. Passar
disso significa varredura de tabela, JSON grande demais ou espera por lock.

| Operação | Orçamento p95 |
| --- | --- |
| `escrita.abrir_pedido`, `escrita.lancar_item` | 80 ms |
| `escrita.fechar_pedido`, `escrita.receber` | 120 ms |
| `leitura.pedido`, `leitura.caixa_atual` | 60 ms |
| `leitura.catalogo` | 150 ms |
| `render.cupom` | 20 ms |
| `impressao.enfileirar` | 60 ms |

Uma amostra isolada acima de **10× o orçamento** conta como `travou`: é a
interface congelando com o cliente na frente do caixa. Diferente do p95 estourado
(que é lentidão), um travamento reprova a execução.

### 2.2 Vereditos

| Veredito | Significa | É defeito? |
| --- | --- | --- |
| `ok` | operação válida concluída dentro do limite | não |
| `recusa_correta` | dado inválido foi recusado | não (é o certo) |
| `lixo_aceito` | dado inválido foi **aceito e gravado** | **sim** |
| `erro_inesperado` | exceção onde deveria haver recusa tratada | **sim** |
| `travou` | acima de 10× o orçamento | **sim** |

---

## 3. As fases

| Fase | O que exercita |
| --- | --- |
| `catalogo` | listagem paginada, busca, filtro hostil (`' OR 1=1--`), página inexistente, `page_size` absurdo, leitura de registro que não existe |
| `venda` | abrir pedido (comanda e balcão), lançar item, enviar à cozinha, cancelar item, fechar e receber — com 30% dos lançamentos preenchidos errado |
| `caixa` | abertura, `current`, sangria, suprimento e fechamento, com os casos inválidos de cada um |
| `balanca` | `HandsFreeMachine` do prato vazio até a comanda, incluindo abandono e timeout, mais o `checkout-command` offline por peso bruto |
| `impressao` | renderização do cupom (`LocalPrintRenderer`) e a fila local com impressora falhando |
| `sync` | a rede volta: escoamento da fila, promoção do id temporário, reenvio idempotente, resposta corrompida e servidor fora do ar |

**A rede começa desligada.** Tudo o que as fases fazem tem de funcionar offline
e ficar na fila — é a promessa central do PDV
([`PDV_OFFLINE_SCALE_ARCHITECTURE.md`](PDV_OFFLINE_SCALE_ARCHITECTURE.md)).

### 3.1 O transporte falso

`TransporteDeCarga` (`loadtest/src/stack.dart`) imita o backend o suficiente
para a fila fazer sentido: devolve id definitivo na criação e **respeita a chave
de idempotência**, devolvendo a mesma resposta para a mesma chave — que é o
contrato do `IdempotencyMiddleware`. Ele também sabe ficar fora do ar, lento,
instável (`TransientSyncFailure`), recusar por regra (`ApiException` 400) e
devolver **resposta ilegível** — o HTML que um proxy reverso caído entrega no
lugar do JSON.

---

## 4. Verificações de coerência

Além do tempo, a suíte cobra propriedades que o PDV promete:

- pedido criado offline nasce com id temporário próprio;
- venda paga mostra **exatamente um** recebimento no terminal;
- caixa abre, aceita movimentação e fecha sem rede — e some de `current` depois;
- pesagem sem comanda **expira** em vez de virar venda;
- cupom que falhou volta para a fila em vez de sumir;
- a operação inteira fica registrada na fila enquanto não há rede;
- pedido entregue troca o id temporário pelo definitivo;
- reenvio da fila não duplica operação já entregue;
- **o ciclo de sincronização sobrevive a uma resposta ilegível do servidor**;
- o SQLite continua íntegro (`PRAGMA quick_check`) depois de tudo.

Uma verificação reprovada vale mais que qualquer número de latência.

---

## 5. Lendo o relatório

O Markdown abre com a situação, a tabela de vereditos, o **tempo por operação**
com a coluna `situacao` (`ok` / `ACIMA`), as verificações e os problemas com o
detalhe da exceção. O JSON ao lado serve para comparar duas execuções — antes e
depois de uma correção.

O teste falha (código de saída ≠ 0) quando há `erro_inesperado`, `travou` ou
verificação reprovada. **`lixo_aceito` e p95 acima do orçamento não derrubam a
execução**: eles aparecem no relatório para decisão humana, porque nem todo
valor tolerado é bug e nem todo milissegundo a mais importa.

---

## 6. O que este teste NÃO faz

- Não abre janela nem toca widget: o alvo é o núcleo, não a árvore de UI.
  Travamento de renderização continua sendo assunto do `flutter test` comum.
- Não fala com hardware: balança, leitor e impressora seguem exigindo
  homologação física (ver `PDV_OFFLINE_SCALE_ARCHITECTURE.md`).
- Não sobe o servidor local (`/local/...`) nem a cadeia secundário → principal.
  Essa parte é coberta pelos testes de `test/features/topology/` e pela suíte
  Python em [`TESTE_CARGA.md`](TESTE_CARGA.md).
- Não substitui o `flutter test`: ele prova regra; este prova comportamento sob
  volume e sob tempo.
