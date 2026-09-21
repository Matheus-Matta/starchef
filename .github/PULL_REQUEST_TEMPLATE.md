<!--
Este modelo existe para a REVISÃO ser rápida, não para encher linguiça.
Apague as seções que não se aplicam — um PR de uma linha não precisa de todas.
-->

## O que muda, e por quê

<!--
O "por quê" é o que o diff não conta. Descreva o problema que existia; o código
já mostra a solução. Se o PR corrige um defeito, diga como ele aparecia para
quem usa: "o caixa recebia 'comanda ocupada' e não tinha o que fazer".
-->

Fecha #

## Como foi verificado

<!-- O que você RODOU, com o resultado. "Testei" não é verificação. -->

- [ ] Testes automatizados cobrem a mudança (não só passam — cobrem)
- [ ] Rodei a suíte da(s) superfície(s) tocada(s)
- [ ] Exercitei o caminho na interface / no terminal

```
# cole aqui a saída que comprova
```

## Superfícies tocadas

- [ ] `backend/` — `pytest` + `ruff check .`
- [ ] `frontend/` — `npm run lint` + `npm run test` + `npm run build`
- [ ] `pdv_desktop/` — `flutter analyze` + `flutter test`
- [ ] `pdv_mobile/` — `flutter analyze` + `flutter test`
- [ ] `storefront/`

## Checklist

- [ ] **Model novo tem decisão de sincronização** (`catalog.py` ou
      `decisions.py`) — `manage.py sync_check_registry` reprova o deploy sem
      isso. **Campo novo** num model que já sincroniza também viaja? Um campo
      que não viaja some na loja dias depois, como "sumiu".
- [ ] Nenhum arquivo novo passa de 200 linhas
      (`python scripts/check_tamanho_de_arquivo.py`)
- [ ] Os comentários explicam **por que**, não **o quê**
- [ ] Nomes dizem a intenção (nada de `data`, `temp`, `handle`)
- [ ] Dinheiro em `Decimal`/inteiro, nunca `float`
- [ ] Escrita concorrente sob `transaction.atomic` + lock em ordem estável
- [ ] Erro devolve **409** quando é conflito de estado, **400** só quando a
      entrada está errada (o PDV reenvia 400 para sempre)
- [ ] Mensagem de erro diz ao operador **o que fazer**, não só o que houve

## Risco

<!--
O que pode dar errado em produção, e como voltar atrás. Se mexe em dinheiro,
fiscal, caixa ou sincronização, diga aqui — esses quatro não se desfazem com
um `git revert`.
-->
