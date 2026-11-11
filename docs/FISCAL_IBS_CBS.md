# IBS e CBS (reforma tributária) no perfil fiscal

Como o StarChef monta o grupo IBS/CBS da NFC-e/NF-e (NT 2025.002-RTC), do
cadastro do produto até o INI da ACBrLib e o JSON da Focus.

## A ideia em uma frase

O produto recebe uma **regra**, nunca um valor. A regra fica no perfil fiscal
(CST, cClassTrib, redução, diferimento). A **alíquota** vem do ano da emissão, e
o **valor** é calculado item a item na hora de emitir.

Exemplo: o perfil "Refrigerante" tem CST `000` e cClassTrib `000001`. Numa
venda de R$ 25,00 em 2026:

| Tributo | Alíquota | Valor |
| --- | --- | --- |
| CBS | 0,9% | R$ 0,23 |
| IBS estadual | 0,1% | R$ 0,03 |
| IBS municipal | 0% | R$ 0,00 |

Em 2027 a alíquota muda, o perfil continua igual e ninguém precisa recadastrar
nenhum produto.

## Onde cada coisa mora

| O quê | Onde |
| --- | --- |
| Campos (perfil e item da nota) | `backend/apps/invoices/models_ibs_cbs.py` (mixin `IbsCbsCampos`) |
| Regra, validação e cálculo | `backend/apps/invoices/ibs_cbs.py` |
| Alíquotas por ano | `ibs_cbs.ALIQUOTAS` |
| Item no documento neutro (chaves da Focus) | `documento.py`, `_build_item` |
| Tradução para o INI da ACBrLib | `backend/apps/invoices/acbrlib/ini_ibs_cbs.py` |
| Liga/desliga por loja | `FiscalConfig.ibs_cbs_enabled` (tela: Configuração fiscal › Reforma tributária) |
| Cadastro no painel | Financeiro › Perfis fiscais, seção "IBS / CBS" |

## Campos do perfil

| Campo | Obrigatório | Observação |
| --- | --- | --- |
| `ibs_cbs_cst` | quando a loja liga o grupo | um CST só para IBS e CBS |
| `ibs_cbs_cclass_trib` | junto com o CST | 6 dígitos e começa pelo CST (`200003` é do CST `200`) |
| `ibs_cbs_reducao` | só nos CST 200 e 515 | `pRedAliq` em %; 60 = paga 40% da alíquota |
| `ibs_cbs_diferimento` | só nos CST 510 e 515 | `pDif` em % |

Os CST aceitos são `000`, `200`, `410`, `510` e `515`. O `410` (imunidade e
não incidência) leva só o CST e o cClassTrib, sem valores. Os outros CST (550,
620, 800 em diante) exigem grupos que a venda de restaurante não tem, como
tributação regular, monofásica e transferência de crédito. O cadastro recusa
esses CST para a nota não sair pela metade.

**Não confunda com PIS/COFINS.** CST `06` de PIS/COFINS (alíquota zero) não
vira CST zero de IBS/CBS: são tabelas diferentes. Os campos de ICMS, PIS e
COFINS continuam no perfil durante a transição.

## Planilha de importação e exportação

A planilha de Perfis fiscais (botões Exportar/Importar da lista) sai dos campos
do formulário, então as quatro colunas de IBS/CBS vêm nela. Ela aceita o nome
técnico ou o rótulo da coluna:

| Coluna (rótulo) | Nome técnico | Exemplo |
| --- | --- | --- |
| CST do IBS/CBS | `ibs_cbs_cst` | `000` |
| Classificacao tributaria (cClassTrib) | `ibs_cbs_cclass_trib` | `000001` |
| Reducao de aliquota (%) | `ibs_cbs_reducao` | `60` |
| Diferimento (%) | `ibs_cbs_diferimento` | `0` |

O caminho comum é exportar, preencher no Excel e importar de volta. O perfil é
reconhecido pelo nome: o que já existe é atualizado e o que não existe é
criado. O Excel apaga o zero à esquerda (`000` vira `0`, `000001` vira `1`), e
o servidor completa de volta (`ibs_cbs.completar_zeros`). Uma regra impossível
continua recusada e aparece no resultado com o número da linha.

## Liberação: o flag da loja

`FiscalConfig.ibs_cbs_enabled` começa **desligado**. Com ele desligado, o perfil
pode estar preenchido e a nota sai exatamente como antes. O roteiro:

1. Preencher CST e cClassTrib nos perfis, conferidos com o contador.
2. Ligar o flag numa loja em **Homologação** e emitir uma venda.
3. Conferir a nota autorizada (grupo `IBSCBS` em cada item, `IBSCBSTot` no
   total) e só então passar a loja para Produção.

Com o flag ligado, um produto sem CST/cClassTrib vira pendência do cadastro
(`fiscal_payload["fiscal_profile_issues"]`). A pendência só **bloqueia** a nota
se `strict_fiscal_profile` estiver ligado, a mesma regra do NCM e do CST do ICMS.

## Cálculo

- Base (`vBC`) = valor do item − desconto rateado + outras despesas rateadas.
- Alíquota efetiva = alíquota × (100 − redução) / 100, com 4 casas.
- Valor = base × alíquota efetiva, arredondado no item.
- Diferido = valor × diferimento / 100. Na nota sai o valor menos o diferido.
- Total da nota = **soma dos valores já arredondados** de cada item, nunca o
  percentual aplicado ao total.

A base não desconta ICMS, PIS e COFINS. Essa exclusão é regra de 2027 em
diante e deve ser revista junto com a tabela de alíquotas de 2027.

**Ano sem alíquota cadastrada recusa a nota**, com uma mensagem que aponta
`ibs_cbs.ALIQUOTAS`. É de propósito: inventar uma alíquota daria uma nota aceita
e errada. Cadastrar o ano seguinte é tarefa de dezembro, e só afeta as lojas
com o flag ligado.

## ACBrLib: o INI

Nomes conferidos no `ACBrNFe.IniReader.pas` (frones/ACBr). Os grupos são seções
**soltas**, numeradas pelo item, e não aninhadas:

```ini
[IBSCBS001]
CST=000
cClassTrib=000001

[gIBSCBS001]
vBC=25.00
vIBS=0.03

[gIBSUF001]
pIBSUF=0.1000
vIBSUF=0.03

[gIBSMun001]
pIBSMun=0.0000
vIBSMun=0.00

[gCBS001]
pCBS=0.9000
vCBS=0.23

[IBSCBSTot]
vBCIBSCBS=25.00

[gIBS]
vIBS=0.03
vCredPres=0.00
vCredPresCondSus=0.00

[gIBSUFTot]
vDif=0.00
vDevTrib=0.00
vIBSUF=0.03

[gIBSMunTot]
vDif=0.00
vDevTrib=0.00
vIBSMun=0.00

[gCBSTot]
vDif=0.00
vDevTrib=0.00
vCBS=0.23
vCredPres=0.00
vCredPresCondSus=0.00
```

Armadilhas do leitor da ACBr:

- `gIBSUF`/`gIBSMun`/`gCBS` só são lidos se `gIBSCBS` existir. Sem ela, os
  valores somem sem erro;
- redução (`pRedAliq`, `pAliqEfet`) e diferimento (`pDif`, `vDif`) são
  **chaves** dentro de `gIBSUF`/`gIBSMun`/`gCBS`, não seções próprias;
- nos totais, `vDif` e `vDevTrib` são obrigatórios mesmo zerados.

## Focus NFe

O documento neutro já usa as chaves da Focus: `ibs_cbs_situacao_tributaria`,
`ibs_cbs_classificacao_tributaria`, `ibs_cbs_base_calculo`,
`ibs_uf_aliquota`/`ibs_uf_valor`, `ibs_mun_aliquota`/`ibs_mun_valor`,
`cbs_aliquota`/`cbs_valor` e, quando houver,
`*_percentual_reducao_aliquota`, `*_aliquota_efetiva`,
`*_percentual_diferimento` e `*_valor_diferido`. A Focus calcula os totais.
Os nomes vieram do guia "IBS e CBS" da Focus. A homologação é que confirma.

## Fora do escopo (por enquanto)

- **Crédito presumido** e **tributação regular** (CST 550): não aparecem na
  venda ao consumidor de restaurante. Entram como campos novos do mixin quando
  houver um caso real, com o código validado pelo contador.
- `vNFTot` (total da nota com IBS/CBS "por fora"): só passa a valer em 2027.

## Sincronização

Os campos novos entram no payload sem configuração extra (`FiscalProfile`,
`FiscalConfig` e `InvoiceItem` já sincronizam). O teste
`test_regra_e_flag_viajam_para_a_loja` (em
`backend/apps/invoices/tests/test_ibs_cbs.py`) trava isso.
