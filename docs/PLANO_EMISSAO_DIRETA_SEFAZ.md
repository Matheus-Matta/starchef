# Emitir NFC-e direto na SEFAZ — o que é preciso

Hoje o StarChef emite pela Focus NFe: nós montamos os dados, ela assina,
numera e conversa com a SEFAZ. Este documento descreve o que muda se
quisermos falar com a SEFAZ **sem intermediário**.

Não é uma proposta de fazer agora. É o mapa para decidir com números na mão.

> **Aviso.** Nada aqui é parecer jurídico ou contábil. A legislação é
> estadual, e vocês operam no Rio de Janeiro — confirme cada exigência com o
> contador e com a SEFAZ-RJ antes de planejar prazo.

---

## 1. Os documentos e cadastros que você precisa ter

Esta é a parte que **não se resolve programando**, e é por onde começa.

### 1.1 Certificado digital A1 da empresa emitente

O arquivo `.pfx` e a senha, do CNPJ que vai emitir. É ele que assina cada
nota — sem assinatura válida não existe documento fiscal.

Você já tem: está carregado no cadastro e chega à loja pelo canal de
credenciais. Vence todo ano; a renovação precisa entrar no calendário de
alguém, porque no dia em que ele vencer o restaurante para de emitir.

### 1.2 Inscrição Estadual ativa e credenciamento para NFC-e

O CNPJ precisa estar credenciado na SEFAZ-RJ para emitir NFC-e. Isso é
pedido uma vez, por empresa.

### 1.3 CSC — Código de Segurança do Contribuinte

Dois valores: o **ID** (`idToken`, um número pequeno) e o **token** (o segredo
em si). São emitidos pela SEFAZ-RJ para o CNPJ, e existem em duas versões —
uma de homologação e outra de produção.

O CSC é o que permite montar o QR Code que o consumidor lê. Sem ele o QR sai
inválido.

Você já tem: está no cadastro fiscal.

### 1.4 CSRT — Código de Segurança do Responsável Técnico

**Este é o que falta, e não é do restaurante: é da StarChef.**

O leiaute da NFC-e exige identificar quem desenvolveu o sistema emissor — o
grupo `infRespTec`, com CNPJ, contato, e-mail e telefone do desenvolvedor.
Vários estados exigem também o **CSRT**, um código que a SEFAZ emite **para a
empresa de software**, não para o cliente.

O que isso significa na prática:

- a StarChef se cadastra como responsável técnico na SEFAZ-RJ;
- recebe um `idCSRT` e um `CSRT`;
- cada nota emitida leva o hash desse código.

É um cadastro administrativo, feito uma vez, mas **é pré-requisito**: sem ele
a nota é rejeitada. Confirme com o contador se a SEFAZ-RJ exige CSRT para
NFC-e — a regra varia por estado.

### 1.5 Documentação técnica oficial

Baixada do Portal da NF-e, e precisa ser a **versão vigente**:

- **MOC** — Manual de Orientação do Contribuinte, que descreve o leiaute;
- **Nota Técnica vigente** (hoje a série 2025.001), que altera o MOC;
- **Pacote de XSD** — os esquemas contra os quais o XML é validado antes de
  ser enviado;
- **Manual de Padrões Técnicos do DANFE NFC-e e QR Code**, que define o que é
  impresso e como o QR é montado — inclusive o QR de contingência, que é
  diferente do normal.

Estes arquivos mudam. Acompanhar as notas técnicas passa a ser trabalho
recorrente de alguém — é exatamente o serviço que hoje se paga à Focus.

---

## 2. O que já está pronto no StarChef

Vale conhecer antes de estimar, porque é mais do que parece.

| Peça | Onde está |
|---|---|
| Dados do emitente (razão social, CNPJ, IE, endereço, IBGE, UF, CEP, CRT) | `FiscalConfig` |
| Dados fiscais por item (NCM, CEST, CFOP, CSOSN/CST, origem, ICMS, PIS, COFINS) | `InvoiceItem` |
| Formas de pagamento traduzidas para o código fiscal (`tPag`) | `providers._payment_code` |
| Chave de acesso, com dígito verificador e `tpEmis` | `fiscal.build_access_key` |
| Assinatura XMLDSig (C14N 1.0, RSA-SHA1, enveloped) | `inbound_nfe/services/signer.py` |
| Comunicação SOAP com a SEFAZ usando o certificado | `inbound_nfe/services/sefaz_client.py` |
| QR Code da NFC-e, modo online | `fiscal.build_nfce_qrcode` |
| Impressão do DANFE | `printers/` |
| Regra de quando cabe contingência | `invoices/contingency.py` |
| Numeração que não repete número já gravado | `invoices/services._proximo_numero_livre` |

A parte que costuma travar projetos assim — ter o dado fiscal correto de cada
item — já está resolvida.

---

## 3. O que falta construir

Em ordem de esforço crescente.

### 3.1 Dois campos no cadastro (pequeno)

`dhCont` e `xJust` — data/hora de entrada em contingência e o motivo. São
obrigatórios quando `tpEmis=9` e não existem no modelo hoje.

### 3.2 Série própria para contingência (pequeno, mas decisão)

Hoje quem numera é a Focus. Se a loja numerar em contingência na mesma série,
os dois contadores colidem — é a rejeição *"Duplicidade de NF-e, com diferença
na Chave de Acesso"* virando rotina.

Contingência precisa de série separada, reservada para ela.

### 3.3 QR Code de contingência (pequeno)

O nosso monta o QR **online**: `chave|versão|tpAmb|idCSC|hash`.

O de contingência leva mais campos — data/hora de emissão, valor da nota,
valor do ICMS e o digest da assinatura —, justamente para o consumidor poder
conferir a nota antes de ela chegar à SEFAZ. São dois formatos, não um.

### 3.4 Montador do XML da NFC-e (grande)

O coração do trabalho. Os grupos `ide`, `emit`, `det` por item (com ICMS, PIS
e COFINS), `total`, `pag`, `infAdic` e `infRespTec`.

É transcrição, não pesquisa: os dados estão todos no banco. Mas é longo e
cada detalhe errado vira rejeição da SEFAZ.

### 3.5 Validação contra o XSD (médio)

Validar o XML antes de enviar. Sem isso, cada erro de leiaute volta como um
código numérico da SEFAZ e vira adivinhação.

### 3.6 Cliente do `NFeAutorizacao` (médio)

O cliente que existe hoje fala com o **DistDFe**, que é o serviço de
distribuição — nacional, e serve para *receber* documentos. O de autorização é
outro serviço e é **por estado**.

A boa notícia: a estrutura é a mesma — SOAP com certificado —, e isso já
funciona no repositório. Muda o endereço, o envelope e o tratamento da
resposta.

### 3.7 Retransmissão e inutilização (médio)

- Nota emitida em contingência precisa ser transmitida em até **24 horas**;
- número reservado e não usado precisa ser **inutilizado** formalmente, senão
  fica um buraco na numeração que a fiscalização cobra.

Nenhum dos dois é difícil; os dois são obrigatórios.

---

## 4. Ordem sugerida

1. **Cadastro** — CSRT e credenciamento. Começa primeiro porque depende da
   SEFAZ, não de nós, e pode levar semanas.
2. **Campos e série** — `dhCont`, `xJust`, série de contingência.
3. **Montador do XML + XSD** — em homologação, contra o esquema oficial.
4. **Cliente do `NFeAutorizacao`** — primeira nota autorizada em homologação.
5. **QR de contingência e DANFE** — com a expressão obrigatória.
6. **Retransmissão em 24h e inutilização.**
7. **Produção**, uma loja por vez.

Chute honesto para os passos 2 a 6, com o cadastro já resolvido: **duas a três
semanas** de trabalho concentrado até a primeira nota autorizada em
homologação. O passo 1 corre em paralelo e não depende de nós.

---

## 5. O que muda depois de pronto

É a parte que costuma ser esquecida na decisão.

- **Toda nota técnica da SEFAZ passa a ser nossa.** Elas saem algumas vezes
  por ano, com prazo para adequação, e uma ignorada derruba a emissão de todos
  os clientes ao mesmo tempo.
- **Rejeição vira suporte nosso.** Hoje um código estranho da SEFAZ é problema
  da Focus; depois, é nosso.
- **A disponibilidade vira nossa.** Se a SEFAZ-RJ estiver instável, somos nós
  que explicamos.

Em troca: independência de fornecedor, custo por nota igual a zero, e
contingência de verdade sem licenciar nada.

---

## 6. Como decidir

- **Poucas lojas, contingência é conforto** → Comunicador da Focus. Paga-se
  para não acompanhar nota técnica.
- **Muitas lojas, "não dependemos de ninguém para emitir" é argumento de
  venda** → vale construir. 70% do caminho já está feito.
- **Em qualquer dos dois cenários** → comprovante não fiscal com fila
  resolve o balcão travado sem rede, e não atrapalha nenhuma das duas rotas.

O que não existe é a quarta opção — um documento de padrão próprio, que
pareça cupom fiscal sem ser. Está detalhado em
[`FLUXO_PAGAMENTO_EMISSAO_FISCAL.md`](FLUXO_PAGAMENTO_EMISSAO_FISCAL.md): já
foi tentado neste sistema e removido, porque o cupom saía com uma chave que a
SEFAZ jamais reconheceria. Quem responde por isso é o restaurante, no CNPJ
dele.
