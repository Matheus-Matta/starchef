# Configuração da Focus NFe no StarChef

Este guia explica a configuração da conta Focus NFe, o cadastro fiscal do
restaurante e, principalmente, de onde vem cada credencial. Ele cobre NF-e
(modelo 55) e NFC-e (modelo 65) nos ambientes de homologação e produção.

> **Aviso fiscal:** confirme CRT, CFOP, NCM, CSOSN/CST, PIS, COFINS, série e
> numeração com a contabilidade. O sistema transporta essas informações, mas
> não decide o enquadramento tributário da empresa.

## Visão geral

A integração possui três níveis diferentes:

1. **Conta StarChef:** guarda o token mestre, as URLs da Focus e o webhook em
   **Financeiro > Configuração Focus**. Cada conta StarChef pode usar uma conta
   Focus diferente.
2. **Restaurante/filial:** guarda CNPJ, IE, ambiente, certificado, CSC, série e
   o token individual da empresa retornado pela Focus.
3. **Produtos:** guardam NCM, CEST, CFOP, origem, CSOSN/CST e alíquotas por meio
   dos perfis fiscais.

O token mestre não é usado para emitir diretamente. Ele administra empresas na
Focus. Depois de **Sincronizar agora**, o StarChef recebe os tokens individuais
de produção e homologação da empresa e usa o token do ambiente selecionado.

## O que é necessário por documento

| Item | NFC-e 65 | NF-e 55 | Onde obter |
|---|---:|---:|---|
| CNPJ, IE, endereço e CRT | Sim | Sim | Empresa, contador e SEFAZ |
| Certificado A1 e senha | Sim | Sim | Certificadora ICP-Brasil ou responsável atual |
| CSC e ID do CSC | Sim | Não | Portal da SEFAZ da UF |
| Série e próximo número | Sim | Sim | Emissor anterior, Focus ou contador |
| Perfis fiscais dos produtos | Sim | Sim | Contador |
| Token mestre Focus | Sim | Sim | Painel/suporte da conta integradora Focus |
| Token individual do ambiente | Automático | Automático | Retornado pela Focus na sincronização |
| Webhook | Opcional | Recomendado | URL pública da própria API StarChef |

## Configuração da conta Focus

Acesse **Financeiro > Configuração Focus**. Os valores ficam isolados por conta
StarChef. Alterar o `.env` depois da criação da conta não altera essa tela e não
funciona como fallback durante a emissão.

### Token mestre

Credencial da conta integradora usada para consultar, criar e atualizar as
empresas pela API `/v2/empresas`.

- Obtenha no painel de API da Focus NFe ou com o suporte/gerente da conta Focus.
- A credencial precisa ter acesso à API de empresas/subcontas.
- Não confunda com `token_producao` ou `token_homologacao` de um restaurante.
- O StarChef não devolve o token pela API; a tela informa apenas se está
  configurado. Quando já existe um valor, o campo vazio mostra `••••••••`
  apenas como referência visual. As bolinhas não são o token e não são enviadas
  ao backend; deixar o campo sem digitar preserva o valor atual.

### URL de produção

Valor oficial:

```text
https://api.focusnfe.com.br
```

Além das emissões de produção, a API de empresas da Focus opera nesse servidor.
Por isso esta URL também é necessária para cadastrar/sincronizar uma empresa
que emitirá documentos apenas em homologação.

### URL de homologação

Valor oficial:

```text
https://homologacao.focusnfe.com.br
```

É usada para emitir documentos de teste, sem validade fiscal ou tributária.
Não troque para produção apenas para conseguir gerar uma DANFE de teste.

### Timeout

Tempo máximo, em segundos, que o backend espera por uma resposta HTTP da Focus.
O padrão é 30 segundos. Aumentar o valor não corrige certificado, CSC ou dados
fiscais inválidos.

### Sincronização automática

Quando ativada, mudanças no restaurante ou na configuração fiscal agendam a
criação/atualização da empresa na Focus. O Celery e o Redis precisam estar
ativos. O botão **Sincronizar agora** permite executar o mesmo fluxo sob
demanda.

### Simular cadastro da empresa (`dry_run`)

Envia `dry_run=1` à API de empresas. A Focus valida a solicitação, mas não
persiste a criação ou alteração.

- Use somente para diagnosticar o payload de cadastro.
- Deixe **desativado** para preparar uma empresa que realmente emitirá em
  homologação ou produção.
- `dry_run` não transforma uma emissão em homologação; ambiente fiscal e
  simulação de cadastro são conceitos diferentes.

O botão **Sincronizar agora** informa explicitamente quando houve somente uma
validação em `dry_run`. Nesse caso a resposta usa `synced: false` e a empresa
continua como não sincronizada. Fora do modo de simulação, o StarChef só marca
sucesso depois que a resposta da Focus contém uma empresa identificável ou que
uma nova consulta por CNPJ confirma a persistência.

### Diagnóstico da sincronização

Os erros da Focus aparecem no status fiscal do restaurante e na resposta do
botão manual. As mensagens distinguem, entre outros casos:

- Token Principal de Produção ausente ou recusado;
- dados obrigatórios do emitente ausentes ou inválidos;
- dados ou certificado recusados pela Focus (`400`/`422`);
- timeout, indisponibilidade e limite temporário de requisições;
- resposta aceita sem empresa confirmada por ID/CNPJ.

O retorno inclui um código estável em `error.code`, o HTTP recebido da Focus em
`focus_status_code` quando disponível e a configuração atual em `config`. Tokens,
CSC, certificado e senhas continuam sendo somente escrita e nunca são incluídos
no erro.

### URL do webhook

Endpoint público no qual a Focus enviará atualizações assíncronas:

```text
https://api.starchef.com.br/api/v1/integrations/focus-nfe/webhook/
```

A URL precisa:

- estar acessível pela internet via HTTPS;
- aceitar `POST` sem sessão de usuário;
- chegar ao backend StarChef, sem ser interceptada pelo frontend;
- responder com HTTP 2xx quando a notificação for processada.

A NFC-e normalmente é processada de forma síncrona. Para NF-e, que pode ficar
em processamento, o webhook é recomendado. Se a entrega falhar, a Focus faz
novas tentativas segundo a política dela.

### Cabeçalho e segredo do webhook

O segredo é um valor aleatório definido pelo administrador do StarChef; ele
não vem da SEFAZ. A Focus envia esse valor no cabeçalho do webhook e o StarChef
compara os dois valores antes de aceitar a atualização.

Configuração recomendada:

```text
Cabeçalho: Authorization
Segredo: valor longo, aleatório e exclusivo da conta
```

Não use o token mestre como segredo do webhook. A documentação pública da
Focus descreve o campo `authorization`; portanto, mantenha o cabeçalho
`Authorization`, salvo se houver um contrato diferente confirmado com a Focus.
O segredo também é somente escrita no frontend.

## Configuração fiscal do restaurante

### Provedor fiscal

Selecione **Focus NFe**. O provedor **Manual** não transmite para a SEFAZ; nesse
caso a API responde HTTP 200 com `emitted: false` e nenhuma nota é criada.

### Modelo do documento

- **NFC-e, modelo 65:** venda presencial ao consumidor; usa CSC e QR Code.
- **NF-e, modelo 55:** operações que exigem NF-e; não usa CSC e geralmente
  exige mais informações do destinatário e da operação.
- SAT/CF-e não é suportado pelo provedor Focus desta integração.

### Ambiente

- **Homologação (`2`):** testes, sem valor fiscal.
- **Produção (`1`):** documento com validade fiscal e tributária.

Os tokens e os parâmetros de CSC, série e numeração são separados por
ambiente. Teste todo o fluxo em homologação antes de selecionar produção.

### Regime tributário (CRT)

É o enquadramento do emitente:

- `1`: Simples Nacional;
- `2`: Simples Nacional — excesso de sublimite;
- `3`: Regime Normal;
- `4`: Simples Nacional — MEI, aceito pela Focus, mas ainda não oferecido pelo
  modelo atual do StarChef.

Confirme com o contador. A situação de optante também pode ser consultada no
Portal do Simples Nacional. Se a empresa for MEI, o StarChef precisa ser
ajustado para aceitar CRT `4` antes da emissão.

### Série e próximo número

Identificam a sequência fiscal do estabelecimento e do modelo. Consulte o
emissor anterior, o painel da Focus, as notas já autorizadas/inutilizadas ou a
contabilidade.

- Se nunca houve emissão naquele ambiente e naquela série, normalmente começa
  com série `1` e próximo número `1`.
- Se já houve emissão, informe o número seguinte ao último usado.
- Não copie automaticamente a sequência de produção para homologação.
- Uma combinação CNPJ + modelo + série + número já utilizada pode ser
  rejeitada por duplicidade.

Ao sincronizar, o StarChef envia esses dados aos campos de série e próximo
número do ambiente escolhido na empresa Focus.

### Dados do emitente

Preencha CNPJ, inscrição estadual, razão social, nome fantasia, logradouro,
**número do endereço**, bairro, município, código IBGE, UF e CEP exatamente como constam
no cadastro fiscal. O CNPJ deve ter 14 dígitos e precisa coincidir com o
certificado. A inscrição estadual aceita de 2 a 14 dígitos ou o texto `ISENTO`.

Antes de chamar a API da Focus, **Sincronizar agora** valida razão social, CNPJ,
IE, logradouro, número, bairro, município, CEP e UF. Para NFC-e também exige CSC e ID do
CSC. Na primeira sincronização também exige o certificado A1 e sua senha; depois
que a empresa já está vinculada, a Focus conserva o certificado e o StarChef
não exige um novo upload em toda atualização. Ausência ou formato inválido
responde HTTP 400, grava o motivo em
`focus_sync_error` e mantém a empresa como não sincronizada; nenhuma chamada
externa é feita enquanto houver essas pendências.

## Certificado e campos da NFC-e

### Certificado A1 (`.pfx`/`.p12`)

É a identidade digital usada para assinar o documento fiscal e autenticar a
empresa perante os serviços fiscais. Para este fluxo é necessário um
certificado de pessoa jurídica do tipo A1, exportável como `.pfx` ou `.p12`.

Onde obter:

1. verifique se o contador ou o emissor atual já possui o A1 da empresa;
2. caso não exista, compre de uma Autoridade Certificadora credenciada na
   ICP-Brasil;
3. faça o download/exportação com a chave privada e guarde a senha criada nesse
   processo.

O certificado deve estar válido e pertencer ao mesmo CNPJ. Certificado A3 em
cartão ou token físico não é aceito pelo upload atual.

No StarChef, o arquivo é convertido para Base64 e enviado à API de empresas da
Focus. Após uma sincronização bem-sucedida, o arquivo e a senha são removidos
do banco do StarChef; a Focus mantém o certificado necessário à emissão. Se a
sincronização falhar, os dados permanecem temporariamente para permitir nova
tentativa. Corrija o erro e sincronize novamente o quanto antes.

### Senha do certificado A1

É a senha que protege o arquivo PFX/P12, definida na emissão ou exportação. Não
é a senha da Focus, do gov.br, da SEFAZ ou do contador. Arquivo e senha precisam
ser enviados juntos na mesma operação.

Nunca envie o PFX ou a senha por chat, e-mail aberto ou chamado público.

### ID do CSC (`idToken`)

Número que identifica qual CSC está sendo usado no cadastro da SEFAZ. Exemplos
visuais comuns são `1` ou `000001`, mas deve ser copiado exatamente do portal
estadual. O ID não é o próprio segredo.

### CSC, segredo da NFC-e

O Código de Segurança do Contribuinte participa da assinatura/hash do QR Code
da NFC-e. Ele é necessário apenas no modelo 65.

Onde obter:

1. acesse o portal da SEFAZ da UF do emitente;
2. procure **NFC-e**, **Credenciamento** ou **Gerenciar CSC**;
3. selecione o ambiente de homologação ou produção;
4. gere/copie o par **ID do token + CSC**.

O CSC de homologação é diferente do CSC de produção. Ele não é o token da
Focus, não é o certificado e não deve ser inventado. Alguns estados exigem que
o contribuinte esteja previamente credenciado como emissor de NFC-e.

O StarChef mantém o CSC como segredo de escrita e o envia para a empresa Focus
do ambiente selecionado. Ao editar, deixe o campo vazio para preservar o valor
existente.

### Referência do certificado A1

Campo legado para identificar externamente um certificado em integrações
manuais, por exemplo um alias ou identificador de um cofre de certificados.

Na integração Focus atual:

- não é enviado à Focus;
- não substitui o upload do `.pfx`/`.p12`;
- não é necessário para sincronizar ou emitir;
- pode permanecer vazio.

### URL de consulta do QR Code da UF

É a URL base oficial na qual o QR Code da NFC-e será consultado pelo consumidor.
O StarChef a usa para montar o QR Code local do DANFE antes/de forma independente
da resposta da Focus. Quando a Focus devolve `qrcode_url`, esse valor atualiza o
QR da nota emitida.

Obtenha a URL na documentação NFC-e da SEFAZ da UF ou no Portal Nacional/SVRS.
Use a URL de **QR Code**, não uma URL de webservice SOAP. Produção e homologação
podem ter endereços diferentes. Não copie uma URL de outra UF.

Se esse campo estiver vazio, o QR local será incompleto até que a Focus devolva
o QR autorizado. Para uma impressão consistente, configure a URL correta do
ambiente.

### URL do portal de consulta por chave

É a página pública exibida no DANFE para o consumidor consultar a nota digitando
a chave de acesso. Também vem do portal NFC-e da SEFAZ da UF.

Ela é diferente de:

- URL de QR Code;
- URL dos webservices de autorização;
- URL da API Focus;
- URL do webhook StarChef.

O StarChef imprime essa URL no DANFE. Informe a página pública correspondente à
UF e ao ambiente selecionado.

## Perfis fiscais dos produtos

Uma empresa sincronizada ainda pode ter notas rejeitadas se os itens estiverem
fiscalmente incompletos. Configure um perfil padrão por filial e/ou um perfil
em cada produto com:

- NCM real de oito dígitos;
- CEST, quando aplicável;
- CFOP;
- origem da mercadoria;
- CSOSN para Simples Nacional ou CST ICMS para regime normal;
- CST e alíquotas de PIS/COFINS;
- percentual aproximado de tributos.

Esses valores devem ser fornecidos ou validados pela contabilidade.

## Fluxo recomendado de homologação

1. Preencha **Financeiro > Configuração Focus** com token mestre e URLs oficiais.
2. Ative sincronização automática e desative `dry_run`.
3. Cadastre o restaurante com provedor Focus, modelo 65 e homologação.
4. Preencha dados fiscais, certificado A1, CSC/ID de homologação, série e número.
5. Configure os perfis fiscais dos produtos.
6. Salve e clique em **Sincronizar agora**.
7. Confirme o status **Sincronizado** e a ausência de mensagem de erro.
8. Configure uma impressora ativa/master no PDV.
9. Faça um pedido de teste, registre o pagamento e emita a NFC-e.
10. Confira status autorizado, protocolo, chave, QR Code e a identificação
    **SEM VALOR FISCAL — HOMOLOGAÇÃO** no DANFE.

Não mude para produção enquanto houver rejeições em homologação. Ao migrar,
obtenha/valide o CSC de produção e confirme a série e a numeração de produção.

## Diagnóstico rápido

| Sintoma | Verificação |
|---|---|
| `Nota fiscal não emitida` com HTTP 200 | Provedor, URLs da conta e token do ambiente |
| `Token mestre ... não configurado` | Financeiro > Configuração Focus |
| `Empresa sem token para o ambiente` | Desative `dry_run` e sincronize novamente |
| `Já existe um registro com estes dados` ao sincronizar empresa | O StarChef consulta novamente pelo CNPJ e vincula o cadastro existente. Se continuar, confirme que a empresa pertence à mesma conta Focus do Token Principal de Produção |
| `Certificado inválido/vencido` | CNPJ, validade, arquivo A1 e senha |
| `Código CSC não configurado` | CSC e ID do mesmo ambiente na SEFAZ |
| Rejeição de item | NCM, CFOP, CSOSN/CST, PIS e COFINS |
| `cMun` inesperado; esperado `xBairro` | Preencha o bairro do emitente, salve, sincronize a empresa e reenvie a nota |
| Duplicidade na emissão da nota | Série e próximo número já utilizados |
| QR Code inválido | CSC/ID, ambiente e URL de QR Code da UF |
| NF-e permanece processando | Webhook, segredo, logs e consulta de status |
| DANFE não imprime | Impressora ativa/master e agente local do PDV |

## Segurança e operação

- Nunca versione `.env`, PFX, senhas, CSC ou tokens.
- Use segredos diferentes para Focus, certificado e webhook.
- Restrinja a tela fiscal a administradores autorizados.
- Troque/revogue credenciais expostas.
- Renove o certificado antes do vencimento e sincronize o novo A1.
- Homologação não possui validade fiscal; produção possui.
- O `.env` serve apenas para popular inicialmente a configuração por conta.

## Referências oficiais

- [Ambientes Focus NFe](https://doc.focusnfe.com.br/reference/ambiente)
- [Autenticação Focus NFe](https://doc.focusnfe.com.br/reference/autenticacao)
- [API de empresas](https://doc.focusnfe.com.br/reference/empresas)
- [Criar empresa e enviar certificado/CSC](https://doc.focusnfe.com.br/reference/criar_empresa)
- [Emitir NFC-e](https://doc.focusnfe.com.br/reference/emitir_nfce)
- [Emitir NF-e](https://doc.focusnfe.com.br/reference/emitir_nfe)
- [Webhooks Focus NFe](https://doc.focusnfe.com.br/reference/webhooks)
- [Criar webhook](https://doc.focusnfe.com.br/reference/criar_webhook)
- [Certificação digital ICP-Brasil](https://www.gov.br/iti/pt-br/acesso-a-informacao/perguntas-frequentes/certificacao-digital)
- [Portal do Simples Nacional](https://www8.receita.fazenda.gov.br/SimplesNacional/)
- [Portal Nacional/SVRS da NFC-e](https://dfe-portal.svrs.rs.gov.br/Nfce)
- [Serviços NFC-e por autorizador e ambiente](https://dfe-portal.svrs.rs.gov.br/Nfce/Servicos)
