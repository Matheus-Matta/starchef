# Padrões de código do StarChef

Como este projeto escreve código, e **por que** cada regra existe. Vale para as
quatro superfícies: `backend/`, `frontend/`, `pdv_desktop/` e `pdv_mobile/`.

Regra que não explica o motivo é desligada na primeira urgência. Por isso cada
item aqui vem com o defeito que ele evita — de preferência um que já aconteceu.

## O critério que decide tudo

> **Entra o que aponta defeito. Fica de fora o que só discorda de uma escolha.**

É o critério dos três arquivos de lint (`backend/pyproject.toml`,
`frontend/eslint.config.js`, `analysis_options.yaml`). Um linter que grita em
cima de decisão deliberada é desligado, e aí ele para de pegar até o que
importava.

**Isso foi medido, não suposto.** Ao ligar `SIM103` no backend, a regra
transformou uma guarda legível em `return not (a and b and c)` — negação
tripla. E `C416` trocou uma compreensão por um `dict(...)` de indentação
quebrada. As duas pedem menos linhas; o preço foi menos clareza. As duas estão
desligadas, com a evidência escrita ao lado.

## Nomes

O nome diz a **intenção**, não o tipo nem o mecanismo.

```python
# ruim
def calc(x, y): ...
data = get()
tmp = []

# bom
def taxa_de_servico_do_pedido(subtotal, percentual): ...
comandas_em_fechamento = ...
```

Três regras que este projeto segue e que surpreendem quem chega:

1. **O domínio é escrito em português.** `comanda`, `sangria`, `pedido`,
   `_apagar_o_lado_da_loja`. Não é descuido: é o vocabulário que o operador do
   caixa usa, e traduzir cria um dicionário mental entre a conversa e o código.
   Por isso a família `N` do ruff está desligada.
2. **Booleano pergunta.** `is_locked`, `tem_itens`, `podeEstornar`.
3. **Nome de teste é uma frase.** `test_a_sangria_aprovada_pelo_gerente_chega_aprovada`.
   Quando ele falha, a linha do relatório já diz o que quebrou.

## Funções pequenas, arquivos pequenos

**Máximo 200 linhas por arquivo.** Passou disso, quebre em módulos com uma
responsabilidade cada.

201 dos 805 arquivos já passavam disso quando a regra passou a ser medida. Uma
trava dura reprovaria todo mundo no primeiro dia, então existe uma **catraca**:

```bash
python scripts/check_tamanho_de_arquivo.py            # confere
python scripts/check_tamanho_de_arquivo.py --atualizar  # ao baixar a dívida
```

O que já era grande está em `scripts/tamanho_de_arquivo.baseline.json` e não
reprova ninguém. **Arquivo novo acima do limite não tem exceção** — quebre.

Arquivo que **já era grande e cresceu** também reprova, e aí há duas saídas,
nesta ordem: quebre o arquivo (é o motivo de a lista existir) ou, se o que
entrou paga o crescimento — um comentário que explica um porquê difícil, uma
correção que precisa de contexto —, rode `--atualizar` e deixe o crescimento
**visível no diff**.

A segunda saída não é brecha: a linha de base é versionada de propósito, então
quem revisa vê o arquivo crescer e pode perguntar por quê. O que não pode é
crescer em silêncio.

Quando um arquivo cresce, o corte natural é por **assunto**, não por camada.
A conta agrupada virou `merge_locks` (ordem de lock), `merge_services` (montar),
`merge_confirm` (consolidar), `merge_settlement` (quitar), `merge_refund`
(estornar) e `merge_expiry` (expirar). Cada um cabe na cabeça de uma vez.

## Comentários: o porquê, nunca o quê

O código já diz o que faz. O comentário existe para o que o código **não pode
dizer**: a razão, a alternativa descartada, o defeito que a linha evita.

```python
# ruim — repete o código
# incrementa o contador
contador += 1

# bom — diz o que o código não pode dizer
# A releitura não é zelo: entre a consulta que listou os candidatos e este
# lock, o caixa pode ter voltado e confirmado a conta. Expirar com o estado
# lido antes do lock cancelaria uma conta que já está sendo paga.
merge = lock_merge(merge.pk)
```

**Comentário desatualizado é pior que nenhum.** Mudou a linha, revise o
comentário dela no mesmo commit.

## Dinheiro, concorrência e estado

As três coisas que este projeto mais erra quando alguém tem pressa:

**Dinheiro nunca é `float`.** `Decimal` no Python, inteiro de centavos ou
`Decimal` no Dart. E arredonde **onde o valor nasce**, não na gravação: o
SQLite não trunca `DecimalField` como o Postgres, e os dois lados discordavam
por um centavo.

Some a isso a regra da taxa: quando um total é a **soma de vários**, some os
valores **já arredondados**. Dois pedidos de R$ 10,05 com 10% dão R$ 1,01 +
R$ 1,01 = R$ 2,02; 10% sobre R$ 20,10 daria R$ 2,01. O centavo some sempre do
mesmo lado.

**Escrita concorrente trava em ordem estável.** Sempre `transaction.atomic` +
`select_for_update` ordenado por UUID, e **releia o estado depois do lock**.
Conferir antes de travar não impede corrida nenhuma — só dá a impressão de que
impede.

**A defesa contra dois operadores é do banco.** Um `if` roda antes do lock do
outro; um índice único condicional roda no INSERT, e não há como os dois
passarem.

```python
models.UniqueConstraint(
    fields=["command"], condition=models.Q(active=True),
    name="unique_active_merge_per_command",
)
```

## Erros que o operador consegue resolver

**409 é conflito de estado; 400 é entrada errada.** A distinção não é
acadêmica: o PDV trata 400 como erro de preenchimento e **reenvia o mesmo corpo
para sempre**. "Outro caixa já incluiu esta comanda" nunca vai passar numa
segunda tentativa.

E a mensagem diz **o que fazer**, não só o que houve:

```
ruim: "Comanda ocupada."
bom:  "A comanda 13 está em fechamento numa conta agrupada. Conclua ou
       cancele a consolidação antes de reabri-la."
```

## Testes

Um teste prova **comportamento**, não implementação. O nome é uma frase, e o
docstring conta o defeito que ele impede:

```python
def test_a_recusa_da_pesagem_vai_NO_INSERT(...):
    """`scale_reading` é `immutable=True`: o destino INSERE e nunca atualiza.

    Uma nota gravada num segundo `save()` viraria um evento de UPDATE que a
    nuvem descarta — e a leitura ficaria lá com o motivo em branco, para
    sempre.
    """
```

**Escreva o teste antes da correção e veja-o falhar.** Um teste que nunca
falhou não provou nada. Ao corrigir um defeito, reverta a correção por um
instante e confirme que o teste pega — foi assim que a catraca de tamanho, a
nota da balança e o saldo do caixa foram validados nesta base.

`pytest.raises(Exception)` é proibido (`B017`): ele passa até com um
`AttributeError` de digitação. Nomeie a exceção.

## Sincronização: a regra que mais some

Nada está pronto enquanto o dado novo não sincronizar. É o passo mais fácil de
esquecer porque a tela funciona sem ele — o defeito aparece na loja, dias
depois, como "sumiu".

- **Model novo** precisa de decisão em `catalog.py` ou `decisions.py`.
  `manage.py sync_check_registry` reprova o deploy sem isso.
- **Campo novo** num model que já sincroniza **não tem trava automática**.
  Confira que ele entra no payload (`serialization.serialize`), e escreva o
  teste — foi assim que se descobriu que `ScaleReading.notes` nunca chegava à
  nuvem.
- **`QuerySet.update()` não dispara signal**, logo não gera evento. Cancelar em
  massa deixa a mudança só na loja.
- **Não declare append-only o que tem ciclo de vida.** `cash_movement` era
  `immutable=True` e tem `pending → approved → cancelled`: as transições
  morriam na chegada e o caixa da nuvem fechava o turno com outro valor.

Detalhes em [`SINCRONIZACAO.md`](SINCRONIZACAO.md).

## Ferramentas por superfície

| Superfície | Lint | Testes | Build |
| --- | --- | --- | --- |
| `backend/` | `ruff check .` | `pytest` | — |
| `frontend/` | `npm run lint` | `npm run test` | `npm run build` |
| `pdv_desktop/` | `flutter analyze` | `flutter test` | `flutter build windows` |
| `pdv_mobile/` | `flutter analyze` | `flutter test` | `flutter build apk` |
| todas | `python scripts/check_tamanho_de_arquivo.py` | | |

As quatro rodam no CI e reprovam o merge.

## Branches e commits

- `main` é produção e só recebe PR aprovado.
- `release/vX.Y.Z` é a linha da versão.
- Trabalho novo sai em `feat/<assunto>`, `fix/<assunto>` ou `docs/<assunto>`.
- Mensagem de commit: `tipo(escopo): o que muda, em uma linha`. O corpo conta o
  **porquê** — é o que alguém vai ler daqui a seis meses pelo `git log`.

```
fix(sync): o movimento de caixa nao e append-only

`cash_movement` era `immutable=True`, mas tem ciclo de vida: a aprovacao da
sangria pelo gerente nunca chegava a nuvem, e o saldo do turno divergia.
```

Tag só com autorização explícita: ela dispara publicação externa dos quatro
produtos (ver [`PDV_UPDATE_RELEASE.md`](PDV_UPDATE_RELEASE.md)).

## Revisão de código

Quem revisa procura, nesta ordem:

1. **Isso pode cobrar errado, perder venda ou travar o salão?** Dinheiro,
   caixa, fiscal e sincronização primeiro — os quatro não se desfazem com um
   revert.
2. **O teste prova o comportamento, e ele já falhou alguma vez?**
3. **O comentário explica o porquê, e ainda é verdade?**
4. **Conflito volta 409?** A mensagem diz o que fazer?
5. **Nome diz a intenção?** Arquivo cabe em 200 linhas?

Sugestão de estilo vem por último e como sugestão. O que trava o merge é
defeito, não gosto.
