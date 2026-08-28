# Integração fiscal Brasil — Focus NFe

Para a explicação operacional de cada campo da tela, origem das credenciais e
checklist de homologação/produção, consulte
[`FOCUS_NFE_CONFIGURACAO.md`](FOCUS_NFE_CONFIGURACAO.md).

O StarChef possui dois provedores fiscais independentes:

- `manual`: não transmite; a API responde que a nota não foi emitida;
- `focus_nfe`: transmite NF-e (modelo 55) e NFC-e (modelo 65) pela API Focus NFe.

Selecionar a Focus não remove nem substitui o modo manual. O provedor é definido por restaurante no cadastro, em **Fiscal > Provedor fiscal**.

## Fluxo automático

1. Ao criar um restaurante com `focus_nfe`, o backend cria a `FiscalConfig` ligada à filial automática.
2. Após o commit, a tarefa Celery `invoices.sync_focus_company` lê a configuração Focus da conta e procura a empresa pelo CNPJ na Focus.
3. Se não existir, cria por `POST /v2/empresas`; se existir, atualiza por `PUT /v2/empresas/{id}`.
4. O StarChef salva separadamente `token_producao` e `token_homologacao`, sem expô-los na API ou no admin.
5. Se um webhook estiver configurado, cadastra o evento `nfe` automaticamente.
6. Alterações no restaurante ou na configuração fiscal enfileiram uma nova sincronização.
7. Ao emitir, o modelo 55 usa `/v2/nfe` e o modelo 65 usa `/v2/nfce`, sempre com uma referência única `starchef-<uuid>`.

A API de empresas da Focus opera apenas no servidor de produção, mesmo quando a empresa emitirá documentos em homologação. Para validar sem persistir, habilite **Simular cadastro da empresa** na configuração Focus da conta.

## Produtos e perfis fiscais

A Focus não oferece um CRUD de catálogo de produtos ou de perfis tributários. A fonte de verdade continua no StarChef:

- `FiscalProfile` mantém NCM, CEST, CFOP, origem, CSOSN/CST, ICMS, PIS, COFINS e tributos aproximados;
- cada `Product` pode apontar para um perfil fiscal;
- sem perfil no produto, é usado o perfil padrão da filial;
- cada emissão cria um snapshot em `InvoiceItem` e envia os itens completos no JSON da NF-e/NFC-e.

Assim, criar, editar ou trocar o perfil de um produto passa a valer automaticamente na próxima nota. Notas já emitidas preservam o snapshot original para auditoria.

## Configuração por conta

Administradores da conta configuram a integração em **Financeiro > Configuração Focus**. O endpoint correspondente é:

```text
GET/PATCH /api/v1/integrations/focus-nfe/config/
```

Token mestre e segredo do webhook são somente graváveis: a API informa se existem, mas nunca devolve seus valores. Uma conta não lê nem altera a configuração de outra.

## Bootstrap pelas variáveis de ambiente

As variáveis abaixo são usadas somente como bootstrap:

```dotenv
FOCUS_NFE_MASTER_TOKEN=TOKEN_DA_CONTA_INTEGRADORA
FOCUS_NFE_PRODUCTION_URL=https://api.focusnfe.com.br
FOCUS_NFE_HOMOLOGATION_URL=https://homologacao.focusnfe.com.br
FOCUS_NFE_TIMEOUT_SECONDS=30
FOCUS_NFE_AUTO_SYNC=True
FOCUS_NFE_COMPANY_DRY_RUN=False

# Opcionais para NF-e assíncrona
FOCUS_NFE_WEBHOOK_URL=https://api.seu-dominio.com/api/v1/integrations/focus-nfe/webhook/
FOCUS_NFE_WEBHOOK_AUTHORIZATION=UM_SEGREDO_FORTE
FOCUS_NFE_WEBHOOK_AUTHORIZATION_HEADER=Authorization
```

Ao aplicar a migration, os valores são copiados para todas as contas existentes. Ao criar uma conta nova, um signal cria sua configuração e copia os valores vigentes. Mesmo que estejam todos vazios, o registro por conta é criado.

Depois da criação, a API e a integração usam exclusivamente o registro persistido da conta. Alterar o `.env` não altera configurações já existentes e não funciona como fallback em runtime.

`FOCUS_NFE_MASTER_TOKEN` é o token da conta integradora usado no bootstrap. Não use nele o token individual de um restaurante. Os tokens individuais são obtidos automaticamente na resposta da API de empresas.

O `.env` real é ignorado pelo Git. O contrato versionado está em `.env.example`.

## Cadastro do restaurante

Para usar a Focus:

1. Cadastre razão social, nome fantasia, CNPJ, endereço, cidade, UF e CEP.
2. Escolha **Focus NFe** em **Provedor fiscal**.
3. Salve o restaurante.
4. Na configuração fiscal, escolha NF-e ou NFC-e, ambiente, CRT e série.
5. Para emissão real, envie o certificado A1 `.pfx/.p12` e sua senha.
6. Para NFC-e, informe também CSC e ID do CSC do ambiente selecionado.
7. Salve ou use **Sincronizar agora** e confira o indicador de status.

O PFX e a senha ficam disponíveis somente enquanto a tarefa precisa sincronizá-los. Depois de uma resposta bem-sucedida da Focus, ambos são apagados do StarChef.

## Endpoints administrativos

Com o módulo financeiro habilitado:

```text
POST   /api/v1/fiscal/config/{id}/focus-sync/       cria ou atualiza agora
POST   /api/v1/fiscal/config/{id}/focus-refresh/    consulta a empresa remota
DELETE /api/v1/fiscal/config/{id}/focus-company/    exclui a empresa remota
POST   /api/v1/invoices/{id}/refresh-status/        consulta o documento
POST   /api/v1/integrations/focus-nfe/webhook/      recebe eventos da Focus
GET    /api/v1/integrations/focus-nfe/config/       consulta a configuração da conta
PATCH  /api/v1/integrations/focus-nfe/config/       altera a configuração da conta
```

Quando não há configuração fiscal ativa, o provedor é manual/desconhecido ou faltam URL/token Focus para o ambiente selecionado, `POST /api/v1/invoices/emit/` não cria uma nota local nem tenta transmitir. Ele responde HTTP 200:

```json
{
  "emitted": false,
  "message": "Nota fiscal nao emitida: ..."
}
```

A exclusão remota é irreversível, restrita a administrador e exige o corpo:

```json
{"confirm_cnpj": "11222333000181"}
```

Excluir ou desativar um restaurante localmente não exclui sua empresa da Focus.

## Deploy

Depois de atualizar a imagem:

```bash
docker compose pull
docker compose up -d
docker compose exec backend python manage.py migrate --noinput
```

O `celery_worker` precisa estar ativo para o cadastro automático. Confira com:

```bash
docker compose ps
docker compose logs --tail=200 celery_worker
```

## Diagnóstico

- `not_configured`: ainda não foi enviada à Focus;
- `pending`: tarefa enfileirada;
- `synced`: empresa e tokens sincronizados;
- `error`: consulte `focus_sync_error`, corrija o cadastro e sincronize novamente.

Erros comuns são token mestre ausente, CNPJ incompleto, certificado inválido/vencido, senha incorreta, CSC ausente e Celery/Redis indisponível.

## Referências oficiais

- [Introdução](https://doc.focusnfe.com.br/reference/introducao)
- [Autenticação](https://doc.focusnfe.com.br/reference/autenticacao)
- [Ambientes](https://doc.focusnfe.com.br/reference/ambiente)
- [API de empresas](https://doc.focusnfe.com.br/reference/empresas)
- [Criar empresa](https://doc.focusnfe.com.br/reference/criar_empresa)
- [Emitir NF-e](https://doc.focusnfe.com.br/reference/emitir_nfe)
- [Emitir NFC-e](https://doc.focusnfe.com.br/reference/emitir_nfce)
- [Webhooks](https://doc.focusnfe.com.br/reference/webhooks)
- [Campos de itens NF-e/NFC-e](https://campos.focusnfe.com.br/nfe/ItemNotaFiscalXML.html)
