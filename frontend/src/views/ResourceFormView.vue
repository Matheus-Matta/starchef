<template>
  <div class="rpage">
    <!-- Header: breadcrumb + title + actions -->
    <header class="rpage__head">
      <div class="rpage__crumbs">
        <button class="rpage__back" type="button" @click="goToList">
          <i class="pi pi-arrow-left" />
          <span>{{ title }}</span>
        </button>
        <i class="pi pi-chevron-right rpage__sep" />
        <span class="rpage__crumb">{{ modeLabel }}</span>
      </div>

      <div class="rpage__head-actions">
        <template v-if="isView">
          <Button label="Voltar" severity="secondary" outlined icon="pi pi-arrow-left" @click="goToList" />
          <Button v-if="isOrder" label="Imprimir recibo" severity="secondary" outlined icon="pi pi-print" :loading="printing" @click="printOrder" />
          <Button v-if="isOrder && record?.payment_status === 'paid'" label="Emitir NFC-e / DANFE" severity="secondary" outlined icon="pi pi-receipt" :loading="emittingInvoice" @click="emitOrderInvoice" />
          <Button v-if="isOrder && ['open', 'awaiting_payment'].includes(record?.status)" label="Editar pedido" icon="pi pi-pencil" @click="editOrder" />
          <Button v-if="formFields" label="Editar" icon="pi pi-pencil" @click="startEdit" />
        </template>
      </div>
    </header>

    <!-- Loading skeleton -->
    <div v-if="fetching" class="rpage__card">
      <div class="rpage__card-head">
        <Skeleton width="240px" height="24px" />
        <Skeleton width="380px" height="16px" />
      </div>
      <div class="rpage__grid">
        <div v-for="i in skeletonCount" :key="i" class="rpage__field">
          <Skeleton width="110px" height="13px" />
          <Skeleton height="42px" border-radius="8px" />
        </div>
      </div>
    </div>

    <!-- Fetch error -->
    <div v-else-if="fetchError" class="rpage__alert rpage__alert--error">
      <i class="pi pi-exclamation-triangle" /> {{ fetchError }}
    </div>

    <!-- ────────────── VIEW MODE (fallback): recursos sem formFields ────────────── -->
    <!-- So existe para recursos 100% somente-leitura (sem pagina de edicao); os
         demais reusam o form abaixo, desabilitado (ver item "unified form"). -->
    <div v-else-if="isView && record && !formFields" class="rpage__view">
      <div class="detail-hero" :class="`accent--${detailMeta.accent}`">
        <span class="detail-hero__avatar"><i :class="`pi ${detailMeta.icon}`" /></span>
        <div class="detail-hero__headline">
          <span>{{ detailMeta.eyebrow }}</span>
          <h2>{{ viewTitle }}</h2>
          <p v-if="viewSubtitle">{{ viewSubtitle }}</p>
        </div>
        <span v-if="heroBadge" class="detail-hero__badge">{{ heroBadge }}</span>
      </div>

      <div v-if="detailMetrics.length" class="detail-metrics">
        <div v-for="metric in detailMetrics" :key="metric.label" class="detail-metric">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.display }}</strong>
        </div>
      </div>

      <section class="detail-section">
        <h3 class="detail-section__title">Informacoes</h3>
        <div class="detail-fields">
          <div v-for="field in detailFields" :key="field.key" class="detail-field">
            <span class="detail-field__label">{{ field.label }}</span>
            <span v-if="field.type === 'status'" class="status-chip" :data-status="field._value">{{ label(field._value, field.map) }}</span>
            <Tag
              v-else-if="field.type === 'boolean'"
              :value="field._value ? 'Ativo' : 'Inativo'"
              :severity="field._value ? 'success' : 'danger'"
              rounded
            />
            <strong v-else-if="field.type === 'money'" class="detail-field__money">{{ money(field._value) }}</strong>
            <span v-else-if="field.type === 'date'" class="detail-field__value">{{ dateTime(field._value) }}</span>
            <span v-else class="detail-field__value">{{ label(field._value, field.map) }}</span>
          </div>
        </div>
      </section>

      <!-- Itens do pedido — mesma exibição em DataTable das variações/adicionais -->
      <section v-if="isOrder && record?.items?.length" class="detail-section detail-section--items">
        <h3 class="detail-section__title">Itens do pedido <small>{{ record.items.length }}</small></h3>
        <DataTable :value="record.items" data-key="id" class="order-items" :row-hover="false" responsive-layout="scroll">
          <Column header="Produto">
            <template #body="{ data }">
              <div class="order-items__product">
                <strong>{{ data.product_name }}</strong>
                <small v-if="itemExtras(data)">{{ itemExtras(data) }}</small>
                <small v-if="data.customer_note" class="order-items__note">Obs.: {{ data.customer_note }}</small>
              </div>
            </template>
          </Column>
          <Column header="Qtd" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '80px' }" :style="{ width: '80px' }">
            <template #body="{ data }">{{ quantity(data.quantity) }}</template>
          </Column>
          <Column header="Total" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '110px' }" :style="{ width: '110px' }">
            <template #body="{ data }">{{ money(data.total_price) }}</template>
          </Column>
        </DataTable>
      </section>

      <!-- ── Itens da NF-e de Entrada (Conferência, Mapeamento e Entrada no Estoque) ── -->
      <section v-if="isInboundNFe && record?.items?.length" class="detail-section detail-section--inbound">
        <div class="detail-section__header-flex">
          <div class="detail-section__header-copy">
            <h3 class="detail-section__title">
              Produtos da Nota Fiscal
              <small class="rpro-badge ml-2">{{ record.items.length }} {{ record.items.length === 1 ? 'produto' : 'produtos' }}</small>
            </h3>
            <p class="text-sm text-muted">
              Confira os itens recebidos da SEFAZ, vincule aos ingredientes do estoque e confirme a entrada para atualizar seu saldo físico.
            </p>
          </div>

          <div class="detail-section__header-actions">
            <button
              v-if="record.status !== 'received' && record.status !== 'cancelled'"
              type="button"
              class="rpro-btn rpro-btn--primary"
              @click="openReceiveModal"
            >
              <i class="pi pi-box" /> Dar Entrada no Estoque
            </button>
            <div v-else-if="record.status === 'received'" class="rpro__inbound-received-badge">
              <i class="pi pi-check-circle text-emerald-600 text-lg" />
              <div>
                <strong class="text-emerald-700 block text-xs uppercase tracking-wider">Estoque Atualizado</strong>
                <span class="text-xs text-muted">{{ dateTime(record.stock_applied_at || record.updated_at) }}</span>
              </div>
            </div>
          </div>
        </div>

        <DataTable :value="record.items" data-key="id" class="inbound-items-table" responsive-layout="scroll">
          <Column header="#" :body-style="{ width: '48px', textAlign: 'center' }">
            <template #body="{ data }">
              <span class="font-bold text-muted">{{ data.item_number }}</span>
            </template>
          </Column>

          <Column header="Cód. Fornecedor" :body-style="{ width: '130px' }">
            <template #body="{ data }">
              <code class="rpro__code-pill">{{ data.supplier_code || '-' }}</code>
            </template>
          </Column>

          <Column header="Descrição do Produto">
            <template #body="{ data }">
              <div class="inbound-item-cell">
                <strong class="inbound-item-title">{{ data.description }}</strong>
                <div class="inbound-item-meta">
                  <span v-if="data.ean || data.ean_trib" class="inbound-item-meta-tag font-mono">
                    <i class="pi pi-barcode text-xs" /> {{ data.ean || data.ean_trib }}
                  </span>
                  <span v-if="data.ncm" class="inbound-item-meta-tag font-mono">NCM: {{ data.ncm }}</span>
                  <span v-if="data.cest" class="inbound-item-meta-tag font-mono">CEST: {{ data.cest }}</span>
                  <span v-if="data.cfop" class="inbound-item-meta-tag font-mono">CFOP: {{ data.cfop }}</span>
                </div>
                <!-- Tributos da NF-e -->
                <div v-if="data.tax_data && Object.keys(data.tax_data).length" class="inbound-item-taxes">
                  <span v-if="data.tax_data.ICMS" class="inbound-tax-badge">
                    ICMS {{ data.tax_data.ICMS.tipo || data.tax_data.ICMS.CST }} (R$ {{ data.tax_data.ICMS.vICMS || '0,00' }})
                  </span>
                  <span v-if="data.tax_data.PIS" class="inbound-tax-badge">
                    PIS: {{ data.tax_data.PIS.tipo }}
                  </span>
                  <span v-if="data.tax_data.COFINS" class="inbound-tax-badge">
                    COFINS: {{ data.tax_data.COFINS.tipo }}
                  </span>
                </div>
              </div>
            </template>
          </Column>

          <Column header="Qtd Comprada" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '130px' }">
            <template #body="{ data }">
              <strong>{{ Number(data.commercial_quantity).toLocaleString('pt-BR') }}</strong>
              <small class="text-muted ml-1 font-bold">{{ data.commercial_unit }}</small>
            </template>
          </Column>

          <Column header="Valor Unit." header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '110px' }">
            <template #body="{ data }">
              <span class="font-mono">{{ money(data.commercial_unit_value) }}</span>
            </template>
          </Column>

          <Column header="Valor Total" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '120px' }">
            <template #body="{ data }">
              <strong class="font-mono text-emerald-600">{{ money(data.product_total) }}</strong>
            </template>
          </Column>

          <Column header="Vínculo Sistema / Estoque" :body-style="{ width: '280px' }">
            <template #body="{ data }">
              <div v-if="data.ingredient_name || data.product_name" class="inbound-mapping-linked">
                <div class="inbound-mapping-linked-info">
                  <Tag severity="success" rounded :value="data.ingredient_name ? `Ingrediente: ${data.ingredient_name}` : `Produto: ${data.product_name}`" />
                  <small v-if="data.conversion_factor && Number(data.conversion_factor) !== 1" class="text-muted block text-xs mt-1 font-mono">
                    Fator: x{{ Number(data.conversion_factor) }}
                  </small>
                </div>
                <button
                  v-if="record.status !== 'received'"
                  type="button"
                  class="rpro-btn rpro-btn--ghost rpro-btn--xs"
                  title="Alterar vínculo"
                  @click="openMapModal(data)"
                >
                  <i class="pi pi-pencil" />
                </button>
              </div>
              <div v-else class="inbound-mapping-unlinked">
                <button
                  type="button"
                  class="rpro-btn rpro-btn--ghost rpro-btn--sm w-full"
                  :disabled="record.status === 'received'"
                  @click="openMapModal(data)"
                >
                  <i class="pi pi-link" /> Vincular Produto
                </button>
              </div>
            </template>
          </Column>
        </DataTable>
      </section>
    </div>

    <!-- ────────── FORM UNIFICADO: criar / editar / ver (campos desabilitados) ────────── -->
    <form
      v-else-if="formFields"
      class="rpage__card"
      :class="{ 'rpage__card--readonly': isView }"
      novalidate
      @submit.prevent="submit"
    >
      <div class="rpage__card-head">
        <h2>{{ isView ? viewTitle : isEdit ? `Editar ${title}` : `Novo ${title}` }}</h2>
        <p>
          {{
            isView
              ? 'Somente leitura. Clique em "Editar" para alterar os dados.'
              : isEdit
                ? "Altere os campos e salve para confirmar."
                : "Preencha os campos para criar um novo registro."
          }}
        </p>
      </div>

      <div v-for="group in formSections" :key="group.title || '_default'" class="rpage__section">
        <h3 v-if="group.title" class="rpage__section-title">{{ group.title }}</h3>
        <div class="rpage__grid">
          <div
            v-for="field in group.fields"
            :key="field.name"
            class="rpage__field"
            :class="{
              'rpage__field--full': field.full || field.type === 'textarea' || field.type === 'remote-multiselect' || (field.type === 'boolean' && field.name === 'is_active'),
              'rpage__field--error': !!fieldErrors[field.name],
            }"
          >
            <label :for="`f-${field.name}`" class="rpage__label">
              {{ field.label }}
              <span v-if="field.required && !isView" class="rpage__required" aria-hidden="true">*</span>
              <i v-if="field.hint" v-tooltip.top="field.hint" class="pi pi-question-circle rpage__help-icon" aria-hidden="true" />
            </label>

            <div v-if="field.type === 'boolean'" class="rpage__switch-row">
              <InputSwitch :id="`f-${field.name}`" v-model="formData[field.name]" :disabled="isView" />
              <span class="rpage__switch-label">{{ formData[field.name] ? "Ativo" : "Inativo" }}</span>
            </div>

            <Dropdown
              v-else-if="field.type === 'dropdown'"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :options="field.options"
              option-label="label"
              option-value="value"
              :placeholder="fieldPlaceholder(field, `Selecionar ${field.label.toLowerCase()}`)"
              :class="['rpage__select', { 'p-invalid': !!fieldErrors[field.name] }]"
              :show-clear="!field.required"
              :disabled="isView"
              filter
              fluid
            />

            <div v-else-if="field.type === 'remote-dropdown' && field.quickCreate" class="rpage__field-row">
              <Dropdown
                :id="`f-${field.name}`"
                v-model="formData[field.name]"
                :options="remoteOptions[field.name] || []"
                option-label="label"
                option-value="value"
                :placeholder="fieldPlaceholder(field, `Selecionar ${field.label.toLowerCase()}`)"
                :class="['rpage__select', { 'p-invalid': !!fieldErrors[field.name] }]"
                :show-clear="!field.required"
                :loading="!remoteOptions[field.name]"
                :disabled="isView"
                filter
                fluid
              />
              <Button
                v-if="!isView"
                type="button"
                icon="pi pi-plus"
                text
                rounded
                aria-label="Criar novo"
                :disabled="quickCreateLoading"
                @click="openQuickCreate(field)"
              />
            </div>

            <Dropdown
              v-else-if="field.type === 'remote-dropdown'"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :options="remoteOptions[field.name] || []"
              option-label="label"
              option-value="value"
              :placeholder="fieldPlaceholder(field, `Selecionar ${field.label.toLowerCase()}`)"
              :class="['rpage__select', { 'p-invalid': !!fieldErrors[field.name] }]"
              :show-clear="!field.required"
              :loading="!remoteOptions[field.name]"
              :disabled="isView"
              filter
              fluid
            />

            <PermissionAccordion
              v-else-if="field.type === 'remote-multiselect' && field.grouped && field.name === 'permissions'"
              v-model="formData[field.name]"
              :groups="groupedOptions(field.name)"
              :disabled="isView"
            />

            <MultiSelect
              v-else-if="field.type === 'remote-multiselect' && field.grouped"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :options="groupedOptions(field.name)"
              option-label="label"
              option-value="value"
              option-group-label="label"
              option-group-children="items"
              display="chip"
              :placeholder="fieldPlaceholder(field, `Selecionar ${field.label.toLowerCase()}`)"
              :class="['rpage__select', { 'p-invalid': !!fieldErrors[field.name] }]"
              :loading="!remoteOptions[field.name]"
              :disabled="isView"
              filter
              fluid
            />

            <MultiSelect
              v-else-if="field.type === 'remote-multiselect'"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :options="remoteOptions[field.name] || []"
              option-label="label"
              option-value="value"
              display="chip"
              :placeholder="fieldPlaceholder(field, `Selecionar ${field.label.toLowerCase()}`)"
              :class="['rpage__select', { 'p-invalid': !!fieldErrors[field.name] }]"
              :loading="!remoteOptions[field.name]"
              :disabled="isView"
              filter
              fluid
            />

            <Textarea
              v-else-if="field.type === 'textarea' || field.type === 'json'"
              :id="`f-${field.name}`"
              :model-value="field.type === 'json' && typeof formData[field.name] !== 'string' ? JSON.stringify(formData[field.name] || {}, null, 2) : formData[field.name]"
              :placeholder="fieldPlaceholder(field, field.label)"
              :maxlength="field.maxlength"
              :rows="field.rows || 4"
              auto-resize
              :disabled="isView"
              :class="['rpage__input', { 'p-invalid': !!fieldErrors[field.name] }]"
              @update:model-value="formData[field.name] = $event"
            />

            <Password
              v-else-if="field.type === 'password'"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :placeholder="fieldPlaceholder(field, field.label)"
              :feedback="false"
              toggle-mask
              :disabled="isView"
              :class="['rpage__password', { 'p-invalid': !!fieldErrors[field.name] }]"
              :input-class="['rpage__input', { 'p-invalid': !!fieldErrors[field.name] }]"
            />

            <InputText
              v-else-if="field.type === 'number' || field.type === 'decimal'"
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              type="number"
              :step="field.type === 'decimal' ? '0.01' : '1'"
              :min="field.min ?? '0'"
              :placeholder="fieldPlaceholder(field, '0')"
              :disabled="isView"
              :class="['rpage__input', { 'p-invalid': !!fieldErrors[field.name] }]"
            />

            <InputText
              v-else
              :id="`f-${field.name}`"
              v-model="formData[field.name]"
              :type="field.inputType || 'text'"
              :placeholder="fieldPlaceholder(field, field.label)"
              :maxlength="field.maxlength"
              :disabled="isView"
              :class="['rpage__input', { 'p-invalid': !!fieldErrors[field.name] }]"
            />

            <small v-if="fieldErrors[field.name]" class="rpage__field-err">
              <i class="pi pi-exclamation-circle" />
              {{ fieldErrors[field.name] }}
            </small>
          </div>
        </div>
      </div>

      <!-- Secoes especificas de produto: variacoes (editaveis) e ficha tecnica (leitura) -->
      <div v-if="isProduct" class="rpage__extra">
        <ProductVariationsEditor
          v-if="recordId"
          :key="`var-${recordId}-${record ? 'loaded' : 'new'}`"
          :product-id="recordId"
          :initial-variations="record?.variations || []"
          :readonly="isView"
        />
        <ProductAddonsEditor
          v-if="recordId"
          :key="`add-${recordId}-${record ? 'loaded' : 'new'}`"
          :product-id="recordId"
          :initial-addons="record?.addons || []"
          :readonly="isView"
        />
        <p v-else class="rpage__hint">Salve o produto para poder adicionar variacoes e adicionais.</p>

        <!-- Ficha técnica (leitura) — mesmo layout das variações/adicionais -->
        <RecipeItemsEditor
          v-if="record?.recipe?.id"
          :key="`ptech-${record.recipe.id}`"
          :recipe-id="record.recipe.id"
          :initial-items="record.recipe.items || []"
          readonly
        />
      </div>

      <!-- Ficha tecnica editavel da receita (Sprint 3 · STC-034/035) -->
      <div v-else-if="isRecipe" class="rpage__extra">
        <RecipeItemsEditor
          v-if="recordId"
          :key="`rec-${recordId}-${record ? 'loaded' : 'new'}`"
          :recipe-id="recordId"
          :initial-items="record?.items || []"
          :readonly="isView"
        />
        <p v-else class="rpage__hint">Salve a receita para poder adicionar ingredientes.</p>
      </div>

      <!-- Configuração fiscal (CNPJ, CSC, integrador) do restaurante -->
      <div v-else-if="isRestaurant" class="rpage__extra">
        <RestaurantFiscalSection
          v-if="recordId"
          ref="fiscalSectionRef"
          :key="`fiscal-${recordId}`"
          :restaurant-id="recordId"
          :readonly="isView"
        />
        <p v-else class="rpage__hint">Salve o restaurante para poder configurar os dados fiscais.</p>
      </div>

      <div v-if="saveError" class="rpage__alert rpage__alert--error rpage__alert--inline">
        <i class="pi pi-exclamation-triangle" /> {{ saveError }}
      </div>

      <div v-if="!isView" class="rpage__footer">
        <Button type="button" label="Cancelar" severity="secondary" outlined @click="cancelForm" />
        <Button type="submit" :label="isEdit ? 'Salvar alteracoes' : 'Criar registro'" :loading="saving" icon="pi pi-check" />
      </div>
    </form>

    <!-- Criação rápida de perfil fiscal a partir de qualquer remote-dropdown marcado com quickCreate: "fiscal-profile" (ex.: produto) -->
    <FiscalProfileDialog
      v-if="quickCreateBranchId"
      v-model:visible="fiscalProfileDialogOpen"
      :restaurant-id="quickCreateRestaurantId"
      :branch-id="quickCreateBranchId"
      @saved="onQuickCreateSaved"
    />

    <!-- ── Modal de Mapeamento / Vínculo de Item da NF-e ── -->
    <Dialog
      v-model:visible="mapItemDialogVisible"
      modal
      :header="mappingItem ? `Vincular Item #${mappingItem.item_number} · ${mappingItem.description}` : 'Vincular Item'"
      :style="{ width: 'min(560px, 95vw)' }"
    >
      <div v-if="mappingItem" class="inbound-modal-form">
        <div class="inbound-modal-item-summary">
          <span class="text-xs font-bold uppercase text-muted">Item da NF-e:</span>
          <strong class="text-base text-strong">{{ mappingItem.description }}</strong>
          <small class="text-muted">
            Cód. Forn: {{ mappingItem.supplier_code || '-' }} · EAN: {{ mappingItem.ean || mappingItem.ean_trib || 'Sem GTIN' }} · Qtd: {{ Number(mappingItem.commercial_quantity) }} {{ mappingItem.commercial_unit }}
          </small>
        </div>

        <div class="rpage__grid" style="grid-template-columns: 1fr; gap: 14px; margin-top: 14px">
          <div class="rpage__field rpage__field--full">
            <label class="rpage__label">Tipo de Destino no Sistema</label>
            <div class="flex gap-2">
              <button
                type="button"
                class="rpro-btn flex-1"
                :class="mappingForm.targetType === 'ingredient' ? 'rpro-btn--primary' : 'rpro-btn--ghost'"
                @click="mappingForm.targetType = 'ingredient'"
              >
                <i class="pi pi-database" /> Ingrediente de Estoque
              </button>
              <button
                type="button"
                class="rpro-btn flex-1"
                :class="mappingForm.targetType === 'product' ? 'rpro-btn--primary' : 'rpro-btn--ghost'"
                @click="mappingForm.targetType = 'product'"
              >
                <i class="pi pi-shopping-bag" /> Produto de Venda
              </button>
            </div>
          </div>

          <!-- Seleção de Ingrediente -->
          <div v-if="mappingForm.targetType === 'ingredient'" class="rpage__field rpage__field--full">
            <label class="rpage__label">Ingrediente de Estoque</label>
            <Dropdown
              v-model="mappingForm.ingredient_id"
              :options="mappingIngredients"
              option-label="name"
              option-value="id"
              placeholder="Selecione o ingrediente correspondente..."
              filter
              :loading="mappingLoading"
              class="w-full"
            />
          </div>

          <!-- Seleção de Produto -->
          <div v-else class="rpage__field rpage__field--full">
            <label class="rpage__label">Produto do Cardápio</label>
            <Dropdown
              v-model="mappingForm.product_id"
              :options="mappingProducts"
              option-label="name"
              option-value="id"
              placeholder="Selecione o produto correspondente..."
              filter
              :loading="mappingLoading"
              class="w-full"
            />
          </div>

          <!-- Fator de Conversão -->
          <div class="rpage__field rpage__field--full">
            <label class="rpage__label">
              Fator de Conversão de Quantidade
              <i class="pi pi-question-circle text-xs text-muted" title="Exemplo: Se a nota veio em Caixa (CX) com 12 unidades e o seu estoque controla em UN, informe 12. Se a nota já está na mesma unidade, deixe 1." />
            </label>
            <InputNumber
              v-model="mappingForm.conversion_factor"
              :min-fraction-digits="1"
              :max-fraction-digits="6"
              class="w-full"
            />
          </div>

          <!-- Lembrar Vínculo -->
          <div class="rpage__field rpage__field--full">
            <label class="flex items-center gap-2 cursor-pointer">
              <Checkbox v-model="mappingForm.save_supplier_mapping" :binary="true" />
              <span class="text-sm">Lembrar este vínculo automaticamente para as próximas compras deste fornecedor</span>
            </label>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="mappingSubmitting" @click="mapItemDialogVisible = false">
          Cancelar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="mappingSubmitting || (mappingForm.targetType === 'ingredient' ? !mappingForm.ingredient_id : !mappingForm.product_id)"
          @click="submitItemMapping"
        >
          <i :class="mappingSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-check'" /> Salvar Vínculo
        </button>
      </template>
    </Dialog>

    <!-- ── Modal de Confirmação de Entrada no Estoque / Recebimento Físico ── -->
    <Dialog
      v-model:visible="receiveDialogVisible"
      modal
      header="Conferência Física e Entrada no Estoque"
      :style="{ width: 'min(1050px, 96vw)' }"
    >
      <div class="inbound-receive-form">
        <p class="text-sm text-muted mb-4">
          Realize a conferência física dos volumes, lotes, validades e números de série. Ao confirmar, o sistema gerará o registro imutável da <strong>Conferência de Recebimento</strong>, atualizará os saldos e lotes FEFO e criará os bens patrimoniais serializados.
        </p>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label class="rpage__label">Local de Estoque de Destino *</label>
            <Dropdown
              v-model="receiveForm.location_id"
              :options="receiveStockLocations"
              option-label="name"
              option-value="id"
              placeholder="Selecione o local de estoque..."
              :loading="receiveLocationsLoading"
              class="w-full"
            />
          </div>
          <div>
            <label class="rpage__label">Observações da Conferência (Opcional)</label>
            <InputText
              v-model="receiveForm.notes"
              placeholder="Ex: Carga entregue lacrada, sem avarias..."
              class="w-full"
            />
          </div>
        </div>

        <div class="inbound-receive-table-wrapper">
          <table class="rpro__inbound-table">
            <thead>
              <tr>
                <th style="min-width: 200px">Item NF-e / Vínculo</th>
                <th style="width: 100px; text-align: right">Qtd NF-e</th>
                <th style="width: 120px; text-align: right">Qtd Recebida</th>
                <th style="min-width: 260px">Rastreabilidade (Lote / Validade / Seriais)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in receiveForm.items" :key="it.item_id">
                <td>
                  <strong>{{ it.description }}</strong>
                  <div class="text-xs text-muted">Cód: {{ it.supplier_code || '-' }}</div>
                  <div class="mt-1">
                    <span v-if="it.target_name !== 'Não vinculado'" class="text-emerald-700 font-bold text-xs">
                      <i class="pi pi-check text-xs" /> {{ it.target_name }}
                    </span>
                    <span v-else class="text-amber-600 font-bold text-xs">
                      <i class="pi pi-exclamation-triangle text-xs" /> Não vinculado
                    </span>
                  </div>
                </td>
                <td style="text-align: right">
                  <strong>{{ Number(it.commercial_quantity) }}</strong>
                  <small class="text-muted ml-1">{{ it.commercial_unit }}</small>
                </td>
                <td style="text-align: right">
                  <InputNumber
                    v-model="it.received_quantity"
                    :min-fraction-digits="0"
                    :max-fraction-digits="3"
                    input-class="text-right w-24 p-1 text-sm font-bold"
                  />
                  <div v-if="Number(it.received_quantity) !== Number(it.commercial_quantity)" class="text-xs text-amber-600 font-bold mt-1">
                    Divergência: {{ (Number(it.received_quantity) - Number(it.commercial_quantity)).toFixed(2) }}
                  </div>
                </td>
                <td>
                  <!-- Controle de Lote e Validade (Perecíveis) -->
                  <div v-if="it.requires_lot || it.tracking_mode === 'LOT_EXPIRATION'" class="grid grid-cols-2 gap-2">
                    <div>
                      <label class="text-xs text-muted block mb-0.5">Lote</label>
                      <InputText v-model="it.lot_number" placeholder="Nº Lote" class="w-full text-xs p-1" />
                    </div>
                    <div>
                      <label class="text-xs text-muted block mb-0.5">Validade</label>
                      <InputText v-model="it.expiration_date" placeholder="AAAA-MM-DD" class="w-full text-xs p-1" />
                    </div>
                  </div>
                  <!-- Controle Serializado (Patrimônio / Equipamentos) -->
                  <div v-else-if="it.requires_serial || it.tracking_mode === 'SERIALIZED'">
                    <label class="text-xs text-muted block mb-0.5">Números de Série (1 por item ou separados por vírgula)</label>
                    <InputText v-model="it.serials_text" placeholder="Ex: SER-001, SER-002" class="w-full text-xs p-1 font-mono" />
                  </div>
                  <!-- Padrão / Quantitativo -->
                  <div v-else class="text-xs text-muted italic">
                    Controle por saldo e custo médio
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="receiveSubmitting" @click="receiveDialogVisible = false">
          Cancelar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="receiveSubmitting || !receiveForm.location_id"
          @click="submitReceiveInvoice"
        >
          <i :class="receiveSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-box'" /> Confirmar Recebimento e Estoque
        </button>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
/**
 * View (MVP) da pagina unica de recurso: ver / criar / editar.
 * O estado e as regras vem do presenter `useResourceForm`; a config visual do
 * modo "ver" vem de `config/detailMeta`. Aqui ficam so o template, a navegacao
 * e a montagem dos dados de exibicao.
 */
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Dialog from "primevue/dialog";
import Dropdown from "primevue/dropdown";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import MultiSelect from "primevue/multiselect";
import Password from "primevue/password";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import Textarea from "primevue/textarea";

import ProductVariationsEditor from "../components/product/ProductVariationsEditor.vue";
import ProductAddonsEditor from "../components/product/ProductAddonsEditor.vue";
import RecipeItemsEditor from "../components/product/RecipeItemsEditor.vue";
import RestaurantFiscalSection from "../components/restaurant/RestaurantFiscalSection.vue";
import FiscalProfileDialog from "../components/restaurant/FiscalProfileDialog.vue";
import PermissionAccordion from "../components/form/PermissionAccordion.vue";
import { useResourceForm } from "../composables/useResourceForm";
import { useAuthStore } from "../stores/auth";
import { ResourceService } from "../services/ResourceService";
import { resolveBranchIdForRestaurant } from "../utils/fiscalBranch";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";
import { useToast } from "primevue/usetoast";
import { detailMetaFor, resolveDetailType } from "../config/detailMeta";
import { formatDateTime, formatMoney, formatPercent, formatQuantity, mapLabel } from "../utils/format";
import { getByPath, resolveColumnValue } from "../utils/object";

const props = defineProps({
  endpoint: { type: String, required: true },
  title: { type: String, required: true },
  columns: { type: Array, default: () => [] },
  formFields: { type: Array, default: null },
  id: { type: String, default: null },
  mode: { type: String, default: "view" },
  globalScope: { type: Boolean, default: false },
  // Recurso compartilhado entre restaurantes (categorias, adicionais, etc.):
  // não injeta o seletor de restaurante e não herda um automaticamente.
  sharedAcrossRestaurants: { type: Boolean, default: false },
});

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const recordId = computed(() => props.id || route.params.id);
const baseName = computed(() => String(route.name).replace(/--(?:create|edit|view)$/, ""));

// Seletor de restaurante: em cadastros com escopo por restaurante (não globalScope),
// sempre exibimos um campo "Restaurante" para vincular o item. O valor padrão é o
// restaurante selecionado no topo (ou o do perfil); vazio quando o escopo é "Todos".
const RESTAURANT_SCOPE_KEY = "starchef-restaurant-scope";
const scopedRestaurantId = localStorage.getItem(RESTAURANT_SCOPE_KEY) || auth.user?.restaurant_id || "";

const augmentedFormFields = computed(() => {
  const fields = props.formFields || [];
  // Só injeta quando: é um formulário, tem escopo por restaurante, não é um recurso
  // compartilhado entre restaurantes e o recurso ainda não define um campo
  // "restaurant" próprio (ex.: kds-estacoes, filiais).
  if (
    !fields.length ||
    props.globalScope ||
    props.sharedAcrossRestaurants ||
    fields.some((field) => field.name === "restaurant")
  ) {
    return fields;
  }
  const restaurantField = {
    name: "restaurant",
    label: "Restaurante",
    type: "remote-dropdown",
    endpoint: "/restaurants/",
    optionLabel: "trade_name",
    optionValue: "id",
    required: true,
    globalScope: true, // opções carregadas sem filtro de escopo (lista todos)
    default: scopedRestaurantId,
    section: "Restaurante",
  };
  // Em 50% (sem `full`). Posiciona logo acima da seção "Disponibilidade" quando
  // ela existe (ex.: Produtos); nos demais recursos, vai ao final.
  const availabilityIndex = fields.findIndex((field) => field.section === "Disponibilidade");
  if (availabilityIndex >= 0) {
    return [...fields.slice(0, availabilityIndex), restaurantField, ...fields.slice(availabilityIndex)];
  }
  return [...fields, restaurantField];
});

// Licenciamento modular: campos atrelados a um modulo que a conta nao tem sao
// omitidos do formulario (nao apenas no template — nao entram no payload/validacao).
// `superuserOnly` esconde campos de uso restrito a superusuário (ex.: escolher
// a conta ao criar um usuário) de qualquer outro perfil.
const visibleFormFields = computed(() =>
  augmentedFormFields.value.filter(
    (field) => auth.hasModule(field.module) && (!field.superuserOnly || auth.user?.is_superuser),
  ),
);

// Agrupa os campos por `section` preservando a ordem de declaração (STC-021).
// Sem nenhuma seção declarada, cai em um único grupo sem título (comportamento antigo).
const formSections = computed(() => {
  const groups = [];
  const byTitle = new Map();
  for (const field of visibleFormFields.value) {
    const title = field.section || "";
    if (!byTitle.has(title)) {
      const group = { title, fields: [] };
      byTitle.set(title, group);
      groups.push(group);
    }
    byTitle.get(title).fields.push(field);
  }
  return groups;
});

// Edição inline: no modo "ver" os campos ficam desabilitados; o botão "Editar"
// habilita na mesma página (sem trocar de rota). `effectiveMode` faz o presenter
// tratar como edição (PATCH) quando o usuário liga o modo de edição a partir do "ver".
const localEdit = ref(false);
const effectiveMode = computed(() => (props.mode === "view" && localEdit.value ? "edit" : props.mode));

// Presenter: dados + validacao + salvamento.
const service = new ResourceService({ endpoint: props.endpoint, globalScope: props.globalScope });
const { isCreate, isEdit, isView, record, formData, fetching, fetchError, saving, saveError, fieldErrors, remoteOptions, reset, fetchRecord, save, loadRemoteOptions } =
  useResourceForm({ service, formFields: visibleFormFields.value, mode: effectiveMode, recordId, sharedAcrossRestaurants: props.sharedAcrossRestaurants });

const modeLabel = computed(() => (isCreate.value ? "Novo" : isEdit.value ? "Editar" : "Detalhe"));
const skeletonCount = computed(() => visibleFormFields.value.length || props.columns.length || 6);

/* ── Navegacao ─────────────────────────────────────────────────────── */
function goToList() {
  router.push({ name: baseName.value });
}
function goToView(id) {
  router.push({ name: `${baseName.value}--view`, params: { id } });
}
// "Editar" no modo ver: habilita os campos na mesma página (sem navegar).
function startEdit() {
  localEdit.value = true;
}
function cancelForm() {
  if (props.mode === "view") {
    // edição inline: volta ao modo leitura descartando alterações não salvas.
    localEdit.value = false;
    reset();
    reload();
    return;
  }
  if (isEdit.value && recordId.value) goToView(recordId.value);
  else goToList();
}
const fiscalSectionRef = ref(null);

async function submit() {
  const saved = await save();
  if (!saved) return; // erros de validacao ja estao em fieldErrors/saveError
  // Botão único: ao salvar o restaurante, salva junto a configuração fiscal
  // embutida na mesma página (dois modelos/endpoints, uma ação só pro usuário).
  if (isRestaurant.value && fiscalSectionRef.value) {
    const fiscalOk = await fiscalSectionRef.value.save();
    if (!fiscalOk) return; // erro já aparece na própria seção fiscal
  }
  if (props.mode === "view") {
    // edição inline concluída: volta ao modo leitura e recarrega o registro.
    localEdit.value = false;
    await reload();
    return;
  }
  const savedId = saved.id || recordId.value;
  if (savedId) goToView(savedId);
  else goToList();
}

/* ── Modo "ver": monta hero, metricas e campos a partir de config/detailMeta ── */
const detailMeta = detailMetaFor(props.endpoint); // estatico por rota (a View remonta por :key)
const isProduct = computed(() => resolveDetailType(props.endpoint) === "product");
const isRecipe = computed(() => props.endpoint.includes("/menu/recipes"));
const isRestaurant = computed(() => props.endpoint === "/restaurants/");
const isOrder = computed(() => resolveDetailType(props.endpoint) === "order");
const isInboundNFe = computed(() => resolveDetailType(props.endpoint) === "inboundNFe" || props.endpoint === "/inbound-nfe/");
const printing = ref(false);
const emittingInvoice = ref(false);
const toast = useToast();

// ── Inbound NF-e Item Mapping & Stock Receipt ────────────────────────
const mapItemDialogVisible = ref(false);
const mappingItem = ref(null);
const mappingForm = reactive({
  targetType: "ingredient", // "ingredient" | "product"
  ingredient_id: null,
  product_id: null,
  conversion_factor: 1,
  save_supplier_mapping: true,
});
const mappingIngredients = ref([]);
const mappingProducts = ref([]);
const mappingLoading = ref(false);
const mappingSubmitting = ref(false);

async function loadMappingOptions() {
  if (mappingIngredients.value.length) return;
  mappingLoading.value = true;
  try {
    const [ingRes, prodRes] = await Promise.all([
      api.get("/menu/ingredients/", { params: { page_size: 200 } }),
      api.get("/menu/products/", { params: { page_size: 200 } }),
    ]);
    mappingIngredients.value = ingRes.data.results || ingRes.data || [];
    mappingProducts.value = prodRes.data.results || prodRes.data || [];
  } catch (err) {
    console.error("Erro ao carregar opções de mapeamento:", err);
  } finally {
    mappingLoading.value = false;
  }
}

async function openMapModal(item) {
  mappingItem.value = item;
  mappingForm.targetType = item.product ? "product" : "ingredient";
  mappingForm.ingredient_id = item.ingredient || null;
  mappingForm.product_id = item.product || null;
  mappingForm.conversion_factor = Number(item.conversion_factor) || 1;
  mappingForm.save_supplier_mapping = true;
  mapItemDialogVisible.value = true;
  await loadMappingOptions();
}

async function submitItemMapping() {
  if (!mappingItem.value?.id) return;
  if (mappingForm.targetType === "ingredient" && !mappingForm.ingredient_id) {
    toast.add({ severity: "warn", summary: "Selecione o Ingrediente", detail: "Escolha um ingrediente para vincular.", life: 3000 });
    return;
  }
  if (mappingForm.targetType === "product" && !mappingForm.product_id) {
    toast.add({ severity: "warn", summary: "Selecione o Produto", detail: "Escolha um produto para vincular.", life: 3000 });
    return;
  }
  mappingSubmitting.value = true;
  try {
    await api.post(`/inbound-nfe-items/${mappingItem.value.id}/map/`, {
      ingredient_id: mappingForm.targetType === "ingredient" ? mappingForm.ingredient_id : null,
      product_id: mappingForm.targetType === "product" ? mappingForm.product_id : null,
      conversion_factor: mappingForm.conversion_factor,
      save_supplier_mapping: mappingForm.save_supplier_mapping,
    });
    toast.add({ severity: "success", summary: "Vínculo salvo", detail: "Item vinculado com sucesso ao estoque.", life: 3000 });
    mapItemDialogVisible.value = false;
    await reload();
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao salvar vínculo", detail: normalizeApiError(err).message, life: 5000 });
  } finally {
    mappingSubmitting.value = false;
  }
}

// ── Recebimento / Entrada de Estoque da NF-e ─────────────────────────
const receiveDialogVisible = ref(false);
const receiveStockLocations = ref([]);
const receiveLocationsLoading = ref(false);
const receiveSubmitting = ref(false);
const receiveForm = reactive({
  location_id: null,
  notes: "",
  items: [],
});

async function openReceiveModal() {
  const unmapped = (record.value?.items || []).filter((it) => !it.ingredient && !it.product);
  if (unmapped.length > 0) {
    toast.add({
      severity: "warn",
      summary: "Itens sem vínculo",
      detail: `Existem ${unmapped.length} item(ns) sem produto/ingrediente vinculado. Vincule todos antes de aplicar a entrada.`,
      life: 6000,
    });
  }

  receiveForm.notes = "";
  receiveForm.items = (record.value?.items || []).map((it) => ({
    item_id: it.id,
    description: it.description,
    supplier_code: it.supplier_code,
    target_name: it.product_name ? `Produto: ${it.product_name}` : (it.ingredient_name ? `Ingrediente: ${it.ingredient_name}` : "Não vinculado"),
    tracking_mode: it.product_tracking_mode || "QUANTITY",
    requires_lot: it.product_requires_lot_control || false,
    requires_serial: it.product_requires_serial_number || false,
    commercial_quantity: it.commercial_quantity,
    commercial_unit: it.commercial_unit,
    conversion_factor: it.conversion_factor,
    received_quantity: Number(it.commercial_quantity),
    accepted_quantity: Number(it.commercial_quantity),
    rejected_quantity: 0,
    lot_number: "",
    expiration_date: "",
    serials_text: "",
  }));

  receiveDialogVisible.value = true;
  receiveLocationsLoading.value = true;
  try {
    const { data } = await api.get("/stock/locations/", { params: { page_size: 100 } });
    receiveStockLocations.value = data.results || data || [];
    if (receiveStockLocations.value.length && !receiveForm.location_id) {
      receiveForm.location_id = receiveStockLocations.value[0].id;
    }
  } catch (err) {
    console.error("Erro ao carregar locais de estoque:", err);
  } finally {
    receiveLocationsLoading.value = false;
  }
}

async function submitReceiveInvoice() {
  if (!receiveForm.location_id) {
    toast.add({ severity: "warn", summary: "Selecione o local de estoque", detail: "Informe onde os produtos serão armazenados.", life: 4000 });
    return;
  }
  receiveSubmitting.value = true;
  try {
    const payload = {
      location_id: receiveForm.location_id,
      notes: receiveForm.notes || "",
      items: receiveForm.items.map((it) => ({
        item_id: it.item_id,
        received_quantity: it.received_quantity,
        accepted_quantity: it.received_quantity,
        rejected_quantity: 0,
        lot_number: it.lot_number || "",
        expiration_date: it.expiration_date || null,
        serials: it.serials_text
          ? it.serials_text.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean)
          : [],
      })),
    };
    const { data } = await api.post(`/inbound-nfe/${recordId.value}/receive/`, payload);
    toast.add({
      severity: "success",
      summary: "Entrada Concluída!",
      detail: `Conferência ${data.receipt_number || ""} gerada e estoque atualizado com sucesso.`,
      life: 5000,
    });
    receiveDialogVisible.value = false;
    await reload();
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao dar entrada no estoque", detail: normalizeApiError(err).message, life: 6000 });
  } finally {
    receiveSubmitting.value = false;
  }
}

/* ── Criação rápida a partir de um remote-dropdown (ex.: perfil fiscal no
   formulário de produto) — o mesmo diálogo usado na seção fiscal do
   restaurante, disparado por um "+" ao lado do campo (`field.quickCreate`). */
const quickCreateLoading = ref(false);
const quickCreateField = ref(null);
const quickCreateRestaurantId = ref(null);
const quickCreateBranchId = ref(null);
const fiscalProfileDialogOpen = ref(false);

async function openQuickCreate(field) {
  if (field.quickCreate !== "fiscal-profile") return;
  const restaurantId = formData.restaurants?.[0] || formData.restaurant || null;
  if (!restaurantId) {
    toast.add({ severity: "warn", summary: "Selecione um restaurante primeiro", life: 3500 });
    return;
  }
  quickCreateLoading.value = true;
  try {
    const branchId = await resolveBranchIdForRestaurant(restaurantId);
    if (!branchId) {
      toast.add({ severity: "warn", summary: "Não foi possível carregar a configuração fiscal deste restaurante. Tente novamente.", life: 4000 });
      return;
    }
    quickCreateField.value = field;
    quickCreateRestaurantId.value = restaurantId;
    quickCreateBranchId.value = branchId;
    fiscalProfileDialogOpen.value = true;
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível preparar a criação", detail: normalizeApiError(err).message, life: 4000 });
  } finally {
    quickCreateLoading.value = false;
  }
}

function onQuickCreateSaved(saved) {
  const field = quickCreateField.value;
  if (!field) return;
  const options = remoteOptions[field.name] || [];
  options.push({ label: saved.name, value: saved.id, group: "", description: "" });
  remoteOptions[field.name] = options;
  formData[field.name] = saved.id;
  toast.add({ severity: "success", summary: "Perfil fiscal criado", life: 2500 });
}

/** Gera a nota (PrintJob) e abre a janela de impressão com o HTML retornado. */
async function printOrder() {
  printing.value = true;
  try {
    const { data } = await api.post(`/orders/${recordId.value}/print/`, { job_type: "receipt" });
    const win = window.open("", "_blank", "width=380,height=640");
    if (win) {
      win.document.write(data.html || "<p>Sem conteúdo para impressão.</p>");
      win.document.close();
      win.focus();
      win.print();
    } else {
      toast.add({ severity: "warn", summary: "Pop-up bloqueado", detail: "Libere pop-ups para imprimir.", life: 4000 });
    }
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao imprimir", detail: normalizeApiError(err).message, life: 5000 });
  } finally {
    printing.value = false;
  }
}

/** Emite a NFC-e do pedido visualizado e abre o DANFE para impressao. */
async function emitOrderInvoice() {
  if (!recordId.value || emittingInvoice.value) return;
  emittingInvoice.value = true;
  try {
    const { data: invoice } = await api.post("/invoices/emit/", {
      order: recordId.value,
      ...(record.value?.customer_document ? { cpf: record.value.customer_document } : {}),
      ...(record.value?.customer_name ? { cpf_name: record.value.customer_name } : {}),
    });
    const { data: printJob } = await api.post(`/invoices/${invoice.id}/print/`, {});
    const win = window.open("", "_blank", "width=420,height=720");
    if (!win) {
      toast.add({ severity: "warn", summary: "Pop-up bloqueado", detail: "Libere pop-ups para imprimir o DANFE.", life: 4000 });
      return;
    }
    win.document.write(printJob.html || "<p>DANFE indisponível.</p>");
    win.document.close();
    win.focus();
    win.print();
    toast.add({ severity: "success", summary: "NFC-e emitida", detail: "DANFE preparado para impressão.", life: 4000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível emitir a NFC-e", detail: normalizeApiError(err).message, life: 5000 });
  } finally {
    emittingInvoice.value = false;
  }
}

/** Abre o pedido no PDV para edição (adicionar/remover itens). */
function editOrder() {
  router.push({ name: "pedido-editar-itens", params: { id: recordId.value } });
}

/** Junta variações + adicionais de um item do pedido numa linha de texto. */
function itemExtras(item) {
  const parts = [];
  for (const v of item.variations || []) parts.push(typeof v === "string" ? v : v?.name || "");
  for (const a of item.addons || []) parts.push(a.addon_name || a.name || "");
  return parts.filter(Boolean).join(" · ");
}

function defaultTitle(row) {
  return row?.name || row?.trade_name || row?.username || row?.number || row?.id || "-";
}
const viewTitle = computed(() => {
  if (!record.value) return "-";
  return detailMeta.title ? detailMeta.title(record.value) : defaultTitle(record.value);
});
const viewSubtitle = computed(() => (record.value && detailMeta.subtitle ? detailMeta.subtitle(record.value) : ""));
const heroBadge = computed(() => (record.value && detailMeta.badge ? detailMeta.badge(record.value) : null));

const detailMetrics = computed(() => {
  if (!record.value) return [];
  return (detailMeta.metrics || []).map((metric) => {
    let display = formatField(record.value, metric.key, metric.type, metric.map);
    if (metric.suffix && display !== "-") display = `${display}${metric.suffix}`;
    return { label: metric.label, display };
  });
});

const detailFields = computed(() => {
  if (!record.value) return [];
  // Campos ja exibidos como metrica/badge nao se repetem no grid.
  const excluded = new Set((detailMeta.metrics || []).map((metric) => metric.key));
  if (detailMeta.badgeKey) excluded.add(detailMeta.badgeKey);
  return props.columns
    .filter((column) => !excluded.has(column.key))
    .map((column) => ({ ...column, _value: resolveColumnValue(record.value, column) }));
});

/** Formata um valor pontual do registro conforme o tipo declarado na metrica. */
function formatField(row, key, type, map) {
  const cellValue = getByPath(row, key);
  if (type === "money") return formatMoney(cellValue);
  if (type === "date") return dateTime(cellValue);
  if (type === "percent") return formatPercent(cellValue);
  if (type === "boolean") return cellValue ? "Ativo" : "Inativo";
  if (cellValue == null || cellValue === "") return "-";
  return map ? map[cellValue] || cellValue : cellValue;
}

/* ── Helpers de exibicao (delegam aos utils) ─────────────────────────── */
const label = mapLabel;
const money = formatMoney;
const quantity = formatQuantity;
const dateTime = (value) => formatDateTime(value, { withYear: true });

/**
 * Placeholder do campo. Em modo "ver" nunca mostra o texto de instrucao
 * (ex.: "Selecionar categoria") — esse texto e uma orientacao de preenchimento,
 * nao um dado; um campo vazio em leitura mostra so um travessao.
 */
function fieldPlaceholder(field, fallback) {
  if (isView.value) return "—";
  return field.placeholder || fallback;
}

/* Agrupa as opções remotas (que já vêm com `group`) no formato que o MultiSelect
 * espera para option groups: [{ label, items: [{ label, value }] }]. A ordem dos
 * grupos segue a primeira ocorrência (o backend já entrega ordenado). */
function groupedOptions(name) {
  const options = remoteOptions[name] || [];
  const buckets = new Map();
  const groups = [];
  for (const option of options) {
    const groupLabel = option.group || "Outros";
    let bucket = buckets.get(groupLabel);
    if (!bucket) {
      bucket = { label: groupLabel, items: [] };
      buckets.set(groupLabel, bucket);
      groups.push(bucket);
    }
    bucket.items.push(option);
  }
  return groups;
}

/* ── Ciclo de vida: carrega ao montar e ao trocar de registro/modo ───── */
async function reload() {
  await Promise.all([fetchRecord(), loadRemoteOptions()]);
}
onMounted(reload);
watch(() => [recordId.value, props.mode], async () => {
  reset();
  await reload();
});
</script>

<style scoped>
.rpage {
  display: flex;
  flex-direction: column;
  gap: 18px;
  width: 100%;
}

/* ── Header ─────────────────────────────────────────────────────────── */
.rpage__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.rpage__crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.rpage__back {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  color: var(--text-muted);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  cursor: pointer;
  transition: background var(--dur-base), color var(--dur-base), border-color var(--dur-base);
}

.rpage__back:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong, var(--border));
  color: var(--text-body);
}

.rpage__back .pi-arrow-left { font-size: 11px; }
.rpage__sep { font-size: 10px; color: var(--text-subtle); }
.rpage__crumb { color: var(--text-strong); font: var(--weight-bold) 13px/1 var(--font-sans); }

.rpage__head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── Card (form + skeleton) ─────────────────────────────────────────── */
.rpage__card {
  width: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.rpage__card-head {
  padding: 16px var(--card-pad);
  border-bottom: 1px solid var(--border-subtle);
}

.rpage__card-head h2 {
  color: var(--text-strong);
  font: var(--weight-extra) 20px/1.2 var(--font-sans);
}

.rpage__card-head p {
  margin-top: 5px;
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.5 var(--font-sans);
}

/* ── Fields grid (form) ─────────────────────────────────────────────── */
.rpage__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--field-gap-y) var(--field-gap-x);
  padding: var(--card-pad);
}

/* Seções do formulário (STC-021) */
.rpage__section { display: flex; flex-direction: column; }
.rpage__section + .rpage__section { border-top: 1px solid var(--border-subtle); }
.rpage__section-title {
  padding: 14px var(--card-pad) 0;
  color: var(--text-strong);
  font: var(--weight-extra) 13px/1.2 var(--font-sans);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.rpage__section .rpage__grid { padding-top: 12px; }

.rpage__field { display: flex; flex-direction: column; gap: var(--field-label-gap); }
.rpage__field--full { grid-column: 1 / -1; }
.rpage__field--error .rpage__label { color: #dc2626; }
.rpage__field--error .rpage__input,
.rpage__field--error :deep(.p-inputtext),
.rpage__field--error :deep(.p-dropdown),
.rpage__field--error :deep(.p-textarea) {
  border-color: #ef4444 !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, #ef4444 12%, transparent) !important;
}

.rpage__label { display: inline-flex; align-items: center; gap: 5px; color: var(--text-strong); font: var(--weight-bold) 12.5px/1.2 var(--font-sans); letter-spacing: 0.01em; }
.rpage__required { color: #ef4444; margin-left: 3px; }
.rpage__help-icon { color: var(--text-muted); font-size: 12px; cursor: help; }
.rpage__help-icon:hover { color: var(--text-strong); }

.rpage__input {
  width: 100%;
  height: var(--control-h);
  padding: 0 var(--control-pad-x);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-strong);
  font: var(--weight-medium) var(--control-font)/1 var(--font-sans);
  transition: border-color 120ms, box-shadow 120ms;
}
.rpage__input:focus {
  outline: none;
  border-color: var(--ring);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
}
.rpage__input:is(textarea) { height: auto; padding: 11px 13px; resize: vertical; line-height: 1.55; }
.rpage__select { width: 100%; }
.rpage__password { width: 100%; }
.rpage__field-row { display: flex; align-items: center; gap: 6px; }
.rpage__field-row .rpage__select { flex: 1; }

.rpage__switch-row { display: flex; align-items: center; gap: 12px; height: var(--control-h); }
.rpage__switch-label { color: var(--text-body); font: var(--weight-semibold) 13.5px/1 var(--font-sans); }

.rpage__field-err { display: flex; align-items: center; gap: 6px; color: #ef4444; font: var(--weight-medium) 12px/1.3 var(--font-sans); }
.rpage__field-err .pi { font-size: 12px; }

/* ── Modo leitura (view): mesma tela do editar, com os campos desabilitados ──
   Estilo "ghost/outline": fundo transparente, borda suave e texto legível —
   sem o cinza opaco padrão de input desabilitado. Ao clicar em "Editar" o modo
   muda na mesma página e os campos ficam habilitados. */
.rpage__card--readonly .rpage__label { color: var(--text-muted); }

.rpage__card--readonly .rpage__input:disabled,
.rpage__card--readonly :deep(.p-inputtext:disabled),
.rpage__card--readonly :deep(.p-inputnumber-input:disabled),
.rpage__card--readonly :deep(.p-dropdown.p-disabled),
.rpage__card--readonly :deep(.p-multiselect.p-disabled),
.rpage__card--readonly :deep(.p-inputtextarea:disabled) {
  opacity: 1;
  background: transparent;
  border-color: var(--border-subtle);
  color: var(--text-body);
  cursor: default;
}
.rpage__card--readonly :deep(.p-dropdown.p-disabled .p-dropdown-label),
.rpage__card--readonly :deep(.p-multiselect.p-disabled .p-multiselect-label) {
  color: var(--text-body);
}
/* Esconde seta/limpar dos selects em leitura (não há o que abrir) */
.rpage__card--readonly :deep(.p-dropdown-trigger),
.rpage__card--readonly :deep(.p-dropdown-clear-icon),
.rpage__card--readonly :deep(.p-multiselect-trigger) {
  opacity: 0.4;
}
.rpage__card--readonly :deep(.p-inputswitch.p-disabled) { opacity: 0.7; }

.rpage__alert {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}
.rpage__alert--error {
  background: color-mix(in srgb, #ef4444 9%, var(--surface-card));
  border: 1px solid color-mix(in srgb, #ef4444 24%, transparent);
  color: #dc2626;
}
.rpage__alert--inline { margin: 0 var(--card-pad); }

.rpage__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px var(--card-pad);
  border-top: 1px solid var(--border-subtle);
  background: transparent; /* mesma cor do corpo do formulário (card) */
}

/* ── View mode ──────────────────────────────────────────────────────── */
.rpage__view { display: flex; flex-direction: column; gap: 16px; }

.detail-hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px 24px;
  border-radius: var(--radius-lg);
  color: #fff;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.detail-hero__avatar {
  width: 58px; height: 58px; flex-shrink: 0;
  display: grid; place-items: center;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.18);
  font-size: 25px;
}
.detail-hero__headline { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.detail-hero__headline span { font: var(--weight-bold) 11px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); opacity: 0.85; }
.detail-hero__headline h2 { overflow: hidden; font: var(--weight-extra) 24px/1.15 var(--font-sans); text-overflow: ellipsis; white-space: nowrap; }
.detail-hero__headline p { font: var(--weight-semibold) 13px/1.3 var(--font-sans); opacity: 0.92; }
.detail-hero__badge {
  flex-shrink: 0;
  padding: 6px 12px;
  border-radius: var(--radius-pill);
  background: rgba(255, 255, 255, 0.22);
  border: 1px solid rgba(255, 255, 255, 0.32);
  color: #fff;
  font: var(--weight-extra) 12px/1 var(--font-sans);
  white-space: nowrap;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.detail-metric {
  display: flex; flex-direction: column; gap: 7px;
  padding: 15px 17px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  box-shadow: var(--shadow-xs);
}
.detail-metric span { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.detail-metric strong { color: var(--text-strong); font: var(--weight-extra) 20px/1.1 var(--font-sans); }

/* Secoes extras dentro do form (ex.: variacoes/ficha tecnica de produto) */
.rpage__extra {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 0 var(--card-pad) var(--card-pad); /* mesmo padding das demais seções */
}
.rpage__hint {
  padding: 14px 16px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.4 var(--font-sans);
}

.detail-section {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.detail-section__title {
  display: flex; align-items: center; gap: 8px;
  padding: 15px 18px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-strong);
  font: var(--weight-extra) 14px/1.2 var(--font-sans);
}
.detail-section__title small { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }

.detail-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--border-subtle);
}
.detail-field { display: flex; flex-direction: column; gap: 7px; padding: 14px 18px; background: var(--surface-card); }
.detail-field__label { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.detail-field__value { color: var(--text-strong); font: var(--weight-semibold) 13.5px/1.4 var(--font-sans); word-break: break-word; }
.detail-field__money { color: var(--success-text); font: var(--weight-extra) 14.5px/1 var(--font-sans); }

.detail-list { display: flex; flex-direction: column; }
.detail-list__row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.detail-list__row:last-child { border-bottom: none; }
.detail-list__row span { min-width: 0; overflow: hidden; color: var(--text-body); font: var(--weight-semibold) 13px/1.25 var(--font-sans); text-overflow: ellipsis; white-space: nowrap; }
.detail-list__row strong { flex-shrink: 0; color: var(--text-strong); font: var(--weight-bold) 12.5px/1 var(--font-sans); }

/* Itens do pedido — DataTable no mesmo padrão das variações/adicionais */
.order-items { padding: 0 6px 8px; }
.order-items :deep(.p-datatable-thead > tr > th) {
  padding: 7px 12px;
  background: transparent;
  color: var(--text-subtle);
  border-color: var(--border-subtle);
  font: var(--weight-bold) 10.5px/1 var(--font-table);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.order-items :deep(.p-datatable-thead > tr > th.dt-col-right .p-column-header-content) { justify-content: flex-end; }
.order-items :deep(.p-datatable-tbody > tr) { background: var(--surface-sunken); }
.order-items :deep(.p-datatable-tbody > tr > td) {
  padding: 8px 12px;
  border-color: var(--border-subtle);
  font: var(--weight-medium) 13.5px/1.3 var(--font-table);
  color: var(--text-body);
  background: transparent;
}
.order-items__product { display: flex; flex-direction: column; gap: 2px; }
.order-items__product strong { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-table); }
.order-items__product small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.3 var(--font-sans); }
.order-items__note { color: var(--warning-text); }

/* Hero accents */
.accent--violet  { background: linear-gradient(135deg, #7c3aed, #4f46e5); }
.accent--blue    { background: linear-gradient(135deg, #2563eb, #1d4ed8); }
.accent--green   { background: linear-gradient(135deg, #059669, #047857); }
.accent--amber   { background: linear-gradient(135deg, #d97706, #b45309); }
.accent--rose    { background: linear-gradient(135deg, #e11d48, #be123c); }
.accent--teal    { background: linear-gradient(135deg, #0d9488, #0f766e); }
.accent--indigo  { background: linear-gradient(135deg, #4338ca, #3730a3); }
.accent--slate   { background: linear-gradient(135deg, #475569, #334155); }

/* Status chip */
.status-chip {
  display: inline-flex; align-items: center; width: fit-content;
  padding: 3px 9px; border-radius: 99px; border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans); white-space: nowrap; color: #fff; background: #475569;
}
.status-chip[data-status="open"]             { background: #2563eb; }
.status-chip[data-status="sent_to_kitchen"]  { background: #7c3aed; }
.status-chip[data-status="preparing"]        { background: #4338ca; }
.status-chip[data-status="partially_ready"]  { background: #0891b2; }
.status-chip[data-status="ready"]            { background: #059669; }
.status-chip[data-status="delivered"]        { background: #16a34a; }
.status-chip[data-status="awaiting_payment"] { background: #d97706; }
.status-chip[data-status="paid"]             { background: #047857; }
.status-chip[data-status="cancelled"]        { background: #b91c1c; }
.status-chip[data-status="refunded"]         { background: #be185d; }
.status-chip[data-status="free"]      { background: #047857; }
.status-chip[data-status="occupied"]  { background: #b91c1c; }
.status-chip[data-status="reserved"]  { background: #1d4ed8; }
.status-chip[data-status="cleaning"]  { background: #b45309; }
.status-chip[data-status="closed"]    { background: #475569; }
.status-chip[data-status="issued"]    { background: #047857; }
.status-chip[data-status="draft"]     { background: #64748b; }
.status-chip[data-status="error"]     { background: #b91c1c; }
.status-chip[data-status="in"]          { background: #047857; }
.status-chip[data-status="out"]         { background: #b91c1c; }
.status-chip[data-status="adjustment"]  { background: #b45309; }
.status-chip[data-status="sale"]        { background: #7c3aed; }
.status-chip[data-status="inventory"]   { background: #475569; }
.status-chip[data-status="admin"]    { background: #b91c1c; }
.status-chip[data-status="owner"]    { background: #7c3aed; }
.status-chip[data-status="manager"]  { background: #1d4ed8; }
.status-chip[data-status="waiter"]   { background: #0891b2; }
.status-chip[data-status="kitchen"]  { background: #d97706; }
.status-chip[data-status="cashier"]  { background: #059669; }
.status-chip[data-status="driver"]   { background: #475569; }

/* ── PrimeVue structural overrides ──────────────────────────────────── */
:deep(.p-inputtext) { width: 100%; height: var(--control-h); padding: 0 var(--control-pad-x); font: var(--weight-medium) var(--control-font)/1 var(--font-sans); }
:deep(.p-dropdown) { width: 100%; height: var(--control-h); }
:deep(.p-dropdown-label),
:deep(.p-dropdown-label.p-inputtext) { display: flex; align-items: center; height: 100%; padding: 0 var(--control-pad-x); font: var(--weight-medium) var(--control-font)/1 var(--font-sans); }
:deep(.p-dropdown-panel) { z-index: 9999 !important; }
:deep(.p-multiselect) { width: 100%; min-height: var(--control-h); }
:deep(.p-multiselect-label) { padding: 6px var(--control-pad-x); font: var(--weight-medium) var(--control-font)/1.3 var(--font-sans); }
:deep(.p-multiselect-panel) { z-index: 9999 !important; }
:deep(.p-textarea) { width: 100%; padding: 8px var(--control-pad-x); font: var(--weight-medium) var(--control-font)/1.55 var(--font-sans); resize: vertical; }
:deep(.p-password) { width: 100%; }
:deep(.p-password input) { width: 100%; height: var(--control-h); }
:deep(.p-button) { height: var(--control-h); font: var(--weight-bold) var(--control-font)/1 var(--font-sans); border-radius: var(--radius-md); }

:deep(.p-tag) { border: 1px solid transparent; font: var(--weight-extra) 11px/1 var(--font-sans); }
:deep(.p-tag.p-tag-success) { background: #047857; border-color: #065f46; color: #fff; }
:deep(.p-tag.p-tag-danger) { background: #b91c1c; border-color: #991b1b; color: #fff; }

/* ── Estilos da Seção de NF-e de Entrada ──────────────────────────── */
.detail-section--inbound {
  padding: 24px;
}

.detail-section__header-flex {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.detail-section__header-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rpro__inbound-received-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: color-mix(in srgb, #059669 10%, var(--surface-card));
  border: 1px solid color-mix(in srgb, #059669 25%, transparent);
  border-radius: var(--radius-md);
}

.inbound-items-table :deep(.p-datatable-thead > tr > th) {
  background: var(--surface-sunken);
  color: var(--text-subtle);
  font-size: 11px;
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

.inbound-items-table :deep(.p-datatable-tbody > tr > td) {
  padding: 12px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
}

.inbound-item-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.inbound-item-title {
  font-size: 13.5px;
  font-weight: var(--weight-semibold);
  color: var(--text-strong);
}

.inbound-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.inbound-item-meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-muted);
}

.inbound-item-taxes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.inbound-tax-badge {
  display: inline-flex;
  padding: 1px 6px;
  background: color-mix(in srgb, var(--brand) 8%, var(--surface-card));
  border: 1px solid color-mix(in srgb, var(--brand) 20%, transparent);
  border-radius: 3px;
  font-size: 10.5px;
  color: var(--brand);
}

.inbound-mapping-linked {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.inbound-mapping-linked-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.inbound-modal-item-summary {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.inbound-receive-table-wrapper {
  max-height: 340px;
  overflow-y: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

/* ── Responsive ─────────────────────────────────────────────────────── */
@media (max-width: 760px) {
  .rpage__grid { grid-template-columns: 1fr; padding: 20px; gap: 18px; }
  .rpage__field--full { grid-column: 1; }
  .rpage__card-head { padding: 18px 20px 16px; }
  .rpage__footer { padding: 14px 20px; }
  .rpage__alert--inline { margin: 0 20px; }
  .rpage__extra { padding: 0 20px 20px; }
  .detail-fields { grid-template-columns: 1fr; }
}
</style>
