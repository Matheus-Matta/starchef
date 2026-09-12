# loadtest — carga do PDV Flutter (execução manual)

Testa o **núcleo do PDV por dentro**: o mesmo SQLite, a mesma fila de saída, o
mesmo gateway offline-first, a mesma máquina da Balança Rápida e a mesma fila de
impressão que rodam no balcão. Só a rede é substituída, por um transporte que o
teste liga, desliga, atrasa e faz recusar sob comando.

Ele mora fora de `test/` de propósito: `flutter test` sem argumento — o que o CI
roda — não o encontra.

```powershell
flutter test loadtest/ --dart-define=PERFIL=pesado
flutter test loadtest/ --dart-define=PERFIL=medio --dart-define=FASES=venda,sync
```

Perfis: `fumaca`, `leve`, `medio`, `pesado`, `extremo`.
Fases: `catalogo`, `venda`, `caixa`, `balanca`, `impressao`, `sync`.
Outros `--dart-define`: `CAOS` (0 a 1), `SEMENTE`, `RELATORIO`, `DETALHADO`.

O relatório sai no terminal e em `artifacts/loadtest/pdv/pdv-carga-<data>.{md,json}`.

## O diferencial: orçamento de tempo

Toda operação tem um **orçamento** em `src/metrics.dart` — o tempo máximo
aceitável no p95. Uma escrita local é um INSERT mais um INSERT na fila, na mesma
transação: passar de 80 ms significa que alguma coisa está varrendo tabela ou
esperando lock. É assim que "demora na resposta" vira um número que reprova, em
vez de uma impressão.

Uma amostra isolada acima de 10× o orçamento conta como **travamento** — a
interface congelando na frente do cliente.

A documentação completa está em
[`docs/TESTE_CARGA_PDV.md`](../../docs/TESTE_CARGA_PDV.md).
