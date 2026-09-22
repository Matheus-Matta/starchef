# Guia de Merge e Deploy para Produção — NF-e de Entrada (Inbound NF-e)

> **Documento para o desenvolvedor responsável pelo Merge e Deploy da branch.**  
> Este guia detalha exatamente o que foi implementado, o porquê de cada mudança, os arquivos modificados, como fazer o merge com segurança e como migrar os dados para o ambiente de produção sem trabalho braçal e sem erros de SEFAZ.

---

## ⚡ 1. Resumo Executivo (TL;DR)

O objetivo desta entrega foi estabilizar o módulo de **NF-e de Entrada**, permitindo a **exportação e importação em lote (.ZIP)** completa de notas fiscais entre ambientes (ex: de homologação para produção vazia), garantindo a persistência do **NSU (Número Sequencial Único)** e do cursor de sincronização da SEFAZ (`ult_nsu`).

### Principais Benefícios:
1. **Migração em 1 Clique com Manifesto:** Ao exportar as notas em `.zip`, o sistema gera automaticamente um arquivo `manifest.json` com os NSUs originais de cada nota e o último NSU consultado na SEFAZ. Na importação em produção, o sistema restaura tudo e atualiza o `DFeSyncState`.
2. **Proteção Contra Rejeição 656 (Consumo Indevido):** Como o cursor da SEFAZ (`ult_nsu`) é restaurado na produção, o sistema não tenta reconsultar notas antigas na SEFAZ nem é bloqueado por excesso de consultas.
3. **Fim do "XML Resumo Sobrescrevendo XML Completo":** Corrigido o problema onde reimportar um resumo `<resNFe>` apagava o `full_xml` de notas já existentes.
4. **Escopo de Restaurante Unificado:** Removido o seletor duplicado da tela; a tela agora sincroniza de forma reativa com o restaurante selecionado na barra lateral global (`starchef-restaurant-scope`).
5. **Acesso Fácil a "Dar Ciência" e "Baixar XML":** Botões visíveis diretamente na linha, no menu de três pontos e dentro do modal da nota.
6. **Zero Migrations & Zero Novas Libs:** Nenhuma tabela foi alterada e nenhum pacote novo foi adicionado.

---

## 📊 2. Tabela de Arquivos Alterados (Apenas 5 arquivos)

| Arquivo | Superfície | O que mudou resumidamente |
| :--- | :--- | :--- |
| `backend/apps/inbound_nfe/views.py` | Backend | Gera `manifest.json` no ZIP; corrige filtro de datas (`__date__lte`); aceita filtros via POST. |
| `backend/apps/inbound_nfe/services/importer.py` | Backend | Lê `manifest.json` no ZIP; restaura NSU e estado de manifestação; atualiza `DFeSyncState`. |
| `backend/apps/inbound_nfe/tasks.py` | Backend | Preenche NSU de nota existente se chegar resumo da SEFAZ (`doc.nsu`). |
| `backend/apps/inbound_nfe/services/manifestation.py` | Backend | Preenche NSU imediatamente após buscar XML completo via chave (`consChNFe`). |
| `frontend/src/views/ResourceListViewPro.vue` | Frontend | Conecta escopo à sidebar; exibe botões de ciência/download; decodifica erro em Blob; ativa rolagem fluida de tela. |
| `frontend/src/styles/inbound-nfe-list.css` | Frontend | Regras de rolagem fluida e cabeçalho sticky (`th`) para expandir espaço útil da tabela de notas. |

---

## 🔍 3. Detalhamento Técnico das Modificações

### A. Backend

#### 1. `backend/apps/inbound_nfe/views.py`
- **Inclusão do `manifest.json` na Exportação em Lote:**  
  No método `export_xml`, ao gerar o arquivo ZIP, é consultado o `DFeSyncState` atual da conta/restaurante. É gravado um arquivo `manifest.json` dentro do ZIP contendo:
  ```json
  {
    "version": "1.0",
    "ult_nsu": "000000000000142",
    "max_nsu": "000000000000142",
    "notes": {
      "33260901438784002302550070002834371262795621": {
        "nsu": "000000000000141",
        "status": "pending_mapping",
        "manifestation_status": "science_registered"
      }
    }
  }
  ```
- **Correção no Filtro de Datas:**  
  O filtro de data final usava `issue_date__lte=issue_before`. Como `issue_date` é `DateTimeField` e a data vinha como `2026-09-22`, qualquer nota emitida às `10:00` do dia 22 era descartada. Foi ajustado para `issue_date__date__lte=issue_before[:10]`.
- **Leitura de Filtros em Requisições POST:**  
  O método `get_queryset()` agora lê `mapping_filter` tanto dos query params quanto do body (`request.data`), permitindo que a exportação respeite a aba selecionada na tela.

#### 2. `backend/apps/inbound_nfe/services/importer.py`
- **Importação com Leitura do Manifesto:**  
  Ao processar um arquivo `.zip`, o importador verifica se existe um `manifest.json`. Se existir:
  1. Atualiza o `DFeSyncState` daquele restaurante com o `ult_nsu` e `max_nsu` indicados.
  2. Passa os metadados (`manifest_meta`) para cada XML processado, restaurando o `nsu` original e o `manifestation_status`.
- **Tratamento Seguro de XML Completo vs Resumo:**  
  Se uma nota já tiver `full_xml`, o envio acidental de um XML de resumo (`<resNFe>`) não apaga mais os dados completos nem muda o status da nota para pendente de produtos vazios.
- **Sanitização de Nomes de Arquivo no ZIP:**  
  Ignora diretórios internos, arquivos ocultos do macOS (`__MACOSX`, `.DS_Store`) e aceita extensões `.xml` ou `.XML`.
- **Total Retrocompatibilidade:**  
  Caso o usuário envie um `.zip` gerado por outro sistema ou sem `manifest.json`, o importador funciona normalmente importando cada XML de forma avulsa.

#### 3. `backend/apps/inbound_nfe/tasks.py` e `manifestation.py`
- **Garantia de Preenchimento de NSU:**  
  Quando a SEFAZ entrega uma atualização de nota (via resumo ou consulta de chave), se o registro de `InboundNFe` estiver sem NSU ou com `MANUAL`, o campo `nsu` é atualizado com o NSU oficial do documento (`doc.nsu`).

---

### B. Frontend

#### `frontend/src/views/ResourceListViewPro.vue` e `inbound-nfe-list.css`
- **Rolagem Fluida da Página e Tabela Expandida (Monitores Menores):**
  - Anteriormente, a tabela usava altura fixa interna flex, deixando a área de visualização das notas espremida (apenas 2 a 4 linhas) quando os cartões da SEFAZ estavam visíveis em telas menores ou notebooks.
  - Ajustado para que o módulo de NF-e acompanhe o scroll natural da página (`.app-content`). Ao rolar o scroll, o topo (título e os 4 cartões da SEFAZ) sobe e sai do campo de visão, dando **100% da altura da tela** para a tabela de notas.
  - As colunas da tabela (`<th>`) usam `position: sticky` no topo do scroll para que os títulos das colunas permaneçam visíveis ao navegar pelas notas.
- **Escopo Único de Restaurante:**  
  Removido o `<InboundRestaurantSelector>` redundante no cabeçalho da página de NF-e. Agora `inboundRestaurantId` é uma propriedade reativa ligada a `getBrowserValue("starchef-restaurant-scope")`. Ao trocar o restaurante na sidebar lateral, a listagem e as contagens de notas recarregam automaticamente.
- **Botões "Dar Ciência" e "Baixar XML":**  
  - Se a nota for apenas resumo (`status === 'summary'` ou sem itens), exibe o botão **"Dar Ciência"** (`pi-bolt`).
  - Se a ciência já foi registrada mas o XML ainda não baixou, exibe **"Baixar XML"** (`pi-cloud-download`).
  - Disponíveis tanto na coluna de ações da tabela quanto no cabeçalho do modal de detalhes da nota.
- **Tratamento de Erros de Download em Formato Blob:**  
  Quando o backend retorna erro HTTP (ex: 400 ou 404) para endpoints que retornam arquivo, o Axios entrega um `Blob`. A função `exportInboundXml` agora faz o parse do JSON contido no Blob e mostra a mensagem de erro real no toast (ex: *"Nenhum arquivo XML disponível para as notas selecionadas"*).

---

## 🔀 4. Como Fazer o Merge (Passo a Passo)

### Passo 1: Trazer as alterações para a sua branch de trabalho
```bash
# Na raiz do projeto StarChef:
git status

# Para fazer o merge na branch de release/produção:
git checkout release/v3.0.0
git merge fixing/nfe-exportacao
```

### Passo 2: Executar as validações de integridade
Execute os três comandos obrigatórios do projeto:
```bash
# 1. Catraca de tamanho de arquivo (deve retornar código 0):
python scripts/check_tamanho_de_arquivo.py

# 2. Verificação do Django (deve retornar 0 issues):
python manage.py check

# 3. Linter do Frontend (deve retornar 0 erros):
npm run lint --prefix frontend
```

### Passo 3: Subir os serviços
Não há novas migrations para rodar (`manage.py migrate` não gerará novas tabelas).
```bash
# No servidor / containers:
docker compose restart backend celery_worker
# No frontend, rebuild padrão de produção se aplicável
```

---

## 📦 5. Como Fazer a Migração de Dados para Produção (Zero Trabalho)

Se o banco de produção estiver vazio ou sem as notas recentes de homologação/teste:

### Etapa 1: Exportar no ambiente de teste/homologação
1. Abra a tela de **Notas Fiscais (Entrada)**.
2. Certifique-se de que a unidade/restaurante desejada está selecionada na barra lateral.
3. Clique no botão **"Exportar Tudo (XML)"** no canto superior direito.
4. Um arquivo chamado `nfe_export_AAAAMMDD_HHMMSS.zip` será baixado.
   *(Dentro dele estarão todos os XMLs das notas + o `manifest.json` com os NSUs).*

### Etapa 2: Importar no ambiente de produção
1. Acesse o sistema em **Produção**.
2. Selecione a unidade correspondente na barra lateral.
3. Vá em **Notas Fiscais (Entrada)** e clique em **"Importar XMLs"**.
4. Selecione o arquivo `.zip` baixado na Etapa 1.
5. **O que o sistema faz automaticamente:**
   - Cadastra todas as notas fiscais e seus respectivos produtos.
   - Restaura o **NSU original** de cada uma.
   - Restaura o status de manifestação (ex: Ciência da Operação já registrada).
   - Atualiza o `DFeSyncState` da empresa com o `ult_nsu` mais alto.
6. **Resultado:** Ao clicar em "Sincronizar SEFAZ" em produção, o sistema saberá exatamente onde parou e **não sofrerá rejeição 656 (Consumo Indevido)**.

---

## ❓ 6. Perguntas Frequentes do Desenvolvedor

**P: Preciso mexer no `catalog.py` ou `decisions.py` da sincronização?**  
*R:* Não. Não criamos nenhum model novo. Todos os dados usam os models `InboundNFe`, `InboundNFeItem`, `DFeDistributionDocument` e `DFeSyncState` já existentes.

**P: A nota Leroy Merlin chave `...2795621` que antes era #138 agora aparece como #141. Por quê?**  
*R:* A SEFAZ entrega resumos e eventos em lotes com numeração crescente. Essa nota foi entregue pela primeira vez no lote/NSU 138 (como resumo). Mais tarde, a SEFAZ entregou o evento completo no lote/NSU 141. O sistema mantém o NSU mais recente para rastreabilidade real perante a SEFAZ.

**P: E se o usuário subir um `.zip` com notas de outros restaurantes?**  
*R:* O importador vincula as notas ao restaurante ativo selecionado no momento da importação, mantendo o isolamento multi-tenant seguro.

**P: E se alguém importar notas duplicadas?**  
*R:* O sistema usa `access_key` (chave de 44 dígitos) como identificador único. Se a nota já existir, ele apenas atualiza campos ausentes e não duplica produtos.
