# Emissão direta de NFC-e na SEFAZ: pendências

Este documento lista o trabalho para o StarChef montar, assinar e transmitir
NFC-e modelo 65 diretamente à SEFAZ, sem a API da Focus. O escopo inicial é o
Rio de Janeiro; outras UFs exigem levantamento próprio.

## Os três caminhos são diferentes

| Caminho | Quem autoriza a nota | Estado no StarChef |
| --- | --- | --- |
| Emissão online atual | API Focus NFe, que integra com a SEFAZ | Implementado no backend |
| Comunicador Offline Focus | Programa licenciado instalado no terminal; a Focus continua sendo a integração fiscal | Campos de configuração existem; agente local e protocolo ainda faltam |
| Integração direta | Backend ou agente StarChef conversa com os web services da SEFAZ/SVRS | Não implementada para autorização NFC-e |

Os campos “Emissão local” da tela configuram o uso planejado do Comunicador.
Ligar um campo não instala/licencia o programa e não cria, por si só, um emissor
local funcional. A tela e o fluxo de emissão só devem ser habilitados em uma
loja depois de existir o agente que conversa com o Comunicador e coordena as
notas.

## O que já existe

- `FiscalConfig`, `Invoice` e `InvoiceItem` guardam emitente, ambiente, modelo,
  dados fiscais dos itens, totais e pagamentos.
- `invoices/fiscal.py` calcula chave de acesso e QR Code online da NFC-e.
- `inbound_nfe/services/signer.py` contém primitives de assinatura XMLDSig
  usadas no domínio de documentos fiscais; isso não equivale a um emissor de
  NFC-e completo.
- `inbound_nfe/services/sefaz_client.py` consulta distribuição de DF-e
  (`NFeDistribuicaoDFe`/NSU), para receber documentos. Não autoriza NFC-e.
- `invoices/providers.py` transmite o documento pela API Focus. O payload atual
  não é o XML assinado de autorização da SEFAZ.
- A máquina de estados, a reconciliação da Focus e a impressão do DANFE cobrem
  a integração atual; não cobrem emissão offline direta.

## O que falta para emissão direta

### 1. Contrato fiscal e atualização contínua

- Fixar escopo inicial: NFC-e 65 no RJ, ambientes de homologação e produção,
  operações, meios de pagamento e contingências suportadas.
- Acompanhar o MOC, anexos, schemas e Notas Técnicas vigentes. Em 2026 há
  alterações independentes, por exemplo Reforma Tributária e CNPJ alfanumérico;
  não basta acompanhar uma única “NT vigente”.
- Confirmar com contabilidade e SEFAZ-RJ credenciamento do emitente, regras de
  responsável técnico/CSRT aplicáveis, CSC e eventuais exigências por UF. Não
  presumir que um requisito administrativo de outro estado também vale no RJ.
- Manter uma matriz versionada de schemas e datas de implantação em
  homologação e produção.

### 2. Montagem e validação do documento

- Montar o XML NFC-e completo a partir de `Invoice` e seus itens, incluindo
  identificação, emitente, destinatário quando aplicável, produtos, tributos,
  totais, pagamentos, informações adicionais e responsável técnico exigido.
- Validar o XML com o pacote XSD correto antes de transmitir.
- Aplicar regras de negócio e consistência dos totais, códigos fiscais,
  tributação, arredondamento e meios de pagamento sem inventar defaults fiscais.
- Assinar o nó correto com certificado A1 e validar assinatura, cadeia,
  validade do certificado, canonicalização e algoritmo segundo o leiaute
  vigente. As rotinas de assinatura de eventos não substituem estes testes.
- Criar testes com XMLs de referência oficiais e casos aceitos/recusados em
  homologação.

### 3. Autorização, consultas e eventos

- Implementar cliente SOAP para os serviços da UF/autorizador: status do
  serviço, autorização, consulta de recibo/lote, consulta por chave, eventos e
  inutilização. Para NFC-e do RJ, validar os endereços atuais da SVRS no portal
  oficial antes de configurar cada ambiente.
- Interpretar separadamente falha de transporte, lote recebido, autorização,
  rejeição, duplicidade e resposta ambígua. Timeout não prova que a SEFAZ não
  recebeu o documento: consultar antes de retransmitir.
- Implementar cancelamento como evento assinado e autorizado, com prazo e
  motivo validados; implementar inutilização de faixa quando cabível.
- Persistir XML enviado e retornado, protocolo, chave, recibos, eventos e
  respostas integrais necessárias à auditoria, com proteção de dados e acesso
  por conta/emitente.

### 4. Numeração, concorrência e operação em mais de um caixa

- Definir quem é a autoridade única de numeração quando vários terminais
  vendem ao mesmo CNPJ. Bloquear alocação concorrente no banco e nunca reutilizar
  número que possa ter chegado ao autorizador.
- Definir série online e série de contingência quando necessário; hoje, com
  Focus, o provedor administra a numeração real.
- Para emissão em terminal, criar agente fiscal local com fila durável,
  eleição/coordenação de um emissor por emitente, locks, recuperação após
  queda de energia e protocolo idempotente com o backend.
- Registrar a configuração e o certificado efetivamente usados em cada nota,
  mantendo segredos fora dos logs e evitando distribuí-los a terminais sem
  necessidade.

### 5. Contingência offline real e DANFE

- Implementar `tpEmis=9`, data/hora e justificativa de contingência, chave e
  numeração próprias, assinatura e QR Code offline conforme os manuais atuais.
- Guardar a NFC-e autorizada localmente como pendente; transmitir e reconciliar
  quando a conexão voltar, sem duplicar documento quando a resposta se perder.
- Controlar o prazo fiscal por UF. No RJ, a orientação oficial consultada
  informa transmissão até o primeiro dia útil subsequente à emissão em
  contingência; não tratar “24 horas” como regra universal.
- Gerar e imprimir DANFE NFC-e com a indicação de contingência exigida. Só
  marcar como autorizada/imprimível após confirmação válida, exceto a impressão
  offline que o manual permite com a indicação de pendência.
- Criar monitoramento e alertas para notas offline que se aproximem do prazo,
  rejeições posteriores, lacunas de numeração e certificado vencendo.

### 6. Homologação e liberação

1. Fechar com contador/SEFAZ-RJ o credenciamento, CSC, responsável técnico e
   regras operacionais aplicáveis ao CNPJ.
2. Implementar XML, validação XSD, assinatura e autorização online em
   homologação; cobrir autorização síncrona/assíncrona, rejeições e timeout.
3. Implementar consulta, cancelamento e inutilização; validar XML, DANFE e QR.
4. Implementar contingência offline, coordenação entre terminais, fila durável,
   recuperação e reconciliação.
5. Fazer piloto com emitente autorizado, comparar notas com a contabilidade e
   validar impressão e consultas públicas.
6. Liberar por feature flag, emitente e terminal; manter a Focus como retorno
   operacional até os critérios do piloto serem cumpridos.

Não há estimativa confiável de prazo antes de fechar os requisitos fiscais e
provar a primeira autorização em homologação. A manutenção das mudanças legais,
dos schemas, do suporte e da operação passa a ser responsabilidade do
StarChef.

## Referências oficiais consultadas

- [Portal Nacional NF-e: manuais](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=ndIjl+iEFdE=) — MOC, anexos, QR Code e contingência offline.
- [Portal Nacional NF-e: schemas](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=) — pacotes XSD publicados.
- [Portal Nacional NF-e: Notas Técnicas](https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY=) — mudanças por versão e cronograma.
- [Portal NFC-e da SVRS: documentos](https://dfe-portal.svrs.rs.gov.br/Nfce/Documentos) — serviços, MOC e documentação NFC-e.
- [SEFAZ-RJ: perguntas frequentes de NFC-e](https://portal.fazenda.rj.gov.br/dfe/wp-content/uploads/sites/17/2023/01/DF-e_NFC-e.pdf) — credenciamento, contingência e prazo no RJ.
- [Portal Nacional NF-e: relação de web services](https://www.nfe.fazenda.gov.br/portal/WebServices.aspx) — autorizadores e endereços publicados por UF.

As URLs, versões e datas de implantação devem ser reconferidas antes de cada
release fiscal. A orientação da SEFAZ-RJ e a validação do contador prevalecem
para o caso concreto do emitente.
