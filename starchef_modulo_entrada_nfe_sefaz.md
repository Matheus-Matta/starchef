# StarChef — Módulo de Entrada Automática de NF-e via SEFAZ

## 1. Objetivo

Adicionar ao StarChef um módulo isolado para:

1. Consultar automaticamente as NF-e modelo 55 emitidas contra o CNPJ da empresa.
2. Baixar os documentos pela SEFAZ usando `NFeDistribuicaoDFe`.
3. Controlar corretamente o NSU de distribuição.
4. Executar Manifestação do Destinatário quando necessário.
5. Obter e armazenar o XML completo da NF-e.
6. Ler fornecedor, produtos, quantidades, unidades, valores e dados fiscais.
7. Fazer o DE/PARA entre o item informado pelo fornecedor e o cadastro interno do StarChef.
8. Permitir conferência física do recebimento.
9. Gerar entrada no estoque usando a estrutura já existente de `Ingredient` e `StockMovement`.
10. Atualizar custo médio e, consequentemente, custos das fichas técnicas e produtos.

O módulo deve ser implementado sem reestruturar o sistema atual.

A regra arquitetural principal será:

```text
NF-e recebida
    ↓
InboundNFe
    ↓
InboundNFeItem
    ↓
SupplierItemMapping
    ↓
Ingredient
    ↓
StockMovement TYPE_IN
    ↓
Ingredient.average_cost
    ↓
Recipe / RecipeItem
    ↓
Product.estimated_cost
```

O estoque não deve ser duplicado em `Product`.

---

# 2. Premissa importante da arquitetura atual do StarChef

No StarChef:

- `Product` representa principalmente o produto vendido.
- O estoque real é controlado através de `Ingredient`.
- As movimentações estão em `StockMovement`.
- As fichas técnicas usam `Recipe` e `RecipeItem`.
- A venda de um `Product` consome os ingredientes associados à sua receita.

Portanto, o módulo de entrada de NF-e não deve criar um segundo saldo de estoque diretamente em `Product`.

A NF-e deve alimentar `Ingredient`.

Exemplo:

```text
NF-e:
ARROZ TIPO 1 FD 30KG

↓ mapeamento

Ingredient:
Arroz Branco

↓ entrada

StockMovement:
+60 KG
```

Para produtos vendidos diretamente, como bebidas:

```text
Product:
Heineken Long Neck

Recipe:
rendimento = 1

RecipeItem:
Ingredient = Heineken Long Neck
quantity = 1 UN
```

Assim:

```text
Compra da NF-e
    ↓
+24 Ingredient Heineken

Venda
    ↓
Product Heineken
    ↓
Recipe
    ↓
-1 Ingredient Heineken
```

Existe apenas um estoque.

---

# 3. Novo módulo Django

Criar um app isolado:

```text
backend/apps/inbound_nfe/
```

Estrutura sugerida:

```text
backend/apps/inbound_nfe/
├── __init__.py
├── apps.py
├── models.py
├── serializers.py
├── views.py
├── urls.py
├── tasks.py
├── admin.py
│
├── services/
│   ├── __init__.py
│   ├── sefaz_client.py
│   ├── certificate.py
│   ├── distribution.py
│   ├── manifestation.py
│   ├── xml_parser.py
│   ├── matching.py
│   └── receiving.py
│
└── tests/
    ├── fixtures/
    │   ├── res_nfe.xml
    │   ├── nfe_proc.xml
    │   └── cancel_event.xml
    ├── test_parser.py
    ├── test_matching.py
    ├── test_receiving.py
    ├── test_distribution.py
    └── test_idempotency.py
```

Não concentrar toda a lógica em um único `services.py`.

---

# 4. Alteração permitida em Product

Adicionar apenas um campo para GTIN/EAN.

Exemplo:

```python
gtin = models.CharField(
    max_length=14,
    blank=True,
    db_index=True,
    help_text="GTIN/EAN/UPC do produto, somente dígitos."
)
```

Opcionalmente, criar uma constraint por filial:

```python
models.UniqueConstraint(
    fields=["branch", "gtin"],
    condition=~models.Q(gtin=""),
    name="unique_product_gtin_by_branch",
)
```

Não adicionar `codigo_fornecedor` diretamente em `Product`.

Um mesmo produto pode possuir códigos diferentes para fornecedores diferentes.

Exemplo:

```text
Coca-Cola 2L

Fornecedor A → código 155
Fornecedor B → código 928833
Fornecedor C → código CC2L
```

Por isso o relacionamento fornecedor/produto precisa estar em uma tabela própria.

---

# 5. Reutilizar FiscalConfig

O StarChef já possui informações fiscais como:

```text
FiscalConfig.cnpj
FiscalConfig.uf
FiscalConfig.environment
FiscalConfig.certificate_ref
```

Esses dados devem ser reaproveitados.

Não duplicar CNPJ, UF ou ambiente sem necessidade.

Para distribuição de DF-e, validar especificamente:

```text
CNPJ
UF
certificado A1
referência/senha segura do certificado
ambiente
```

CSC não deve ser exigido para a consulta de distribuição de DF-e.

CSC pertence ao fluxo da NFC-e e não ao `NFeDistribuicaoDFe`.

---

# 6. Certificado digital

Para automação, utilizar preferencialmente certificado A1:

```text
.pfx
.p12
```

O certificado precisa ser carregado pelo backend para autenticação mTLS com os serviços da SEFAZ.

Nunca guardar a senha do certificado em texto puro.

Possibilidades:

- secret manager;
- variável segura do ambiente;
- campo criptografado;
- referência para segredo externo.

Exemplo conceitual:

```python
class DFeSyncState(TenantModel):
    certificate_password_ref = models.CharField(...)
```

O `certificate_ref` existente em `FiscalConfig` continua apontando para o arquivo/certificado.

---

# 7. Estado da sincronização / controle do NSU

Criar uma tabela própria para controlar a sincronização.

Exemplo:

```python
class DFeSyncState(TenantModel):
    ult_nsu = models.CharField(
        max_length=15,
        default="000000000000000"
    )

    max_nsu = models.CharField(
        max_length=15,
        default="000000000000000"
    )

    last_cstat = models.CharField(
        max_length=3,
        blank=True
    )

    last_reason = models.TextField(
        blank=True
    )

    last_sync_at = models.DateTimeField(
        null=True,
        blank=True
    )

    next_allowed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    is_syncing = models.BooleanField(
        default=False
    )
```

Deve existir somente um estado de sincronização por empresa/filial/CNPJ, conforme a arquitetura multi-tenant do projeto.

Nunca calcular manualmente o próximo NSU.

Sempre reutilizar exatamente o `ultNSU` retornado pela SEFAZ.

Fluxo:

```text
Banco:
ultNSU = 000000000000125

↓

Consulta SEFAZ

↓

Resposta:
ultNSU = 000000000000140
maxNSU = 000000000000145

↓

Salvar:
ultNSU = 000000000000140

↓

Nova consulta continua desse ponto.
```

---

# 8. Serviço NFeDistribuicaoDFe

Encapsular toda a comunicação SOAP em uma classe.

Exemplo:

```python
class NFeDistribuicaoClient:

    def fetch_since_nsu(self, *, cnpj, uf_code, ult_nsu, environment):
        ...

    def fetch_by_key(self, *, cnpj, uf_code, access_key, environment):
        ...
```

O restante da aplicação não deve conhecer detalhes de SOAP.

Request lógico:

```xml
<distDFeInt
    xmlns="http://www.portalfiscal.inf.br/nfe"
    versao="1.01">

    <tpAmb>1</tpAmb>
    <cUFAutor>33</cUFAutor>
    <CNPJ>12345678000190</CNPJ>

    <distNSU>
        <ultNSU>000000000000000</ultNSU>
    </distNSU>

</distDFeInt>
```

Para RJ:

```text
cUFAutor = 33
```

Normalizar sempre o CNPJ:

```text
12.345.678/0001-90  → errado para XML
12345678000190      → correto
```

---

# 9. Resposta da SEFAZ

Tratar pelo menos os seguintes status:

```text
138 = Documento(s) localizado(s)
137 = Nenhum documento localizado
656 = Consumo indevido
```

Ao receber documentos, normalmente haverá elementos `docZip`.

Exemplo:

```xml
<docZip
    NSU="000000000000200"
    schema="resNFe_v1.01.xsd">

    BASE64...

</docZip>
```

O conteúdo precisa ser processado assim:

```python
compressed = base64.b64decode(doc_zip.text)
xml_bytes = gzip.decompress(compressed)
```

Não determinar o tipo do documento por tamanho.

Usar:

- atributo `schema`;
- root XML;
- namespace.

---

# 10. Tipos de documento que o módulo deve entender

Tratar pelo menos:

```text
resNFe
nfeProc
procEventoNFe
```

## 10.1 resNFe

Resumo da NF-e.

Normalmente contém informações como:

```text
chNFe
CNPJ
xNome
IE
dhEmi
tpNF
vNF
digVal
dhRecbto
cSitNFe
```

Ainda não possui todos os itens da nota.

Usar esse documento para criar a NF-e como descoberta/resumo.

---

## 10.2 nfeProc

É a NF-e completa processada/autorizada.

É o documento principal para importação do estoque.

Usar dados de:

```text
ide
emit
dest
det[]
total
transp
pag
protNFe
```

Os itens estarão em:

```xml
<det nItem="1">
    <prod>
        ...
    </prod>
</det>
```

---

## 10.3 procEventoNFe

Eventos posteriores relacionados à NF-e.

Processar principalmente:

```text
cancelamento
manifestação do destinatário
```

Se uma NF-e já importada for posteriormente cancelada:

```text
InboundNFe.status = cancelled
```

O sistema deve alertar o operador.

Não estornar silenciosamente o estoque automaticamente.

---

# 11. Model InboundNFe

Criar uma tabela específica para NF-e recebida.

Exemplo:

```python
class InboundNFe(TenantModel):

    STATUS_SUMMARY = "summary"
    STATUS_XML_AVAILABLE = "xml_available"
    STATUS_PENDING_MAPPING = "pending_mapping"
    STATUS_PENDING_RECEIPT = "pending_receipt"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"

    access_key = models.CharField(
        max_length=44,
        db_index=True
    )

    nsu = models.CharField(
        max_length=15,
        blank=True
    )

    number = models.CharField(
        max_length=20,
        blank=True
    )

    series = models.CharField(
        max_length=10,
        blank=True
    )

    issue_date = models.DateTimeField(
        null=True,
        blank=True
    )

    supplier_cnpj = models.CharField(
        max_length=14,
        blank=True
    )

    supplier_name = models.CharField(
        max_length=180,
        blank=True
    )

    total_products = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    total_invoice = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0
    )

    status = models.CharField(
        max_length=30
    )

    manifestation_status = models.CharField(
        max_length=30,
        blank=True
    )

    summary_xml = models.TextField(
        blank=True
    )

    full_xml = models.TextField(
        blank=True
    )

    stock_applied_at = models.DateTimeField(
        null=True,
        blank=True
    )

    stock_applied_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+"
    )
```

Adicionar constraint de idempotência.

Exemplo conceitual:

```python
models.UniqueConstraint(
    fields=["account", "access_key"],
    name="unique_inbound_nfe_by_account"
)
```

Adaptar os campos exatos para a implementação atual de `TenantModel`.

Objetivo:

```text
A mesma chave NF-e jamais pode ser criada duas vezes.
```

---

# 12. Model InboundNFeItem

Criar uma tabela para os itens da NF-e.

Exemplo:

```python
class InboundNFeItem(TenantModel):

    invoice = models.ForeignKey(
        InboundNFe,
        related_name="items",
        on_delete=models.CASCADE
    )

    item_number = models.PositiveIntegerField()

    supplier_code = models.CharField(
        max_length=60,
        blank=True
    )

    ean = models.CharField(
        max_length=14,
        blank=True
    )

    description = models.CharField(
        max_length=255
    )

    ncm = models.CharField(
        max_length=8,
        blank=True
    )

    cfop = models.CharField(
        max_length=4,
        blank=True
    )

    commercial_unit = models.CharField(
        max_length=10,
        blank=True
    )

    commercial_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    commercial_unit_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    taxable_unit = models.CharField(
        max_length=10,
        blank=True
    )

    taxable_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    taxable_unit_value = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0
    )

    product_total = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    discount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    freight = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    insurance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    other_expenses = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0
    )

    ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    conversion_factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=1
    )

    received_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True
    )

    stock_movement = models.OneToOneField(
        "stock.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="inbound_nfe_item"
    )
```

O vínculo com `StockMovement` é essencial para impedir entrada duplicada.

Se:

```text
stock_movement != null
```

o item já foi lançado no estoque.

---

# 13. DE/PARA de fornecedor

Criar uma tabela própria:

```python
class SupplierItemMapping(TenantModel):

    supplier_cnpj = models.CharField(
        max_length=14,
        db_index=True
    )

    supplier_code = models.CharField(
        max_length=60,
        blank=True
    )

    supplier_ean = models.CharField(
        max_length=14,
        blank=True
    )

    ingredient = models.ForeignKey(
        "menu.Ingredient",
        on_delete=models.PROTECT
    )

    product = models.ForeignKey(
        "menu.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    conversion_factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=1
    )
```

Exemplo:

```text
Fornecedor:
Ambev

supplier_code:
009182

Descrição na NF:
CERVEJA HEINEKEN LN CX 24

↓ DE/PARA

Ingredient:
Heineken Long Neck 330ml

conversion_factor:
24
```

Então:

```text
qCom = 10 CX

↓

10 × 24

↓

240 unidades em estoque
```

---

# 14. Algoritmo de matching

Tentar associação nesta ordem:

```text
1. supplier_cnpj + supplier_code
2. supplier_cnpj + EAN
3. Product.gtin
4. similaridade de descrição
5. associação manual
```

A similaridade de nome deve ser apenas sugestão.

Nunca lançar estoque automaticamente somente por similaridade textual.

Exemplo:

```text
NF:
COCA COLA ORIGINAL PET 2 LT

Possível produto:
Coca-Cola 2L

Confiança:
94%

[VINCULAR]
```

Quando o operador confirmar, salvar o vínculo em `SupplierItemMapping`.

Nas próximas NF-e do mesmo fornecedor, o mapeamento será automático.

---

# 15. Parser do XML da NF-e

Criar em:

```text
services/xml_parser.py
```

A função deve receber XML completo e retornar objetos/DTOs internos.

Exemplo:

```python
@dataclass
class ParsedNFeItem:
    item_number: int
    supplier_code: str
    ean: str
    description: str
    ncm: str
    cfop: str
    commercial_unit: str
    commercial_quantity: Decimal
    commercial_unit_value: Decimal
    taxable_unit: str
    taxable_quantity: Decimal
    taxable_unit_value: Decimal
    product_total: Decimal
    discount: Decimal
    freight: Decimal
    insurance: Decimal
    other_expenses: Decimal
```

E:

```python
@dataclass
class ParsedNFe:
    access_key: str
    number: str
    series: str
    issue_date: datetime

    supplier_cnpj: str
    supplier_name: str

    total_products: Decimal
    total_invoice: Decimal

    items: list[ParsedNFeItem]
```

Separar parser do banco de dados.

O parser não deve criar models Django diretamente.

Fluxo:

```text
XML
 ↓
xml_parser.py
 ↓
ParsedNFe
 ↓
distribution/import service
 ↓
models
```

---

# 16. Informações mínimas de `<prod>`

Para cada `<det>`, extrair pelo menos:

```text
cProd
cEAN
xProd
NCM
CFOP
uCom
qCom
vUnCom
vProd
cEANTrib
uTrib
qTrib
vUnTrib
vFrete
vSeg
vDesc
vOutro
```

Sempre aceitar campos ausentes.

Não assumir que todas as notas possuem EAN.

Possíveis valores de EAN:

```text
SEM GTIN
vazio
código válido
```

Normalizar.

---

# 17. Cálculo da quantidade que entra no estoque

Quantidade física de estoque:

```python
stock_quantity = (
    received_quantity
    * conversion_factor
)
```

Exemplo:

```text
NF:
10 CX

Fator:
24 UN/CX

Entrada:
240 UN
```

Outro exemplo:

```text
NF:
2 FD

Fator:
30 KG/FD

Entrada:
60 KG
```

---

# 18. Fluxo de recebimento

Não aumentar o estoque automaticamente quando a NF-e for descoberta.

Fluxo obrigatório:

```text
NF localizada
↓
XML obtido
↓
itens importados
↓
mapeamento
↓
conferência física
↓
CONFIRMAR ENTRADA
↓
StockMovement TYPE_IN
```

Isso evita divergências quando:

- veio quantidade menor;
- veio produto errado;
- mercadoria foi recusada;
- parte da compra não chegou;
- houve avaria;
- o peso real difere da quantidade faturada.

---

# 19. API de recebimento

Criar:

```text
POST /api/v1/inbound-nfe/{id}/receive/
```

Payload sugerido:

```json
{
  "location_id": "UUID-OU-ID",
  "items": [
    {
      "item_id": "UUID-OU-ID",
      "received_quantity": "24"
    },
    {
      "item_id": "UUID-OU-ID",
      "received_quantity": "19.750"
    }
  ]
}
```

Executar tudo dentro de transação:

```python
@transaction.atomic
def receive_invoice(...):
    ...
```

Bloquear a NF para concorrência:

```python
invoice = (
    InboundNFe.objects
    .select_for_update()
    .get(...)
)
```

Antes de criar movimentações verificar:

```text
invoice já recebida?
item.stock_movement já existe?
ingredient está mapeado?
location é válida?
```

---

# 20. Criação do StockMovement

Para cada item:

```python
stock_qty = (
    item.received_quantity
    * item.conversion_factor
)
```

Criar:

```python
movement = StockMovement.objects.create(
    account=invoice.account,
    restaurant=invoice.restaurant,
    branch=invoice.branch,

    ingredient=item.ingredient,
    location=location,

    operator=user,

    movement_type=StockMovement.TYPE_IN,

    quantity=stock_qty,
    unit_cost=stock_unit_cost,
    total_cost=stock_qty * stock_unit_cost,

    reason=(
        f"Entrada NF-e {invoice.number} "
        f"- {invoice.supplier_name} "
        f"- {invoice.access_key}"
    ),

    created_by=user,
    updated_by=user,
)
```

Depois:

```python
item.stock_movement = movement
item.save(update_fields=["stock_movement"])
```

No final:

```python
invoice.status = InboundNFe.STATUS_RECEIVED
invoice.stock_applied_at = timezone.now()
invoice.stock_applied_by = user
invoice.save(...)
```

---

# 21. Idempotência obrigatória

A implementação deve suportar repetição segura.

Exemplos:

```text
Celery roda duas vezes
API recebe retry
usuário clica duas vezes
SEFAZ devolve documento repetido
```

Nenhuma dessas situações pode duplicar:

- NF-e;
- item;
- movimento de estoque;
- manifestação.

Regras:

```text
access_key deve ser única por tenant/empresa
invoice + item_number deve ser único
stock_movement por InboundNFeItem deve ser único
evento fiscal deve possuir chave/idempotency key
```

---

# 22. Custo do item

Não considerar apenas:

```text
vUnCom
```

Guardar todos os componentes.

Para um MVP:

```text
custo bruto mercadoria
    = vProd

custo líquido aproximado
    = vProd
    - vDesc
    + vFrete
    + vSeg
    + vOutro
    + vIPI
```

Depois:

```python
stock_unit_cost = total_item_cost / stock_quantity
```

A apropriação fiscal definitiva depende do regime tributário.

Por isso:

- guardar os componentes separados;
- não destruir os valores originais do XML;
- deixar a fórmula isolada em um service.

Exemplo:

```text
services/cost.py
```

ou dentro de:

```text
services/receiving.py
```

com função separada.

---

# 23. Custo médio

A entrada da NF-e deve atualizar:

```text
Ingredient.average_cost
```

Depois aproveitar a lógica existente para recalcular:

```text
RecipeItem
↓
Recipe.total_cost
↓
Product.estimated_cost
↓
Product.margin_percent
```

Antes de utilizar isso, revisar a implementação atual do cálculo de custo médio.

Possível problema:

```text
o StockMovement é salvo
↓
função consulta o saldo
↓
o movimento novo já faz parte desse saldo
↓
função soma incoming_quantity novamente
```

Isso pode duplicar matematicamente a quantidade recebida no cálculo.

Fórmula correta:

```text
estoque anterior:
100 UN × R$ 5,00

entrada:
100 UN × R$ 6,00

novo custo médio:

(100 × 5,00 + 100 × 6,00) / 200

= R$ 5,50
```

Não:

```text
(200 × 5,00 + 100 × 6,00) / 300
```

Recomendações:

1. calcular custo médio antes de persistir o movimento; ou
2. passar `previous_stock` explicitamente; ou
3. alterar o serviço para descontar corretamente o movimento atual.

Essa correção não exige alteração de banco.

---

# 24. Manifestação do Destinatário

Criar:

```text
services/manifestation.py
```

Eventos principais:

```text
210210 = Ciência da Emissão
210200 = Confirmação da Operação
210220 = Desconhecimento da Operação
210240 = Operação Não Realizada
```

Criar endpoint:

```text
POST /api/v1/inbound-nfe/{id}/manifest/
```

Exemplo:

```json
{
  "event": "science"
}
```

Para operação não realizada:

```json
{
  "event": "not_performed",
  "reason": "Mercadoria recusada devido a divergência..."
}
```

O evento precisa ser:

1. montado no XML correto;
2. assinado digitalmente;
3. transmitido ao serviço de recepção de eventos;
4. validado pela resposta da SEFAZ;
5. persistido no banco.

---

# 25. Estratégia de manifestação

Não marcar automaticamente todas as notas como `Confirmação da Operação`.

Fluxo recomendado:

```text
Nova NF-e
↓
Ciência da Emissão
↓
obter XML completo
↓
operador confere mercadoria
↓
confirmar entrada de estoque
↓
Confirmação da Operação
```

Pode futuramente existir configuração para fornecedores confiáveis.

Exemplo:

```text
Fornecedor confiável:
[x] manifestar Ciência automaticamente

[ ] confirmar operação automaticamente
```

A confirmação da operação deve ser mais conservadora.

---

# 26. Celery

O StarChef já possui Celery/Redis.

Criar:

```python
@shared_task
def sync_all_inbound_nfe():
    ...
```

E:

```python
@shared_task
def sync_branch_inbound_nfe(branch_id):
    ...
```

O scheduler pode ser disparado periodicamente, por exemplo:

```text
a cada 5 ou 10 minutos
```

Mas a task deve consultar `next_allowed_at`.

Exemplo:

```python
if (
    state.next_allowed_at
    and state.next_allowed_at > timezone.now()
):
    return
```

Se a SEFAZ retornar que não há documentos:

```text
cStat 137
```

definir aproximadamente:

```python
state.next_allowed_at = (
    timezone.now()
    + timedelta(minutes=65)
)
```

Se houver `656`, também suspender novas consultas e registrar o motivo.

Nunca criar loop agressivo de consulta.

---

# 27. Lock de sincronização

Evitar que duas tasks consultem o mesmo CNPJ ao mesmo tempo.

Possibilidades:

- `select_for_update`;
- Redis lock;
- advisory lock;
- flag `is_syncing` com proteção transacional.

Exemplo conceitual:

```python
with transaction.atomic():
    state = (
        DFeSyncState.objects
        .select_for_update()
        .get(...)
    )

    if state.is_syncing:
        return

    state.is_syncing = True
    state.save(...)
```

Garantir `finally` para liberar estado.

---

# 28. API sugerida

Criar:

```text
GET
/api/v1/inbound-nfe/

GET
/api/v1/inbound-nfe/{id}/

POST
/api/v1/inbound-nfe/sync/

POST
/api/v1/inbound-nfe/{id}/manifest/

POST
/api/v1/inbound-nfe/{id}/refresh-xml/

POST
/api/v1/inbound-nfe/{id}/receive/

POST
/api/v1/inbound-nfe/items/{id}/map/

GET
/api/v1/inbound-nfe/mappings/

POST
/api/v1/inbound-nfe/mappings/
```

Filtros úteis:

```text
status
supplier_cnpj
supplier_name
issue_date
number
access_key
mapped
unmapped
```

---

# 29. Endpoint de mapeamento

Exemplo:

```text
POST /api/v1/inbound-nfe/items/{id}/map/
```

Payload:

```json
{
  "ingredient_id": "UUID-OU-ID",
  "product_id": "UUID-OU-ID-OPCIONAL",
  "conversion_factor": "24",
  "save_supplier_mapping": true
}
```

Se:

```text
save_supplier_mapping = true
```

criar/atualizar:

```text
SupplierItemMapping
```

Assim o próximo item igual será reconhecido automaticamente.

---

# 30. Interface administrativa / retaguarda

Adicionar menu:

```text
Fiscal
└── Notas de Entrada
```

Tela de listagem:

| NF | Emissão | Fornecedor | Valor | Situação |
|---|---|---|---:|---|
| 56021 | 19/08/2026 | ABC Alimentos | R$ 4.382,00 | Aguardando |
| 56110 | 20/08/2026 | Distribuidora XYZ | R$ 2.100,00 | Recebida |

Possíveis status:

```text
Nova
XML disponível
Mapeamento pendente
Aguardando recebimento
Recebida
Cancelada
Erro
```

---

# 31. Tela de detalhes da NF-e

Exemplo:

```text
NF-e 56021
Fornecedor: XYZ Alimentos
CNPJ: 00.000.000/0001-00
Emissão: 19/08/2026
Valor: R$ 4.382,00
```

Itens:

```text
Descrição NF             Qtd NF      Produto StarChef
-------------------------------------------------------
ARROZ T1 FD 30KG         2 FD        Arroz Branco       ✓
OLEO SOJA PET 900ML      12 UN       Óleo de Soja       ✓
CARNE FILE KG            22 KG       Não mapeado        ⚠
```

Ações:

```text
[MAPEAR ITEM]
[MANIFESTAR CIÊNCIA]
[ATUALIZAR XML]
[CONFERIR RECEBIMENTO]
```

---

# 32. Tela de conferência

Exemplo:

```text
ITEM                       NOTA        RECEBIDO

Arroz Branco               60 KG       60 KG
Óleo de Soja               12 UN       12 UN
Filé Mignon                22 KG       21,760 KG
```

Botão:

```text
[CONFIRMAR ENTRADA NO ESTOQUE]
```

Usar o valor realmente recebido para o movimento de estoque.

O XML original continua preservado.

---

# 33. Cancelamento posterior

Se chegar um evento de cancelamento para uma NF-e:

```text
InboundNFe.status = cancelled
```

Se ainda não houve entrada:

```text
bloquear recebimento
```

Se já houve entrada:

```text
exibir alerta crítico:

"NF-e cancelada após entrada de estoque."
```

Não executar estorno silencioso.

O operador deverá decidir se:

- cria movimento de saída;
- recebe uma NF substituta;
- houve devolução;
- houve erro administrativo.

---

# 34. Segurança

Requisitos mínimos:

1. Certificado A1 fora do repositório Git.
2. Senha do certificado nunca em plaintext.
3. XML armazenado com controle de acesso.
4. API filtrada por tenant/filial.
5. Nunca permitir acesso cruzado entre empresas.
6. Logs sem senha do certificado.
7. Logs sem conteúdo sensível desnecessário.
8. Validar CNPJ do destinatário do XML antes de aceitar a nota.
9. Validar chave de acesso.
10. Validar protocolo/autorização quando houver `nfeProc`.

---

# 35. Validações obrigatórias ao importar XML

Antes de persistir uma NF-e completa:

```text
1. XML parseia corretamente?
2. Root/namespace é esperado?
3. Chave possui 44 dígitos?
4. destinatário é o CNPJ da empresa?
5. NF está autorizada?
6. chave já existe?
7. número e série correspondem à chave?
8. itens são válidos?
```

Nunca aceitar XML de outro CNPJ como entrada da empresa atual.

---

# 36. Testes

## 36.1 Parser

Testar:

```text
NF com EAN
NF sem EAN
NF com desconto
NF com frete
NF com unidade CX
NF com unidade KG
NF com casas decimais
NF com vários itens
```

---

## 36.2 Matching

Testar:

```text
supplier_code exato
EAN exato
GTIN do Product
descrição parecida
nenhum match
```

Nunca auto-confirmar apenas por similaridade.

---

## 36.3 Conversão

Exemplo:

```text
10 CX
fator 24
resultado 240 UN
```

Outro:

```text
2 FD
fator 30
resultado 60 KG
```

---

## 36.4 Idempotência

Executar duas vezes:

```python
receive_invoice(invoice_id)
receive_invoice(invoice_id)
```

Resultado esperado:

```text
apenas um StockMovement por item
```

---

## 36.5 Concorrência

Simular duas requisições simultâneas de recebimento.

Resultado:

```text
apenas uma consegue efetivar a entrada
```

---

## 36.6 Eventos

Testar:

```text
cancelamento antes da entrada
cancelamento depois da entrada
Ciência
Confirmação
Operação Não Realizada
Desconhecimento
```

---

# 37. Logs e observabilidade

Registrar:

```text
CNPJ/tenant
data/hora
ultNSU enviado
ultNSU recebido
maxNSU
cStat
xMotivo
quantidade de docZip
quantidade de novas NF-e
chaves processadas
erros de parser
erros de certificado
erros de manifestação
```

Nunca registrar:

```text
senha do certificado
private key
PFX em Base64
```

---

# 38. Estados sugeridos

Fluxo simplificado:

```text
summary
    ↓
xml_available
    ↓
pending_mapping
    ↓
pending_receipt
    ↓
received
```

Fluxos alternativos:

```text
qualquer etapa
    ↓
cancelled
```

ou:

```text
qualquer etapa
    ↓
error
```

Pode ser implementado por `status` com escolhas.

---

# 39. Ordem de implementação

Implementar nesta sequência.

## Etapa 1 — Models

Criar:

```text
DFeSyncState
InboundNFe
InboundNFeItem
SupplierItemMapping
```

Adicionar:

```text
Product.gtin
```

Gerar migrations.

---

## Etapa 2 — Parser XML

Antes de conectar à SEFAZ:

1. usar XMLs reais/sanitizados como fixtures;
2. implementar parser;
3. criar testes;
4. garantir leitura de todos os campos necessários.

---

## Etapa 3 — Matching

Implementar:

```text
supplier_code
EAN
Product.gtin
similaridade
manual
```

Persistir o DE/PARA.

---

## Etapa 4 — Recebimento

Implementar:

```text
InboundNFe
↓
itens
↓
conferência
↓
StockMovement TYPE_IN
```

Garantir transação e idempotência.

---

## Etapa 5 — Custo médio

Revisar e corrigir o cálculo de custo médio existente.

Testar propagação para:

```text
Ingredient.average_cost
Recipe
Product.estimated_cost
Product.margin_percent
```

---

## Etapa 6 — APIs

Criar serializers, views, permissions e URLs.

---

## Etapa 7 — Interface

Criar:

```text
lista de notas
detalhes
mapeamento
conferência
recebimento
```

---

## Etapa 8 — Certificado A1

Implementar carregamento seguro e autenticação mTLS.

---

## Etapa 9 — Distribuição DF-e

Implementar:

```text
NFeDistribuicaoDFe
controle do NSU
docZip
Base64
GZip
resNFe
nfeProc
procEventoNFe
```

---

## Etapa 10 — Manifestação

Implementar:

```text
Ciência
Confirmação
Desconhecimento
Operação Não Realizada
```

Assinar o XML corretamente.

---

## Etapa 11 — Celery

Criar tasks.

Controlar:

```text
next_allowed_at
locks
137
138
656
```

---

## Etapa 12 — Homologação

Testar antes de produção.

Nunca habilitar sincronização automática em produção sem validar:

```text
certificado
NSU
idempotência
parsing
manifestação
movimento de estoque
custo médio
```

---

# 40. Escopo do MVP

O primeiro MVP deve fazer apenas:

```text
1. detectar NF-e
2. armazenar resumo
3. obter XML completo
4. parsear itens
5. fazer DE/PARA
6. conferir quantidade
7. gerar entrada de estoque
8. atualizar custo
```

Não incluir inicialmente:

```text
contas a pagar
conciliação bancária
pedido de compra
aprovação de compra
devolução automática
contabilidade completa
apuração tributária
```

Esses recursos podem ser adicionados depois.

---

# 41. Regra central para a IA que fará a implementação

Não criar estoque paralelo.

Não transformar cada item da NF-e diretamente em `Product`.

Não misturar entrada de fornecedor com o model atual de documentos fiscais emitidos pelo PDV.

A arquitetura correta é:

```text
SEFAZ
  ↓
NFeDistribuicaoDFe
  ↓
InboundNFe
  ↓
InboundNFeItem
  ↓
SupplierItemMapping
  ↓
Ingredient
  ↓
StockMovement TYPE_IN
  ↓
average_cost
  ↓
Recipe
  ↓
Product
```

`Product` deve permanecer praticamente intacto.

A alteração mínima sugerida é:

```text
Product.gtin
```

Toda a complexidade específica da entrada de NF-e deve ficar dentro de:

```text
backend/apps/inbound_nfe/
```

---

# 42. Critérios de aceite

O módulo será considerado funcional quando for possível:

- [ ] Configurar certificado A1 para uma empresa.
- [ ] Consultar o `NFeDistribuicaoDFe`.
- [ ] Continuar corretamente a partir do último NSU.
- [ ] Detectar uma NF-e nova emitida contra o CNPJ.
- [ ] Salvar a NF-e sem duplicação.
- [ ] Processar `docZip`.
- [ ] Descompactar Base64 + GZip.
- [ ] Ler `resNFe`.
- [ ] Ler `nfeProc`.
- [ ] Ler eventos posteriores.
- [ ] Manifestar Ciência da Emissão.
- [ ] Exibir os itens da NF-e.
- [ ] Relacionar item do fornecedor com `Ingredient`.
- [ ] Memorizar esse relacionamento.
- [ ] Aplicar fator de conversão.
- [ ] Informar quantidade efetivamente recebida.
- [ ] Criar um único `StockMovement TYPE_IN`.
- [ ] Atualizar custo médio corretamente.
- [ ] Propagar custo para fichas técnicas.
- [ ] Impedir entrada duplicada.
- [ ] Detectar cancelamento posterior.
- [ ] Respeitar intervalo de consulta da SEFAZ.
- [ ] Tratar `cStat 137`, `138` e `656`.
- [ ] Manter isolamento multi-tenant.
- [ ] Nunca expor senha ou chave privada do certificado.

---

# 43. Resultado esperado

Após implementado, o fluxo operacional deverá ser aproximadamente:

```text
Fornecedor emite NF-e
        ↓
StarChef detecta a nota
        ↓
"Nova NF-e recebida"
        ↓
Sistema obtém XML
        ↓
Lê produtos
        ↓
Reconhece itens já mapeados
        ↓
Solicita mapeamento somente dos desconhecidos
        ↓
Funcionário confere a entrega
        ↓
CONFIRMAR ENTRADA
        ↓
StockMovement TYPE_IN
        ↓
estoque atualizado
        ↓
custo médio atualizado
        ↓
CMV/ficha técnica atualizados
```

O objetivo final é transformar o recebimento de mercadorias em um processo quase automático, mantendo conferência humana somente onde realmente for necessária.
