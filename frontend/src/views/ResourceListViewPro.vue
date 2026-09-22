<template>
  <div class="rpro" :class="{ 'rpro--inbound': props.endpoint === '/inbound-nfe/' }">
    <!-- ── Cabeçalho: título + ações (Export / Import / ação primária) ── -->
    <header class="rpro__head">
      <div class="rpro__head-top" :class="{ 'rpro__head-top--inbound': props.endpoint === '/inbound-nfe/' }">
        <div class="rpro__head-copy">
          <h1>{{ title }}</h1>
          <p>{{ total }} {{ total === 1 ? "registro" : "registros" }}</p>
        </div>
        <div class="rpro__head-actions">
          <template v-if="props.endpoint === '/inbound-nfe/'">
            <button
              class="rpro-btn rpro-btn--ghost rpro__export-selected"
              type="button"
              :disabled="exportInboundLoading"
              :title="selection.length ? `Exportar ${selection.length} nota(s) selecionada(s) em XML` : 'Selecione as notas desejadas na tabela para exportar em XML'"
              @click="exportInboundXml(false)"
            >
              <i :class="exportInboundLoading && !isExportingAll ? 'pi pi-spin pi-spinner' : 'pi pi-file-export'" />
              Exportar Selecionadas {{ selection.length ? `(${selection.length})` : '' }}
            </button>
            <button
              class="rpro-btn rpro-btn--ghost"
              type="button"
              :disabled="exportInboundLoading"
              title="Exportar todas as notas fiscais em arquivo compactado (.ZIP com os XMLs individuais)"
              @click="exportInboundXml(true)"
            >
              <i :class="exportInboundLoading && isExportingAll ? 'pi pi-spin pi-spinner' : 'pi pi-download'" />
              Exportar Tudo (XML)
            </button>
          </template>
          <template v-else>
            <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="exchangeLoading" @click="exportRows">
              <i class="pi pi-upload" /> Export
            </button>
            <button v-if="formEnabled" class="rpro-btn rpro-btn--ghost" type="button" @click="importVisible = true">
              <i class="pi pi-download" /> Import
            </button>
          </template>
          <button
            v-for="headerAction in headerActions"
            :key="headerAction.key"
            class="rpro-btn rpro-btn--ghost"
            type="button"
            :disabled="syncingSefaz || (headerAction.type === 'sync-sefaz' && isDfeBlocked)"
            :title="headerAction.type === 'sync-sefaz' && isDfeBlocked ? (dfeSyncInfo?.blocked_reason || `Aguarde a janela de segurança da SEFAZ até ${formatDfeDate(dfeSyncInfo?.next_allowed_at)} (~${dfeMinutesRemaining} min restantes)`) : undefined"
            @click="runHeaderAction(headerAction)"
          >
            <i :class="[headerAction.icon || 'pi pi-bolt', { 'pi-spin': syncingSefaz && headerAction.type === 'sync-sefaz' }]" />
            {{ syncingSefaz && headerAction.type === 'sync-sefaz' ? 'Sincronizando...' : (headerAction.type === 'sync-sefaz' && isDfeBlocked) ? `Aguarde (~${dfeMinutesRemaining}m)` : headerAction.label }}
          </button>
          <button v-if="primaryAction" class="rpro-btn rpro-btn--primary" type="button" @click="runPrimary">
            <i :class="primaryAction.icon || 'pi pi-plus'" /> {{ primaryAction.label }}
          </button>
          <InboundHelpButton v-if="props.endpoint === '/inbound-nfe/' && proCfg.description" class="rpro__help-action" :description="proCfg.description" />
        </div>
      </div>
      <template v-if="props.endpoint === '/inbound-nfe/' && dfeSyncInfo">
        <div class="rpro__head-banner">
          <div v-if="dfeSyncInfo.is_all_restaurants" class="rpro__dfe-alert rpro__dfe-alert--info">
            <div class="rpro__dfe-alert-icon"><i class="pi pi-building" /></div>
            <div class="rpro__dfe-alert-info">
              <div class="rpro__dfe-alert-head">
                <strong>Visão Global · Todas as Unidades</strong>
                <span class="rpro__dfe-pill">Multilojas</span>
              </div>
              <p>
                Você está visualizando as notas de compras de todas as empresas cadastradas. A rotina automática de consulta na SEFAZ roda em segundo plano a cada <strong>{{ dfeSyncInfo.sync_interval_hours || 5 }} horas</strong> para todos os restaurantes com certificado A1 ativo.
              </p>
              <div v-if="dfeSyncInfo.last_sync_at" class="mt-2 text-xs font-semibold text-neutral-300 flex items-center gap-2">
                <i class="pi pi-history text-xs text-primary" />
                <span>Última verificação automática registrada: <strong>{{ formatDfeDate(dfeSyncInfo.last_sync_at) }}</strong></span>
              </div>
            </div>
          </div>

          <div v-else-if="dfeSyncInfo.has_certificate === false" class="rpro__dfe-alert rpro__dfe-alert--warning">
            <div class="rpro__dfe-alert-icon"><i class="pi pi-shield" /></div>
            <div class="rpro__dfe-alert-info">
              <div class="rpro__dfe-alert-head">
                <strong>Certificado A1 Não Configurado · {{ dfeSyncInfo.restaurant_name }}</strong>
                <span class="rpro__dfe-pill rpro__dfe-pill--warning">Pendente</span>
              </div>
              <p>
                Para consultar e puxar automaticamente as notas fiscais emitidas contra este restaurante, acesse o <strong>Perfil do Restaurante (aba Fiscal)</strong> para anexar o Certificado Digital A1 (.pfx) e definir o NSU inicial.
              </p>
            </div>
          </div>

          <div v-else class="rpro__dfe-banner">
            <div class="rpro__dfe-card">
              <div class="rpro__dfe-card-icon rpro__dfe-card-icon--nsu">
                <i class="pi pi-hashtag" />
              </div>
              <div class="rpro__dfe-card-info">
                <div class="rpro__dfe-card-top">
                  <span class="rpro__dfe-card-label">Último NSU</span>
                  <span class="rpro__dfe-badge">{{ dfeSyncInfo.restaurant_name }}</span>
                </div>
                <strong class="rpro__dfe-card-value font-mono">{{ dfeSyncInfo.ult_nsu || '000000000000000' }}</strong>
                <small class="rpro__dfe-card-hint">
                  <i class="pi pi-shield text-xs" /> Gerenciado no perfil fiscal
                </small>
              </div>
            </div>

            <div class="rpro__dfe-card">
              <div class="rpro__dfe-card-icon rpro__dfe-card-icon--sync">
                <i class="pi pi-history" />
              </div>
              <div class="rpro__dfe-card-info">
                <span class="rpro__dfe-card-label">Última Verificação SEFAZ</span>
                <strong class="rpro__dfe-card-value font-mono text-sm">{{ formatDfeDate(dfeSyncInfo.last_sync_at) }}</strong>
                <small class="rpro__dfe-card-hint flex items-center gap-1.5 mt-1">
                  <span v-if="dfeSyncInfo.cstat" :class="['rpro__dfe-tag', `rpro__dfe-tag--${dfeSyncInfo.cstat === '138' ? 'success' : dfeSyncInfo.cstat === '656' ? 'danger' : 'info'}`]">
                    cStat {{ dfeSyncInfo.cstat }}
                  </span>
                  <span>{{ dfeSyncInfo.cstat === '656' ? 'Consumo Indevido' : dfeSyncInfo.cstat === '138' ? 'Notas localizadas' : dfeSyncInfo.cstat === '137' ? 'Sem novas notas' : 'Automático a cada 5h' }}</span>
                </small>
              </div>
            </div>

            <div class="rpro__dfe-card" :class="{ 'rpro__dfe-card--blocked': isDfeBlocked }">
              <div class="rpro__dfe-card-icon" :class="isDfeBlocked ? 'rpro__dfe-card-icon--blocked' : 'rpro__dfe-card-icon--ready'">
                <i :class="isDfeBlocked ? 'pi pi-lock' : 'pi pi-check-circle'" />
              </div>
              <div class="rpro__dfe-card-info">
                <span class="rpro__dfe-card-label">Próxima Consulta Permitida</span>
                <strong class="rpro__dfe-card-value" :class="isDfeBlocked ? 'text-amber-600' : 'text-emerald-600'">
                  {{ isDfeBlocked ? formatDfeDate(dfeSyncInfo.next_allowed_at) : 'Pronta para sincronizar' }}
                </strong>
                <small class="rpro__dfe-card-hint">
                  <span v-if="isDfeBlocked" class="text-amber-700 font-semibold flex items-center gap-1">
                    <i class="pi pi-hourglass" /> Bloqueio ativo (~{{ dfeMinutesRemaining }} min restantes)
                  </span>
                  <span v-else class="text-emerald-700 font-semibold flex items-center gap-1">
                    <i class="pi pi-shield" /> Intervalo seguro liberado
                  </span>
                </small>
              </div>
            </div>

            <button class="rpro__dfe-card rpro__dfe-card--action" type="button" aria-label="Buscar nota por NSU" @click="openFetchNsuDialog">
              <span class="rpro__dfe-card-icon rpro__dfe-card-icon--fetch">
                <i class="pi pi-search" />
              </span>
              <span class="rpro__dfe-card-info">
                <span class="rpro__dfe-card-label">Consulta Pontual</span>
                <strong class="rpro__dfe-card-value text-brand">Buscar por NSU</strong>
                <small class="rpro__dfe-card-hint">
                  <span><i class="pi pi-bolt text-xs" /> Recuperar via consNSU</span>
                </small>
              </span>
            </button>
          </div>
        </div>
      </template>
    </header>

    <!-- Filtro que chegou por um link de outra tela (ex.: "ver movimentacoes deste insumo"). -->
    <div v-if="linkFilterLabels.length" class="rpro__linkfilter">
      <i class="pi pi-filter" />
      <span>Lista recortada por {{ linkFilterLabels.join(" e ") }}, a pedido da tela anterior.</span>
      <button type="button" @click="clearLinkFilters">Ver tudo</button>
    </div>

    <!-- Descrição opcional do recurso -->
    <div v-if="proCfg.description && props.endpoint !== '/inbound-nfe/'" class="rpro__description-box">
      <i class="pi pi-info-circle" />
      <p>{{ proCfg.description }}</p>
    </div>

    <!-- ── Toolbar: busca + período · mais filtros + engrenagem ───────── -->
    <button class="rpro__mobile-filter-trigger" type="button" @click="mobileFiltersOpen = true">
      <i class="pi pi-sliders-h" />
      <span>Filtros e opções</span>
      <small v-if="activeFilterCount">{{ activeFilterCount }}</small>
    </button>

    <div class="rpro__toolbar" :class="{ 'rpro__toolbar--mobile-open': mobileFiltersOpen }">
      <div class="rpro__mobile-drawer-head">
        <div><span>Organizar tabela</span><h2>Filtros e opções</h2></div>
        <button type="button" aria-label="Fechar filtros" @click="mobileFiltersOpen = false"><i class="pi pi-times" /></button>
      </div>
      <div class="rpro__toolbar-left">
        <IconField icon-position="left" class="rpro__search">
          <InputIcon class="pi pi-search" />
          <InputText
            v-model="search"
            :placeholder="props.endpoint === '/inbound-nfe/' ? 'Buscar por número, fornecedor, chave, CNPJ, produto...' : `Buscar em ${title.toLowerCase()}...`"
            @keyup.enter="onSearchSubmit"
            @input="onSearchInput"
          />
          <button
            v-if="search"
            class="rpro__search-clear"
            type="button"
            title="Limpar busca"
            @click="clearSearch"
          >
            <i class="pi pi-times" />
          </button>
        </IconField>
        <AppDateRange
          v-if="dateField"
          v-model="dateRange"
          class="rpro__daterange"
          :placeholder="dateField.label || 'Período'"
          :default-current-month="props.endpoint === '/inbound-nfe/' ? false : (dateField.defaultCurrentMonth ?? true)"
          @change="onDateRange"
        />
        <ResourceDirectFilters :fields="directFilterFields" :values="advancedFilters" @change="onDirectFilterChange" />
      </div>
      <div class="rpro__toolbar-right">
        <button v-if="advancedFilterFields.length" class="rpro-btn rpro-btn--ghost" type="button" @click="advancedFiltersVisible = true">
          <i class="pi pi-sliders-h" /> Mais filtros
        </button>
      </div>
      <div class="rpro__mobile-file-actions">
        <template v-if="props.endpoint === '/inbound-nfe/'">
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="exportInboundLoading" @click="exportInboundXml(false)">
            <i class="pi pi-file-export" /> Exportar Selecionadas
          </button>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="exportInboundLoading" @click="exportInboundXml(true)">
            <i class="pi pi-download" /> Exportar Tudo (XML)
          </button>
        </template>
        <template v-else>
          <button class="rpro-btn rpro-btn--ghost" type="button" @click="exportRows"><i class="pi pi-upload" /> Exportar</button>
          <button v-if="formEnabled" class="rpro-btn rpro-btn--ghost" type="button" @click="importVisible = true"><i class="pi pi-download" /> Importar</button>
        </template>
        <button
          v-for="headerAction in headerActions"
          :key="`mobile-${headerAction.key}`"
          class="rpro-btn rpro-btn--ghost"
          type="button"
          @click="runHeaderAction(headerAction)"
        >
          <i :class="headerAction.icon || 'pi pi-bolt'" /> {{ headerAction.label }}
        </button>
      </div>
      <div class="rpro__mobile-drawer-footer">
        <button class="rpro-btn rpro-btn--ghost" type="button" @click="clearMobileFilters">Limpar</button>
        <button class="rpro-btn rpro-btn--primary" type="button" @click="applyMobileFilters">Aplicar filtros</button>
      </div>
    </div>

    <div v-if="error" class="rpro__error"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <!-- ── Painel da tabela ───────────────────────────────────────────── -->
    <section class="rpro__panel">
      <!-- Filtros em pílula por Status de Mapeamento/Entrada (inbound-nfe) -->
      <div v-if="props.endpoint === '/inbound-nfe/'" class="rpro__inbound-filters">
        <button
          v-for="opt in INBOUND_FILTER_OPTIONS"
          :key="opt.value"
          type="button"
          class="rpro__inbound-filter-pill"
          :class="{
            'rpro__inbound-filter-pill--active': inboundStatusFilter === opt.value,
            [`rpro__inbound-filter-pill--${opt.tone}`]: opt.tone && inboundStatusFilter === opt.value
          }"
          @click="setInboundFilter(opt.value)"
        >
          <i :class="opt.icon" />
          <span>{{ opt.label }}</span>
          <span
            v-if="inboundStatusCounts[opt.value] != null"
            class="rpro__inbound-filter-count"
            :class="{ 'rpro__inbound-filter-count--active': inboundStatusFilter === opt.value }"
          >
            {{ inboundStatusCounts[opt.value] }}
          </span>
        </button>
      </div>

      <!-- Barra de ações em massa (aparece quando há seleção) -->
      <div v-if="selection.length && (bulkActions.length || props.endpoint === '/inbound-nfe/')" class="rpro__bulkbar">
        <span class="rpro__bulkbar-count">
          <i class="pi pi-check-circle" /> {{ selection.length }} {{ selection.length === 1 ? "selecionada" : "selecionadas" }}
          <button
            v-if="selection.length < total"
            class="rpro__bulkbar-all"
            type="button"
            :disabled="selectingAll"
            @click="selectAllMatching"
          >
            {{ selectingAll ? "Selecionando..." : `Selecionar todos os ${total}` }}
          </button>
        </span>
        <div class="rpro__bulkbar-actions">
          <button
            v-if="props.endpoint === '/inbound-nfe/'"
            class="rpro-btn rpro-btn--ghost rpro-btn--sm"
            type="button"
            :disabled="exportInboundLoading"
            @click="exportInboundXml(false)"
          >
            <i class="pi pi-file-export" /> Exportar XML ({{ selection.length }})
          </button>
          <button
            v-if="props.endpoint === '/inbound-nfe/'"
            class="rpro-btn rpro-btn--ghost rpro-btn--sm"
            type="button"
            :disabled="reconcileLoading"
            @click="reconcileSelectedSefaz"
          >
            <i :class="reconcileLoading ? 'pi pi-spin pi-spinner' : 'pi pi-shield'" /> Verificar Situação SEFAZ ({{ selection.length }})
          </button>
          <button
            v-if="props.endpoint === '/inbound-nfe/'"
            class="rpro-btn rpro-btn--ghost rpro-btn--sm"
            type="button"
            :disabled="bulkIgnoreLoading"
            @click="openBulkIgnoreDialog"
          >
            <i :class="bulkIgnoreLoading ? 'pi pi-spin pi-spinner' : 'pi pi-eye-slash'" /> Ignorar Notas ({{ selection.length }})
          </button>
          <template v-for="bulkAction in bulkActions" :key="bulkAction.key">
            <InvoiceBulkResendButton
              v-if="bulkAction.type === 'invoice-bulk-resend'"
              :selection="selection"
              @completed="onInvoiceBulkCompleted"
            />
            <button v-else class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" @click="runBulkAction(bulkAction)">
              <i :class="bulkAction.icon || 'pi pi-bolt'" /> {{ bulkAction.label }}
            </button>
          </template>
          <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" @click="selection = []">Limpar</button>
        </div>
      </div>

      <DataTable
        v-model:selection="selection"
        :value="rows"
        data-key="id"
        class="rpro__table"
        :loading="loading"
        :row-hover="true"
        :scrollable="props.endpoint !== '/inbound-nfe/'"
        :scroll-height="props.endpoint !== '/inbound-nfe/' ? 'flex' : undefined"
        removable-sort
        :sort-field="sortField"
        :sort-order="sortOrder"
        @sort="onSort"
        @row-click="onRowClick"
        @dblclick="onTableDblClick"
      >
        <Column selection-mode="multiple" :header-style="{ width: '46px' }" :body-style="{ width: '46px' }" />

        <Column
          v-for="column in visibleColumns"
          :key="column.key"
          :field="column.key"
          :header="column.label"
          :sortable="column.sortable !== false"
          :body-style="columnBodyStyle(column)"
          :header-class="column.align === 'right' ? 'dt-col-right' : undefined"
        >
          <template #body="{ data }">
            <span v-if="column.type === 'badges'" class="rpro-badges">
              <span
                v-for="(item, index) in badgeValues(value(data, column))"
                :key="`${item}-${index}`"
                class="rpro-badge"
              >
                {{ item }}
              </span>
              <span v-if="!badgeValues(value(data, column)).length" class="rpro-muted">—</span>
            </span>
            <span v-else-if="column.type === 'kds'" class="rpro-kds">
              <span class="rpro-chip" :data-tone="statusTone(value(data, column), column.map)">{{ label(value(data, column), column.map) }}</span>
              <small>{{ kdsProgressLabel(value(data, column)) }}</small>
            </span>
            <span v-else-if="column.key === 'nsu'" class="rpro-nsu-cell">
              <code class="rpro__code-pill font-mono font-bold">
                {{ formatNsuDisplay(value(data, column)) }}
              </code>
              <button
                v-if="data.status === 'summary' && value(data, column)"
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--xs ml-1"
                title="Consultar XML Completo na SEFAZ (consNSU)"
                @click.stop="fetchSpecificNsuDirect(value(data, column))"
              >
                <i class="pi pi-bolt text-indigo-500" />
              </button>
            </span>
            <span v-else-if="props.endpoint === '/inbound-nfe/' && column.key === 'status'" class="rpro-nfe-status-cell">
              <span
                class="rpro-chip font-bold"
                :data-tone="(data.fiscal_status === 'CANCELLED' || data.status === 'cancelled') ? 'danger' : (data.status === 'received' ? 'success' : data.status === 'pending_receipt' ? 'info' : (data.manifestation_status === 'science_registered' && data.xml_status === 'full_xml_pending') ? 'info' : data.status === 'pending_mapping' ? 'warning' : 'neutral')"
                :title="(data.fiscal_status === 'CANCELLED' || data.status === 'cancelled') ? (data.cancellation_reason || 'Nota Fiscal Cancelada na SEFAZ') : (data.status === 'ignored' ? (data.ignored_reason || 'Nota Fiscal Ignorada (não gera movimentação de estoque)') : undefined)"
              >
                <i v-if="data.fiscal_status === 'CANCELLED' || data.status === 'cancelled'" class="pi pi-ban text-xs mr-1" />
                <i v-else-if="data.status === 'received'" class="pi pi-check-circle text-xs mr-1" />
                <i v-else-if="data.status === 'pending_receipt'" class="pi pi-box text-xs mr-1" />
                <i v-else-if="data.status === 'ignored'" class="pi pi-eye-slash text-xs mr-1" />
                <i v-else-if="data.manifestation_status === 'science_registered' && data.xml_status === 'full_xml_pending'" class="pi pi-spin pi-spinner text-xs mr-1" />
                <i v-else-if="data.status === 'pending_mapping'" class="pi pi-exclamation-triangle text-xs mr-1" />
                <i v-else class="pi pi-file text-xs mr-1" />
                {{ (data.fiscal_status === 'CANCELLED' || data.status === 'cancelled') ? 'CANCELADA' : (data.status === 'ignored' ? 'IGNORADA' : ((data.manifestation_status === 'science_registered' && data.xml_status === 'full_xml_pending') ? 'Aguardando XML (SEFAZ)' : (data.status === 'pending_mapping' ? 'Pendente de Vínculo' : data.status === 'pending_receipt' ? 'Pronta p/ Entrada' : data.status === 'received' ? 'Entrada Concluída' : data.status === 'summary' ? 'Resumo SEFAZ' : label(value(data, column), column.map)))) }}
              </span>
              <span v-if="data.fiscal_status !== 'CANCELLED' && data.status !== 'cancelled' && data.status === 'pending_mapping' && data.unmapped_items_count" class="rpro-nfe-pending-pill" title="Itens que ainda precisam ser associados ao cadastro interno">
                {{ data.unmapped_items_count }} item(ns) pendente(s)
              </span>
              <span v-if="data.fiscal_status !== 'CANCELLED' && data.status !== 'cancelled' && data.status !== 'ignored' && data.ignored_items_count" class="rpro-nfe-ignored-pill" title="Itens ignorados nesta nota (não darão entrada no estoque)">
                {{ data.ignored_items_count }} ignorado(s)
              </span>
              <template v-if="data.fiscal_status !== 'CANCELLED' && data.status !== 'cancelled'">
                <button
                  v-if="(data.status === 'summary' || data.xml_status === 'summary_only' || (!data.items_count && data.xml_status !== 'full_xml_available')) && data.manifestation_status !== 'science_registered' && data.manifestation_status !== 'confirmed'"
                  type="button"
                  class="rpro-btn rpro-btn--primary rpro-btn--xs ml-1"
                  title="Dar Ciência da Operação (210210) e baixar XML completo da SEFAZ"
                  @click.stop="openScienceConfirmDialog(data)"
                >
                  <i class="pi pi-bolt mr-1" /> Dar Ciência
                </button>
                <button
                  v-else-if="(data.manifestation_status === 'science_registered' || data.manifestation_status === 'confirmed') && data.xml_status !== 'full_xml_available'"
                  type="button"
                  class="rpro-btn rpro-btn--ghost rpro-btn--xs ml-1"
                  title="Reconsultar XML completo na SEFAZ (consChNFe)"
                  @click.stop="retryFetchFullXmlDirect(data)"
                >
                  <i class="pi pi-cloud-download text-indigo-400 mr-1" /> Baixar XML
                </button>
              </template>
            </span>
            <span v-else-if="column.key === 'stock_status'">
              <span
                v-if="data.minimum_stock != null && Number(data.minimum_stock) > 0"
                class="rpro-chip font-bold"
                :data-tone="data.is_below_minimum ? 'danger' : 'success'"
              >
                <i :class="data.is_below_minimum ? 'pi pi-exclamation-triangle mr-1' : 'pi pi-check mr-1'" />
                {{ data.is_below_minimum ? 'Abaixo do Mínimo' : 'Normal' }}
              </span>
              <span v-else class="rpro-muted text-xs">Sem limite mín.</span>
            </span>
            <span v-else-if="props.endpoint === '/assets/reusables/' && column.key === 'current_stock_display'" class="rpro-num font-bold" :class="{ 'text-rose-400': data.is_below_minimum, 'text-emerald-400': !data.is_below_minimum }">
              {{ value(data, column) }}
            </span>
            <span v-else-if="column.type === 'status'" class="rpro-chip" :data-tone="statusTone(value(data, column), column.map)">{{ label(value(data, column), column.map) }}</span>
            <span v-else-if="column.type === 'money'" class="rpro-num">{{ money(value(data, column)) }}</span>
            <span v-else-if="column.type === 'date'" class="rpro-muted">{{ dateTime(value(data, column)) }}</span>
            <span v-else-if="column.type === 'boolean'" class="rpro-chip" :data-tone="value(data, column) ? 'success' : 'danger'">{{ value(data, column) ? "Ativo" : "Inativo" }}</span>
            <img
              v-else-if="column.type === 'image' && value(data, column)"
              :src="value(data, column)"
              :alt="rowLabel(data)"
              class="rpro-thumb"
              loading="lazy"
            />
            <span v-else-if="column.type === 'image'" class="rpro-muted">—</span>
            <span v-else-if="column.type === 'bytes'" class="rpro-num">{{ bytes(value(data, column)) }}</span>
            <span v-else class="rpro-cell">{{ label(value(data, column), column.map) }}</span>
          </template>
        </Column>

        <Column :header-style="{ width: props.endpoint === '/assets/reusables/' ? '112px' : '64px' }" :body-style="{ width: props.endpoint === '/assets/reusables/' ? '112px' : '64px', textAlign: 'right' }" :sortable="false">
          <template #body="{ data }">
            <div class="rpro__row-actions">
              <template v-if="props.endpoint === '/assets/reusables/'">
                <button
                  class="rpro__row-btn rpro__row-btn--danger"
                  type="button"
                  title="Registrar Quebra / Baixa de Vasilhame"
                  @click.stop="openReusableLossDialog(data)"
                >
                  <i class="pi pi-minus-circle" />
                </button>
                <button
                  class="rpro__row-btn rpro__row-btn--info"
                  type="button"
                  title="Histórico de Movimentações"
                  @click.stop="openReusableHistoryDialog(data)"
                >
                  <i class="pi pi-history" />
                </button>
              </template>
              <button class="rpro__row-btn" type="button" aria-label="Ações" aria-haspopup="true" @click.stop="openRowMenu($event, data)">
                <i class="pi pi-ellipsis-h" />
              </button>
            </div>
          </template>
        </Column>

        <template #empty>
          <div class="rpro__empty">
            <i class="pi pi-inbox" />
            <strong>Nenhum registro encontrado</strong>
            <span>Ajuste a busca, o período ou os cartões acima.</span>
          </div>
        </template>
      </DataTable>

      <Menu ref="rowMenu" :model="rowMenuItems" :popup="true" />

      <Dialog v-model:visible="codesVisible" modal :header="`Códigos ${codesTitle}`" :style="{ width: '360px' }">
        <div v-if="codesLoading" class="rpro__codes rpro__codes--loading">
          <i class="pi pi-spin pi-spinner" /> Gerando códigos…
        </div>
        <div v-else-if="codesData" class="rpro__codes">
          <div class="rpro__codes-value">{{ codesData.code }}</div>
          <img v-if="codesData.barcode_uri" :src="codesData.barcode_uri" alt="Código de barras" class="rpro__codes-barcode" />
          <img v-if="codesData.qr_uri" :src="codesData.qr_uri" alt="QR Code" width="160" height="160" />
          <div v-if="!codesData.barcode_uri && !codesData.qr_uri" class="rpro-muted">Sem código definido.</div>
          <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" @click="printCodes">
            <i class="pi pi-print" /> Imprimir
          </button>
        </div>
      </Dialog>

      <Dialog v-model:visible="versionsVisible" modal header="Histórico de versões" :style="{ width: '520px' }">
        <div v-if="versionsLoading" class="rpro__codes rpro__codes--loading">
          <i class="pi pi-spin pi-spinner" /> Carregando versões…
        </div>
        <div v-else-if="!versionsData.length" class="rpro-muted">Nenhuma versão anterior registrada ainda.</div>
        <ul v-else class="rpro__versions">
          <li v-for="version in versionsData" :key="version.id" class="rpro__versions-row">
            <div class="rpro__versions-info">
              <strong>Versão v{{ version.number }}</strong>
              <span>{{ version.label || (version.origin === "publish" ? "Publicação anterior" : version.origin === "restore" ? "Antes de restaurar" : "Manual") }}</span>
              <small>{{ formatDateTime(version.created_at) }}{{ version.created_by_name ? ` · ${version.created_by_name}` : "" }}</small>
            </div>
            <div class="rpro__versions-actions">
              <button
                class="rpro-btn rpro-btn--ghost rpro-btn--sm"
                type="button"
                :disabled="restoringVersionId === version.id"
                @click="restoreVersion(version)"
              >
                Restaurar no rascunho
              </button>
              <button
                v-if="versionsRowAction?.allowPublishOnRestore"
                class="rpro-btn rpro-btn--primary rpro-btn--sm"
                type="button"
                :disabled="restoringVersionId === version.id"
                @click="restoreVersion(version, { publish: true })"
              >
                Restaurar e publicar
              </button>
            </div>
          </li>
        </ul>
      </Dialog>

      <Dialog v-model:visible="resolvedVisible" modal :header="`Itens de ${resolvedTitle}`" :style="{ width: '480px' }">
        <div v-if="resolvedLoading" class="rpro__codes rpro__codes--loading">
          <i class="pi pi-spin pi-spinner" /> Resolvendo o menu…
        </div>
        <template v-else-if="resolvedData">
          <p class="rpro-muted">
            {{ resolvedData.items.length }} {{ resolvedData.items.length === 1 ? "item" : "itens" }}
            — é exatamente isto que o site vai desenhar.
          </p>
          <ul v-if="resolvedData.items.length" class="rpro__versions">
            <li v-for="(item, index) in resolvedData.items" :key="item.id || index" class="rpro__versions-row">
              <div class="rpro__versions-info">
                <strong>{{ item.title }}</strong>
                <small>{{ item.type }}{{ item.url ? ` · ${item.url}` : "" }}</small>
                <small v-if="item.children?.length">{{ item.children.length }} subitem(ns)</small>
              </div>
              <div v-if="item.price" class="rpro-num">{{ money(item.price) }}</div>
            </li>
          </ul>
          <p v-else class="rpro-muted">
            Nenhum item. Menus automáticos ficam vazios enquanto não houver dado
            de origem (venda, promoção ou categoria).
          </p>
        </template>
      </Dialog>

      <Dialog v-model:visible="templateVisible" modal header="Aplicar modelo pronto" :style="{ width: '440px' }">
        <p class="rpro-muted">Substitui o rascunho atual pelo conteúdo do modelo escolhido. O que já está publicado só muda quando você publicar de novo.</p>
        <Dropdown
          v-model="templateSelected"
          :options="templateOptions"
          option-label="label"
          option-value="value"
          placeholder="Selecione um modelo"
          :loading="templateLoading"
          class="rpro__bulk-field"
          fluid
        />
        <p v-if="templateSelectedDescription" class="rpro-muted">{{ templateSelectedDescription }}</p>
        <div class="rpro__dialog-actions">
          <button class="rpro-btn rpro-btn--ghost" type="button" @click="templateVisible = false">Cancelar</button>
          <button
            class="rpro-btn rpro-btn--primary"
            type="button"
            :disabled="!templateSelected || applyingTemplate"
            @click="confirmApplyTemplate"
          >
            {{ applyingTemplate ? "Aplicando…" : "Aplicar modelo" }}
          </button>
        </div>
      </Dialog>

      <Dialog v-model:visible="bulkVisible" modal :header="bulkType === 'commands' ? 'Criar comandas em lote' : 'Criar mesas em lote'" :style="{ width: '420px' }">
        <div class="rpro__bulk">
          <label class="rpro__bulk-field">
            <span>Restaurante</span>
            <Dropdown
              v-model="bulkForm.restaurant_id"
              :options="bulkRestaurants"
              option-label="trade_name"
              option-value="id"
              placeholder="Selecione o restaurante"
              :loading="bulkRestaurantsLoading"
              filter
              @change="onBulkRestaurantChange"
            />
          </label>
          <label v-if="bulkType === 'tables'" class="rpro__bulk-field">
            <span>Setor</span>
            <Dropdown
              v-model="bulkForm.sector_id"
              :options="bulkSectors"
              option-label="name"
              option-value="id"
              :placeholder="bulkForm.restaurant_id ? 'Selecione o setor' : 'Selecione primeiro o restaurante'"
              :loading="bulkSectorsLoading"
              :disabled="!bulkForm.restaurant_id || bulkSectorsLoading"
              filter
            />
          </label>
          <div class="rpro__bulk-row">
            <label class="rpro__bulk-field">
              <span>Número inicial</span>
              <InputText v-model.number="bulkForm.from_number" type="number" min="1" placeholder="auto (próximo)" />
            </label>
            <label class="rpro__bulk-field">
              <span>Número final</span>
              <InputText v-model.number="bulkForm.to_number" type="number" min="1" placeholder="ex.: 200" />
            </label>
          </div>
          <p class="rpro-muted rpro__bulk-hint">
            Deixe o número inicial vazio para começar do próximo disponível. Números já existentes são pulados.
          </p>
        </div>
        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="bulkSubmitting" @click="bulkVisible = false">
            Cancelar
          </button>
          <button
            class="rpro-btn rpro-btn--primary"
            type="button"
            :disabled="bulkSubmitting || bulkRestaurantsLoading || bulkSectorsLoading"
            @click="submitBulk"
          >
            <i :class="bulkSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-check'" /> Criar
          </button>
        </template>
      </Dialog>

      <Dialog v-model:visible="labelsVisible" modal header="Imprimir etiquetas" :style="{ width: '380px' }">
        <div class="rpro__labels">
          <p class="rpro-muted">{{ selection.length }} {{ selection.length === 1 ? "item selecionado" : "itens selecionados" }}.</p>

          <div class="rpro__labels-group">
            <span class="rpro__labels-label">Tipo de código</span>
            <div class="rpro__labels-kinds">
              <button class="rpro-btn" :class="labelKind === 'qr' ? 'rpro-btn--primary' : 'rpro-btn--ghost'" type="button" @click="labelKind = 'qr'">
                <i class="pi pi-qrcode" /> QR Code
              </button>
              <button class="rpro-btn" :class="labelKind === 'barcode' ? 'rpro-btn--primary' : 'rpro-btn--ghost'" type="button" @click="labelKind = 'barcode'">
                <i class="pi pi-align-justify" /> Código de barras
              </button>
            </div>
          </div>

          <div class="rpro__labels-group">
            <span class="rpro__labels-label">Disposição</span>
            <div class="rpro__labels-kinds">
              <button class="rpro-btn" :class="labelLayout === 'sheet' ? 'rpro-btn--primary' : 'rpro-btn--ghost'" type="button" @click="labelLayout = 'sheet'">
                <i class="pi pi-th-large" /> Vários por folha
              </button>
              <button class="rpro-btn" :class="labelLayout === 'single' ? 'rpro-btn--primary' : 'rpro-btn--ghost'" type="button" @click="labelLayout = 'single'">
                <i class="pi pi-file" /> Um por página
              </button>
            </div>
          </div>

          <label class="rpro__labels-check">
            <input v-model="labelCutlines" type="checkbox" />
            <span>Linhas de corte (pontilhado)</span>
          </label>
        </div>
        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="labelsLoading" @click="labelsVisible = false">
            Cancelar
          </button>
          <button class="rpro-btn rpro-btn--primary" type="button" :disabled="labelsLoading" @click="printLabels">
            <i :class="labelsLoading ? 'pi pi-spin pi-spinner' : 'pi pi-print'" /> Imprimir
          </button>
        </template>
      </Dialog>

      <!-- Modal: Alterar Status Operacional de Ativos em Lote -->
      <Dialog v-model:visible="assetBulkStatusVisible" modal header="Alterar Status Operacional em Lote" :style="{ width: '440px' }">
        <div class="rpro__labels">
          <p class="rpro-muted">
            <i class="pi pi-info-circle" />
            {{ selection.length }} {{ selection.length === 1 ? "ativo selecionado" : "ativos selecionados" }}.
          </p>

          <div class="rpro__labels-group">
            <span class="rpro__labels-label">Novo status operacional</span>
            <Dropdown
              v-model="assetBulkStatusTarget"
              :options="ASSET_STATUS_OPTIONS"
              option-label="label"
              option-value="value"
              placeholder="Selecione o status"
              class="w-full"
            />
          </div>
        </div>
        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="assetBulkStatusLoading" @click="assetBulkStatusVisible = false">
            Cancelar
          </button>
          <button class="rpro-btn rpro-btn--primary" type="button" :disabled="assetBulkStatusLoading" @click="submitAssetBulkStatus">
            <i :class="assetBulkStatusLoading ? 'pi pi-spin pi-spinner' : 'pi pi-check'" />
            {{ assetBulkStatusLoading ? "Salvando..." : "Salvar Status em Lote" }}
          </button>
        </template>
      </Dialog>

      <!-- Modal: Mover Local de Estoque de Ativos em Lote -->
      <Dialog v-model:visible="assetBulkLocationVisible" modal header="Mover Local de Estoque em Lote" :style="{ width: '480px' }">
        <div class="rpro__labels">
          <p class="rpro-muted">
            <i class="pi pi-info-circle" />
            {{ selection.length }} {{ selection.length === 1 ? "ativo selecionado" : "ativos selecionados" }}.
          </p>

          <div class="rpro__labels-group">
            <span class="rpro__labels-label">Local de estoque de destino</span>
            <Dropdown
              v-model="assetBulkLocationTarget"
              :options="assetStockLocations"
              option-label="name"
              option-value="id"
              :loading="assetBulkLocationsLoading"
              placeholder="Selecione o local de estoque"
              class="w-full"
            />
          </div>

          <div class="rpro__labels-group">
            <span class="rpro__labels-label">Motivo / Justificativa da movimentação</span>
            <InputText
              v-model="assetBulkLocationReason"
              placeholder="Ex: Transferência para o salão, armário, etc."
              class="w-full"
            />
          </div>
        </div>
        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="assetBulkLocationLoading" @click="assetBulkLocationVisible = false">
            Cancelar
          </button>
          <button class="rpro-btn rpro-btn--primary" type="button" :disabled="assetBulkLocationLoading || !assetBulkLocationTarget" @click="submitAssetBulkLocation">
            <i :class="assetBulkLocationLoading ? 'pi pi-spin pi-spinner' : 'pi pi-map-marker'" />
            {{ assetBulkLocationLoading ? "Movendo..." : "Mover Ativos em Lote" }}
          </button>
        </template>
      </Dialog>

      <!-- Modal: Registrar Quebra / Baixa de Vasilhame & Reutilizável -->
      <Dialog
        v-model:visible="reusableLossVisible"
        modal
        :header="`Registrar Baixa: ${reusableLossTarget?.name || ''}`"
        :style="{ width: 'min(500px, 94vw)' }"
      >
        <div class="rpro__reusable-dialog-body">
          <div class="rpro__reusable-info-card">
            <div class="rpro__reusable-info-item">
              <span>Saldo Atual</span>
              <strong>{{ reusableLossTarget?.current_stock_display || '0 UN' }}</strong>
            </div>
            <div class="rpro__reusable-info-item" style="text-align: right;">
              <span>Local Atual</span>
              <strong>{{ reusableLossTarget?.location_name || 'Geral' }}</strong>
            </div>
          </div>

          <div class="rpro__reusable-field">
            <label>Tipo de Baixa / Ocorrência *</label>
            <Dropdown
              v-model="reusableLossForm.movement_type"
              :options="reusableLossTypes"
              option-label="label"
              option-value="value"
              class="w-full"
            />
          </div>

          <div class="rpro__reusable-field">
            <label>Quantidade de Baixa ({{ reusableLossTarget?.stock_unit || 'UN' }}) *</label>
            <InputNumber
              v-model="reusableLossForm.quantity"
              :min="1"
              :max="reusableLossTarget?.current_stock ? Number(reusableLossTarget.current_stock) : undefined"
              placeholder="Ex.: 1"
              class="w-full"
            />
            <small>Informe a quantidade que quebrou, estragou ou foi extraviada.</small>
          </div>

          <div class="rpro__reusable-field">
            <label>Motivo / Justificativa detalhada</label>
            <Textarea
              v-model="reusableLossForm.notes"
              rows="3"
              placeholder="Ex.: Vasilhame trincado na entrega; Quebrou durante lavagem; Garrafa arranhada e gasta..."
              class="w-full"
            />
          </div>
        </div>

        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="reusableLossLoading" @click="reusableLossVisible = false">
            Cancelar
          </button>
          <button
            class="rpro-btn rpro-btn--primary"
            style="background: #e11d48; border-color: #e11d48;"
            type="button"
            :disabled="reusableLossLoading || !reusableLossForm.quantity || reusableLossForm.quantity <= 0"
            @click="submitReusableLoss"
          >
            <i :class="reusableLossLoading ? 'pi pi-spin pi-spinner' : 'pi pi-check'" />
            {{ reusableLossLoading ? "Registrando..." : "Confirmar Baixa" }}
          </button>
        </template>
      </Dialog>

      <!-- Modal: Histórico de Movimentações de Vasilhames & Reutilizáveis -->
      <Dialog
        v-model:visible="reusableHistoryVisible"
        modal
        :header="`Histórico de Movimentações: ${reusableHistoryTarget?.name || ''}`"
        :style="{ width: 'min(860px, 95vw)' }"
      >
        <div>
          <div class="rpro__reusable-history-summary">
            <div class="rpro__reusable-history-card">
              <span>Saldo Atual</span>
              <strong style="color: #10b981;">{{ reusableHistoryTarget?.current_stock_display || '0 UN' }}</strong>
            </div>
            <div class="rpro__reusable-history-card">
              <span>Total Entradas (Compras/NF-e)</span>
              <strong style="color: #3b82f6;">+{{ reusableHistoryTarget?.total_entries || 0 }} {{ reusableHistoryTarget?.stock_unit || 'UN' }}</strong>
            </div>
            <div class="rpro__reusable-history-card">
              <span>Total Perdas / Quebras</span>
              <strong style="color: #f43f5e;">-{{ reusableHistoryTarget?.total_losses || 0 }} {{ reusableHistoryTarget?.stock_unit || 'UN' }}</strong>
            </div>
          </div>

          <div v-if="reusableHistoryLoading" style="padding: 32px; text-align: center; color: var(--text-muted);">
            <i class="pi pi-spin pi-spinner" style="font-size: 24px;" />
            <p style="margin-top: 8px; font-size: 13px;">Carregando histórico...</p>
          </div>
          <div v-else-if="!reusableHistoryMovements.length" style="padding: 32px; text-align: center; color: var(--text-muted);">
            <i class="pi pi-inbox" style="font-size: 24px;" />
            <p style="margin-top: 8px; font-size: 13px;">Nenhuma movimentação registrada para este item.</p>
          </div>
          <div v-else class="rpro__reusable-table-wrap">
            <table class="rpro__reusable-table">
              <thead>
                <tr>
                  <th>Data / Hora</th>
                  <th>Operação</th>
                  <th style="text-align: right;">Qtd.</th>
                  <th>Local</th>
                  <th>Responsável / NF-e</th>
                  <th>Motivo / Justificativa</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in reusableHistoryMovements" :key="m.id">
                  <td style="white-space: nowrap;">{{ dateTime(m.created_at) }}</td>
                  <td>
                    <span
                      class="rpro-chip"
                      :data-tone="Number(m.quantity) > 0 ? 'success' : 'danger'"
                    >
                      {{ m.movement_type_display || m.movement_type }}
                    </span>
                  </td>
                  <td style="text-align: right; font-weight: bold; white-space: nowrap;" :style="{ color: Number(m.quantity) > 0 ? '#10b981' : '#f43f5e' }">
                    {{ Number(m.quantity) > 0 ? `+${m.quantity}` : m.quantity }} {{ m.stock_unit }}
                  </td>
                  <td>{{ m.location_name || '—' }}</td>
                  <td>
                    <div v-if="m.nfe_number" style="font-weight: 600; color: #60a5fa;">NF-e {{ m.nfe_number }}</div>
                    <div v-if="m.operator_name" style="font-size: 11px; color: var(--text-muted);">{{ m.operator_name }}</div>
                    <div v-if="!m.nfe_number && !m.operator_name">—</div>
                  </td>
                  <td :title="m.reason" style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ m.reason || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <template #footer>
          <button class="rpro-btn rpro-btn--ghost" type="button" @click="reusableHistoryVisible = false">
            Fechar
          </button>
        </template>
      </Dialog>

      <!-- Paginação enxuta (Anterior · Página X de Y · Próxima + Seletor de 10, 20 ou 50) -->
      <div class="rpro__pager">
        <div class="rpro__pager-nav">
          <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" :disabled="page <= 1 || loading" @click="goToPage(page - 1)">
            Anterior
          </button>
          <span class="rpro__pager-info">Página {{ page }} de {{ totalPages }} · {{ total }} {{ total === 1 ? "item" : "itens" }}</span>
          <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" :disabled="page >= totalPages || loading" @click="goToPage(page + 1)">
            Próxima
          </button>
        </div>

        <div class="rpro__pager-size">
          <label for="rpro-page-size-select" class="rpro__pager-size-label">Exibir:</label>
          <select
            id="rpro-page-size-select"
            class="rpro__pager-size-select"
            :value="rowsPerPage"
            @change="setPageSize(Number($event.target.value))"
          >
            <option :value="10">10 por página</option>
            <option :value="20">20 por página</option>
            <option :value="50">50 por página</option>
          </select>
        </div>
      </div>
    </section>

    <ResourceAdvancedFiltersDialog v-model="advancedFiltersVisible" :fields="advancedFilterFields" :values="advancedFilters" @change="setAdvancedFilter" @clear="clearAdvancedFilters" @apply="applyAdvancedFilters" />

    <Dialog v-model:visible="importVisible" modal :header="`Importar ${title}`" :style="{ width: 'min(560px, 94vw)' }">
      <div class="rpro__import">
        <p>Use CSV UTF-8. As colunas aceitas são: <strong>{{ importFieldLabels }}</strong>.</p>
        <input type="file" accept=".csv,text/csv" @change="onImportFile" />
        <small v-if="importFile">{{ importFile.name }}</small>
      </div>
      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="exchangeLoading" @click="importVisible = false">Cancelar</button>
        <button class="rpro-btn rpro-btn--primary" type="button" :disabled="!importFile || exchangeLoading" @click="importRows">
          <i :class="exchangeLoading ? 'pi pi-spin pi-spinner' : 'pi pi-download'" /> Importar
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Detalhes da NF-e de Entrada (Itens, Valores e Tributos) ── -->
    <Dialog
      v-model:visible="inboundDetailVisible"
      modal
      :header="inboundDetailData ? `NF-e #${inboundDetailData.number || 'S/N'} · Série ${inboundDetailData.series || '0'}` : 'Carregando NF-e...'"
      :style="{ width: 'min(980px, 96vw)' }"
      class="rpro__inbound-dialog"
    >
      <div v-if="inboundDetailLoading" class="rpro__inbound-loading">
        <i class="pi pi-spin pi-spinner text-3xl" />
        <span>Carregando dados da nota fiscal...</span>
      </div>

      <div v-else-if="inboundDetailData" class="rpro__inbound-body">
        <!-- Alerta de NF-e Cancelada -->
        <div
          v-if="inboundDetailData.fiscal_status === 'CANCELLED' || inboundDetailData.status === 'cancelled'"
          class="rpro__inbound-cancelled-banner"
        >
          <div class="rpro__inbound-cancelled-icon">
            <i class="pi pi-ban text-2xl" />
          </div>
          <div class="rpro__inbound-cancelled-info">
            <strong>NF-E CANCELADA NA SEFAZ</strong>
            <p>
              Esta nota fiscal foi cancelada pelo emitente. O recebimento físico e a movimentação de estoque estão bloqueados.
            </p>
            <div
              v-if="inboundDetailData.cancellation_protocol || inboundDetailData.cancelled_at || inboundDetailData.cancellation_reason"
              class="rpro__inbound-cancelled-meta"
            >
              <span v-if="inboundDetailData.cancelled_at">
                <strong>Data/Hora do Cancelamento:</strong> {{ formatDfeDate(inboundDetailData.cancelled_at) }}
              </span>
              <span v-if="inboundDetailData.cancellation_protocol">
                <strong>Protocolo:</strong> {{ inboundDetailData.cancellation_protocol }}
              </span>
              <span v-if="inboundDetailData.cancellation_reason">
                <strong>Justificativa:</strong> {{ inboundDetailData.cancellation_reason }}
              </span>
            </div>
          </div>
        </div>

        <!-- Alerta de NF-e Ignorada -->
        <div
          v-if="inboundDetailData.status === 'ignored'"
          class="rpro__inbound-ignored-banner"
        >
          <div class="rpro__inbound-ignored-icon">
            <i class="pi pi-eye-slash text-2xl" />
          </div>
          <div class="rpro__inbound-cancelled-info">
            <strong class="text-neutral-300">NOTA FISCAL IGNORADA</strong>
            <p>
              Esta nota fiscal foi marcada como ignorada. Ela não gera movimentação de estoque nem bloqueia os fluxos do sistema.
            </p>
            <div
              v-if="inboundDetailData.ignored_at || inboundDetailData.ignored_reason"
              class="rpro__inbound-cancelled-meta"
            >
              <span v-if="inboundDetailData.ignored_at">
                <strong>Ignorada em:</strong> {{ formatDfeDate(inboundDetailData.ignored_at) }}
              </span>
              <span v-if="inboundDetailData.ignored_reason">
                <strong>Motivo:</strong> {{ inboundDetailData.ignored_reason }}
              </span>
            </div>
          </div>
        </div>

        <!-- Cabeçalho / Sumário da NF-e -->
        <div class="rpro__inbound-summary">
          <div class="rpro__inbound-summary-grid">
            <div class="rpro__inbound-card">
              <span class="rpro__inbound-card-label">Fornecedor / Emitente</span>
              <strong class="rpro__inbound-card-val">{{ inboundDetailData.supplier_name || 'Não informado' }}</strong>
              <small class="rpro__inbound-card-sub">CNPJ: {{ inboundDetailData.supplier_cnpj || '-' }}</small>
            </div>

            <div class="rpro__inbound-card">
              <span class="rpro__inbound-card-label">Emissão & NSU</span>
              <strong class="rpro__inbound-card-val">{{ formatDfeDate(inboundDetailData.issue_date) }}</strong>
              <small class="rpro__inbound-card-sub">NSU: {{ inboundDetailData.nsu || '-' }}</small>
            </div>

            <div class="rpro__inbound-card rpro__inbound-card--highlight">
              <span class="rpro__inbound-card-label">Valor Total da NF-e</span>
              <strong class="rpro__inbound-card-val text-emerald-600 font-mono">{{ money(inboundDetailData.total_invoice) }}</strong>
              <small class="rpro__inbound-card-sub">Total produtos: {{ money(inboundDetailData.total_products) }}</small>
            </div>
          </div>

          <!-- Chave de Acesso -->
          <div class="rpro__inbound-key-box">
            <div class="rpro__inbound-key-info">
              <span class="rpro__inbound-key-label">Chave de Acesso:</span>
              <span class="rpro__inbound-key-val font-mono">{{ inboundDetailData.access_key }}</span>
            </div>
            <button
              class="rpro-btn rpro-btn--ghost rpro-btn--sm"
              type="button"
              @click="copyAccessKey(inboundDetailData.access_key)"
            >
              <i class="pi pi-copy" /> Copiar
            </button>
          </div>
        </div>

        <!-- Tabela de Produtos / Itens -->
        <div class="rpro__inbound-items-section">
          <div class="rpro__inbound-items-head flex justify-between items-center">
            <div class="flex items-center gap-2">
              <h3>Produtos da Nota ({{ (inboundDetailData.items || []).length }} itens)</h3>
              <span v-if="inboundDetailData.ignored_items_count" class="text-xs text-amber-400 font-normal">
                ({{ inboundDetailData.active_items_count }} ativos, {{ inboundDetailData.ignored_items_count }} ignorados)
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button
                v-if="inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled' && (inboundDetailData.status === 'summary' || inboundDetailData.xml_status === 'summary_only' || (!inboundDetailData.items?.length && inboundDetailData.xml_status !== 'full_xml_available')) && inboundDetailData.manifestation_status !== 'science_registered' && inboundDetailData.manifestation_status !== 'confirmed'"
                type="button"
                class="rpro-btn rpro-btn--primary rpro-btn--sm"
                title="Dar Ciência da Operação (210210) e baixar XML completo da SEFAZ"
                @click="openScienceConfirmDialog(inboundDetailData)"
              >
                <i class="pi pi-bolt mr-1" /> Dar Ciência
              </button>
              <button
                v-else-if="inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled' && (inboundDetailData.manifestation_status === 'science_registered' || inboundDetailData.manifestation_status === 'confirmed') && inboundDetailData.xml_status !== 'full_xml_available'"
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--sm"
                title="Reconsultar XML completo na SEFAZ (consChNFe)"
                @click="retryFetchFullXmlDirect(inboundDetailData)"
              >
                <i class="pi pi-cloud-download text-indigo-400 mr-1" /> Baixar XML
              </button>
              <button
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--sm"
                title="Consultar situação em tempo real na SEFAZ"
                :disabled="checkingSefazId === inboundDetailData.id"
                @click="checkSefazStatusDirect(inboundDetailData)"
              >
                <i :class="checkingSefazId === inboundDetailData.id ? 'pi pi-spin pi-spinner' : 'pi pi-shield'" />
                Verificar Situação SEFAZ
              </button>
              <button
                v-if="inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'received' && inboundDetailData.status !== 'cancelled' && inboundDetailData.status !== 'ignored'"
                type="button"
                class="rpro-btn rpro-btn--primary rpro-btn--sm"
                @click="openReceiveModalFromDetail"
              >
                <i class="pi pi-box" /> Dar Entrada no Estoque
              </button>
              <button
                v-if="inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'received' && inboundDetailData.status !== 'cancelled' && inboundDetailData.status !== 'ignored'"
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--sm text-amber-500 hover:text-amber-400"
                title="Ignorar esta nota inteira (não dará entrada e irá para a aba Ignoradas)"
                :disabled="inboundActionLoading"
                @click="openIgnoreInvoiceDialog(inboundDetailData)"
              >
                <i class="pi pi-eye-slash text-xs mr-1" /> Ignorar Nota
              </button>
              <button
                v-else-if="inboundDetailData.status === 'ignored'"
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--sm text-emerald-400 hover:text-emerald-300"
                title="Reativar esta nota fiscal"
                :disabled="inboundActionLoading"
                @click="unignoreInvoice(inboundDetailData)"
              >
                <i class="pi pi-undo text-xs mr-1" /> Reativar Nota
              </button>
              <button
                v-if="inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled'"
                type="button"
                class="rpro-btn rpro-btn--ghost rpro-btn--sm text-red-500 hover:text-red-600"
                title="Marcar esta nota fiscal como cancelada manualmente no sistema"
                @click="openManualCancelDialog(inboundDetailData)"
              >
                <i class="pi pi-ban text-xs mr-1" /> Cancelar / Substituir
              </button>
              <div v-else-if="inboundDetailData.fiscal_status === 'CANCELLED' || inboundDetailData.status === 'cancelled'" class="rpro__inbound-cancelled-badge">
                <i class="pi pi-ban" /> Cancelada
              </div>
              <div v-else-if="inboundDetailData.status === 'received'" class="rpro__inbound-received-badge">
                <i class="pi pi-check-circle" /> Estocada
              </div>
              <div v-if="inboundDetailData.status === 'ignored'" class="rpro__inbound-ignored-badge">
                <i class="pi pi-eye-slash" /> Ignorada
              </div>
            </div>
          </div>

          <div class="rpro__inbound-table-wrapper">
            <table class="rpro__inbound-table">
              <thead>
                <tr>
                  <th style="width: 40px">#</th>
                  <th style="width: 110px">Cód. Forn.</th>
                  <th>Descrição do Produto</th>
                  <th style="width: 140px">EAN / GTIN</th>
                  <th style="width: 110px">NCM / CEST</th>
                  <th style="width: 60px">CFOP</th>
                  <th style="width: 90px; text-align: right">Qtd</th>
                  <th style="width: 110px; text-align: right">Unitário</th>
                  <th style="width: 110px; text-align: right">Total</th>
                  <th style="width: 260px">Vínculo com o Estoque</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="item in inboundDetailData.items || []" :key="item.id || item.item_number">
                  <tr class="rpro__inbound-row" :class="{ 'rpro__inbound-row--has-taxes': item.tax_data && Object.keys(item.tax_data).length, 'rpro__inbound-row--ignored': item.is_ignored }">
                    <td class="text-center font-bold text-muted">{{ item.item_number }}</td>
                    <td><code class="rpro__code-pill">{{ item.supplier_code || '-' }}</code></td>
                    <td>
                      <strong class="rpro__inbound-item-desc">{{ item.description }}</strong>
                      <small v-if="item.is_ignored && item.ignored_reason" class="text-xs text-amber-400/80 block mt-0.5">
                        Ignorado: {{ item.ignored_reason }}
                      </small>
                    </td>
                    <td><span class="font-mono text-xs">{{ item.ean || item.ean_trib || 'Sem GTIN' }}</span></td>
                    <td>
                      <span class="font-mono text-xs">{{ item.ncm || '-' }}</span>
                      <small v-if="item.cest" class="text-muted block text-xs">CEST: {{ item.cest }}</small>
                    </td>
                    <td><span class="font-mono text-xs">{{ item.cfop || '-' }}</span></td>
                    <td style="text-align: right">
                      <strong>{{ Number(item.commercial_quantity).toLocaleString('pt-BR') }}</strong>
                      <small class="text-muted ml-1">{{ item.commercial_unit }}</small>
                    </td>
                    <td style="text-align: right; font-family: var(--font-table)">{{ money(item.commercial_unit_value) }}</td>
                    <td style="text-align: right; font-weight: bold; font-family: var(--font-table)">{{ money(item.product_total) }}</td>
                    <td>
                      <!-- Item Ignorado -->
                      <div v-if="item.is_ignored" class="flex items-center justify-between gap-2">
                        <Tag severity="secondary" rounded value="Ignorado (Sem Estoque)" icon="pi pi-eye-slash" />
                        <button
                          v-if="inboundDetailData.status !== 'received' && inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled'"
                          type="button"
                          class="rpro-btn rpro-btn--ghost rpro-btn--xs text-emerald-400 hover:text-emerald-300"
                          title="Reativar este item para movimentar estoque"
                          :disabled="inboundActionLoading"
                          @click="unignoreItem(item)"
                        >
                          <i class="pi pi-undo mr-1" /> Reativar
                        </button>
                      </div>

                      <!-- Item Ativo Vinculado -->
                      <div v-else-if="item.product_name || item.ingredient_name" class="flex items-center justify-between gap-2">
                        <div>
                          <Tag
                            v-if="item.is_asset || item.product_item_type === 'EQUIPMENT' || item.product_item_type === 'FIXED_ASSET'"
                            severity="info"
                            rounded
                            :value="`🏢 Patrimônio: ${item.product_name}`"
                          />
                          <Tag
                            v-else
                            severity="success"
                            rounded
                            :value="item.product_name ? `Produto: ${item.product_name}` : `Ingrediente: ${item.ingredient_name}`"
                          />
                          <small v-if="item.product_brand" class="text-muted block text-xs mt-0.5">
                            Marca: {{ item.product_brand }} {{ item.product_model ? `(${item.product_model})` : '' }}
                          </small>
                          <small v-if="item.conversion_factor && Number(item.conversion_factor) !== 1" class="text-muted block text-xs mt-0.5 font-mono">
                            Fator: x{{ Number(item.conversion_factor) }}
                          </small>
                        </div>
                        <div class="flex items-center gap-1">
                          <button
                            v-if="inboundDetailData.status !== 'received' && inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled'"
                            type="button"
                            class="rpro-btn rpro-btn--ghost rpro-btn--xs"
                            title="Alterar vínculo"
                            @click="openMapModal(item)"
                          >
                            <i class="pi pi-pencil" />
                          </button>
                          <button
                            v-if="inboundDetailData.status !== 'received' && inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled'"
                            type="button"
                            class="rpro-btn rpro-btn--ghost rpro-btn--xs text-neutral-400 hover:text-amber-400"
                            title="Ignorar este item (não dará entrada no estoque)"
                            :disabled="inboundActionLoading"
                            @click="openIgnoreItemDialog(item)"
                          >
                            <i class="pi pi-eye-slash" />
                          </button>
                        </div>
                      </div>

                      <!-- Item Ativo Não Vinculado -->
                      <div v-else class="flex items-center gap-1">
                        <button
                          type="button"
                          class="rpro-btn rpro-btn--ghost rpro-btn--sm flex-1"
                          :disabled="inboundDetailData.status === 'received' || inboundDetailData.fiscal_status === 'CANCELLED' || inboundDetailData.status === 'cancelled'"
                          @click="openMapModal(item)"
                        >
                          <i class="pi pi-link" /> Vincular Produto
                        </button>
                        <button
                          v-if="inboundDetailData.status !== 'received' && inboundDetailData.fiscal_status !== 'CANCELLED' && inboundDetailData.status !== 'cancelled'"
                          type="button"
                          class="rpro-btn rpro-btn--ghost rpro-btn--sm text-neutral-400 hover:text-amber-400"
                          title="Ignorar este item (não dará entrada no estoque)"
                          :disabled="inboundActionLoading"
                          @click="openIgnoreItemDialog(item)"
                        >
                          <i class="pi pi-eye-slash" />
                        </button>
                      </div>
                    </td>
                  </tr>

                  <!-- Linha de impostos alinhada logo abaixo da linha com as colunas -->
                  <tr v-if="item.tax_data && Object.keys(item.tax_data).length" class="rpro__inbound-tax-subrow">
                    <td colspan="10" class="rpro__inbound-tax-subcell">
                      <div class="rpro__inbound-tax-line">
                        <span class="rpro__inbound-tax-label">
                          <i class="pi pi-receipt text-xs" /> Tributos:
                        </span>
                        <span v-if="item.tax_data.ICMS" class="rpro__inbound-tax-tag">
                          ICMS: {{ item.tax_data.ICMS.tipo || item.tax_data.ICMS.CST }} (R$ {{ item.tax_data.ICMS.vICMS || '0,00' }})
                        </span>
                        <span v-if="item.tax_data.PIS" class="rpro__inbound-tax-tag">
                          PIS: {{ item.tax_data.PIS.tipo }}
                        </span>
                        <span v-if="item.tax_data.COFINS" class="rpro__inbound-tax-tag">
                          COFINS: {{ item.tax_data.COFINS.tipo }}
                        </span>
                      </div>
                    </td>
                  </tr>
                </template>
                <tr v-if="!(inboundDetailData.items || []).length">
                  <td colspan="10" class="text-center py-6 text-muted">
                    Nenhum item localizado no documento XML (resumo de NF-e ou evento).
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" @click="inboundDetailVisible = false">
          Fechar
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Marcar NF-e como Cancelada / Substituída ── -->
    <Dialog
      v-model:visible="manualCancelDialogVisible"
      modal
      header="Marcar NF-e como Cancelada / Substituída"
      :style="{ width: 'min(480px, 94vw)' }"
    >
      <div v-if="manualCancelInvoice" class="flex flex-col gap-3 py-1">
        <p class="text-sm text-gray-400">
          Você está prestes a invalidar a NF-e <strong>#{{ manualCancelInvoice.number }}</strong> ({{ manualCancelInvoice.supplier_name }}).
          O estoque e recebimento físico serão bloqueados.
        </p>

        <div class="p-3 bg-red-950/20 border border-red-500/30 rounded text-xs text-red-300">
          <i class="pi pi-info-circle mr-1" /> Use esta ação quando o fornecedor tiver substituído o pedido por outra nota fiscal ou cancelado a entrega fora do prazo legal da SEFAZ.
        </div>

        <div class="flex flex-col gap-1 mt-1">
          <label class="text-xs font-semibold text-gray-300">Justificativa do Cancelamento *</label>
          <textarea
            v-model="manualCancelReason"
            rows="3"
            class="rpro__manual-cancel-textarea"
            placeholder="Ex: Nota substituída pela NF-e nº 282063; entrega cancelada pelo fornecedor."
          />
        </div>
      </div>

      <template #footer>
        <button
          class="rpro-btn rpro-btn--ghost"
          type="button"
          :disabled="manualCancelLoading"
          @click="manualCancelDialogVisible = false"
        >
          Voltar
        </button>
        <button
          class="rpro-btn rpro-btn--primary bg-red-600 border-red-600 hover:bg-red-700"
          type="button"
          :disabled="manualCancelLoading"
          @click="confirmManualCancel"
        >
          <i :class="manualCancelLoading ? 'pi pi-spin pi-spinner' : 'pi pi-check'" />
          Confirmar Cancelamento
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Ignorar NF-e Inteira ── -->
    <Dialog
      v-model:visible="ignoreInvoiceDialogVisible"
      modal
      header="Ignorar Nota Fiscal"
      :style="{ width: 'min(480px, 94vw)' }"
    >
      <div v-if="ignoreInvoiceTarget" class="flex flex-col gap-3 py-1">
        <p class="text-sm text-gray-300">
          Deseja ignorar a NF-e <strong>#{{ ignoreInvoiceTarget.number }}</strong> ({{ ignoreInvoiceTarget.supplier_name }})?
        </p>
        <div class="p-3 bg-neutral-900/60 border border-neutral-700/60 rounded text-xs text-neutral-300">
          <i class="pi pi-info-circle mr-1 text-amber-400" />
          A nota será movida para a aba <strong>Ignoradas</strong> e não dará entrada em nenhum item no estoque. Você poderá reativá-la a qualquer momento.
        </div>
        <div class="flex flex-col gap-1 mt-1">
          <label class="text-xs font-semibold text-gray-300">Motivo (opcional)</label>
          <textarea
            v-model="ignoreInvoiceReason"
            rows="3"
            class="rpro__manual-cancel-textarea"
            placeholder="Ex: Mercadoria devolvida, bonificação ou sem controle de estoque."
          />
        </div>
      </div>

      <template #footer>
        <button
          class="rpro-btn rpro-btn--ghost"
          type="button"
          :disabled="ignoreInvoiceLoading"
          @click="ignoreInvoiceDialogVisible = false"
        >
          Voltar
        </button>
        <button
          class="rpro-btn rpro-btn--primary bg-amber-600 border-amber-600 hover:bg-amber-700"
          type="button"
          :disabled="ignoreInvoiceLoading"
          @click="confirmIgnoreInvoice"
        >
          <i :class="ignoreInvoiceLoading ? 'pi pi-spin pi-spinner' : 'pi pi-eye-slash'" />
          Confirmar e Ignorar
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Ignorar Item da NF-e ── -->
    <Dialog
      v-model:visible="ignoreItemDialogVisible"
      modal
      header="Ignorar Item da Nota Fiscal"
      :style="{ width: 'min(480px, 94vw)' }"
    >
      <div v-if="ignoreItemTarget" class="flex flex-col gap-3 py-1">
        <p class="text-sm text-gray-300">
          Deseja ignorar o item <strong>#{{ ignoreItemTarget.item_number }} - {{ ignoreItemTarget.description }}</strong>?
        </p>
        <div class="p-3 bg-neutral-900/60 border border-neutral-700/60 rounded text-xs text-neutral-300">
          <i class="pi pi-info-circle mr-1 text-amber-400" />
          Este item não será movimentado para o estoque e não exigirá vínculo de produto. Os demais itens da nota continuarão o processo normal de entrada.
        </div>
        <div class="flex flex-col gap-1 mt-1">
          <label class="text-xs font-semibold text-gray-300">Motivo (opcional)</label>
          <textarea
            v-model="ignoreItemReason"
            rows="3"
            class="rpro__manual-cancel-textarea"
            placeholder="Ex: Item de uso e consumo imediato, brinde ou serviço."
          />
        </div>
      </div>

      <template #footer>
        <button
          class="rpro-btn rpro-btn--ghost"
          type="button"
          :disabled="ignoreItemLoading"
          @click="ignoreItemDialogVisible = false"
        >
          Voltar
        </button>
        <button
          class="rpro-btn rpro-btn--primary bg-amber-600 border-amber-600 hover:bg-amber-700"
          type="button"
          :disabled="ignoreItemLoading"
          @click="confirmIgnoreItem"
        >
          <i :class="ignoreItemLoading ? 'pi pi-spin pi-spinner' : 'pi pi-eye-slash'" />
          Confirmar e Ignorar Item
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Ignorar Notas em Lote ── -->
    <Dialog
      v-model:visible="bulkIgnoreDialogVisible"
      modal
      header="Ignorar Notas Selecionadas"
      :style="{ width: 'min(480px, 94vw)' }"
    >
      <div class="flex flex-col gap-3 py-1">
        <p class="text-sm text-gray-300">
          Você selecionou <strong>{{ selection.length }}</strong> {{ selection.length === 1 ? 'nota fiscal' : 'notas fiscais' }} para ignorar.
        </p>
        <div class="p-3 bg-neutral-900/60 border border-neutral-700/60 rounded text-xs text-neutral-300">
          <i class="pi pi-info-circle mr-1 text-amber-400" />
          Todas as notas selecionadas serão marcadas como ignoradas e movidas para a aba <strong>Ignoradas</strong>.
        </div>
        <div class="flex flex-col gap-1 mt-1">
          <label class="text-xs font-semibold text-gray-300">Motivo (opcional)</label>
          <textarea
            v-model="bulkIgnoreReason"
            rows="3"
            class="rpro__manual-cancel-textarea"
            placeholder="Ex: Notas fiscais ignoradas em lote pelo usuário."
          />
        </div>
      </div>

      <template #footer>
        <button
          class="rpro-btn rpro-btn--ghost"
          type="button"
          :disabled="bulkIgnoreLoading"
          @click="bulkIgnoreDialogVisible = false"
        >
          Voltar
        </button>
        <button
          class="rpro-btn rpro-btn--primary bg-amber-600 border-amber-600 hover:bg-amber-700"
          type="button"
          :disabled="bulkIgnoreLoading"
          @click="confirmBulkIgnore"
        >
          <i :class="bulkIgnoreLoading ? 'pi pi-spin pi-spinner' : 'pi pi-eye-slash'" />
          Ignorar {{ selection.length }} {{ selection.length === 1 ? 'Nota' : 'Notas' }}
        </button>
      </template>
    </Dialog>

    <!-- ── Modal de Mapeamento / Vínculo de Item (DE/PARA) ── -->
    <Dialog
      v-model:visible="mapItemDialogVisible"
      modal
      header="Vincular Item da NF-e ao Estoque"
      :style="{ width: 'min(680px, 96vw)' }"
      class="inbound-map-dialog"
    >
      <div v-if="mappingItem" class="inbound-map">
        <!-- Resumo do Item Fiscal da NF-e -->
        <div class="inbound-map__summary">
          <div class="inbound-map__summary-top">
            <span class="inbound-map__summary-label">Item na Nota Fiscal</span>
            <span class="inbound-map__summary-price">{{ money(mappingItem.product_total) }}</span>
          </div>
          <strong class="inbound-map__summary-title">{{ mappingItem.description }}</strong>
          <div class="inbound-map__summary-meta">
            <span>Cód. Forn: <code>{{ mappingItem.supplier_code || '-' }}</code></span>
            <span>EAN: <code>{{ mappingItem.ean || 'Sem GTIN' }}</code></span>
            <span>NCM: <code>{{ mappingItem.ncm || '-' }}</code></span>
            <span>Comprado: <strong>{{ Number(mappingItem.commercial_quantity) }} {{ mappingItem.commercial_unit }}</strong></span>
            <span>Unitário: <strong>{{ money(mappingItem.commercial_unit_value) }}</strong></span>
          </div>
        </div>

        <!-- Seletor de Modo: Buscar Existente vs Criar Novo -->
        <!-- Seletor de Modo: Buscar Existente vs Criar Produto vs Cadastrar em Patrimônios & Ativos -->
        <div class="inbound-map__tabs">
          <button
            type="button"
            class="inbound-map__tab-btn"
            :class="{ 'inbound-map__tab-btn--active': mappingMode === 'select' }"
            @click="mappingMode = 'select'"
          >
            <i class="pi pi-search" /> Vincular a Existente
          </button>
          <button
            type="button"
            class="inbound-map__tab-btn"
            :class="{ 'inbound-map__tab-btn--active': mappingMode === 'create' }"
            @click="switchToQuickCreate"
          >
            <i class="pi pi-box" /> Novo Produto / Insumo
          </button>
          <button
            type="button"
            class="inbound-map__tab-btn inbound-map__tab-btn--asset"
            :class="{ 'inbound-map__tab-btn--active': mappingMode === 'asset' }"
            @click="switchToQuickAsset"
          >
            <i class="pi pi-building" /> Cadastrar em Patrimônio & Ativos
          </button>
        </div>

        <!-- ── ABA 1: Buscar & Selecionar Item Existente ── -->
        <div v-if="mappingMode === 'select'">
          <!-- Filtro rápido por tipo de item -->
          <div class="inbound-map__filters">
            <button
              v-for="flt in mappingTypeFilters"
              :key="flt.value"
              type="button"
              class="inbound-map__filter-btn"
              :class="{ 'inbound-map__filter-btn--active': mappingTypeFilter === flt.value }"
              @click="mappingTypeFilter = flt.value"
            >
              {{ flt.label }}
            </button>
          </div>

          <!-- Campo de Autocomplete / Busca Instantânea -->
          <div class="inbound-map__search-box">
            <i class="pi pi-search inbound-map__search-icon" />
            <input
              v-model="mappingSearch"
              type="text"
              placeholder="Digite o nome, código interno ou GTIN para pesquisar..."
              class="inbound-map__search-input"
            />
            <button
              v-if="mappingSearch"
              type="button"
              class="inbound-map__search-clear"
              @click="mappingSearch = ''"
            >
              <i class="pi pi-times" />
            </button>
          </div>

          <!-- Lista de Itens Filtrados -->
          <div class="inbound-map__list">
            <div
              v-for="prod in filteredMappingProducts"
              :key="prod.id"
              class="inbound-map__list-item"
              :class="{ 'inbound-map__list-item--selected': selectedTargetProduct?.id === prod.id }"
              @click="selectTargetProduct(prod)"
            >
              <div class="inbound-map__item-left">
                <div class="inbound-map__item-head">
                  <strong class="inbound-map__item-name">{{ prod.name }}</strong>
                  <span class="inbound-map__tag" :class="`inbound-map__tag--${prod.item_type}`">
                    {{ getItemTypeLabel(prod.item_type) }}
                  </span>
                </div>
                <div class="inbound-map__item-meta">
                  <span>Cód: {{ prod.internal_code || '-' }}</span>
                  <span v-if="prod.category_name">Cat: {{ prod.category_name }}</span>
                  <span>Estoque em: <strong>{{ prod.stock_unit || 'UN' }}</strong></span>
                </div>
              </div>
              <div class="inbound-map__item-right">
                <i v-if="selectedTargetProduct?.id === prod.id" class="pi pi-check-circle text-brand text-lg" />
                <button
                  type="button"
                  class="rpro-btn rpro-btn--xs"
                  :class="selectedTargetProduct?.id === prod.id ? 'rpro-btn--primary' : 'rpro-btn--ghost'"
                >
                  {{ selectedTargetProduct?.id === prod.id ? 'Selecionado' : 'Selecionar' }}
                </button>
              </div>
            </div>

            <!-- Estado Vazio / Nenhum Encontrado -->
            <div v-if="!filteredMappingProducts.length" class="inbound-map__empty">
              <i class="pi pi-inbox text-2xl block mb-2" />
              <p class="mb-3">Nenhum item cadastrado encontrado com esse termo.</p>
              <button
                type="button"
                class="rpro-btn rpro-btn--primary rpro-btn--sm"
                @click="switchToQuickCreate"
              >
                <i class="pi pi-plus" /> Cadastrar "{{ mappingSearch || mappingItem.description }}" agora
              </button>
            </div>
          </div>
        </div>

        <div v-else-if="mappingMode === 'create'" class="inbound-map__quick-form">
          <!-- ── ABA 2: Criação Rápida de Produto / Insumo ── -->
          <div class="inbound-map__callout">
            <i class="pi pi-bolt text-brand" />
            <span>O item será cadastrado com os dados preenchidos abaixo e já ficará vinculado à nota fiscal.</span>
          </div>

          <!-- Nome do Item -->
          <div class="inbound-map__field">
            <label class="inbound-map__label">Nome do Produto / Insumo no Sistema *</label>
            <InputText v-model="quickCreateForm.name" class="inbound-map__input" placeholder="Ex: Cream Cheese Bisnaga Catupiry" />
          </div>

          <!-- Finalidade / Tipo de Item & Categoria -->
          <div class="inbound-map__grid-2">
            <div class="inbound-map__field">
              <label class="inbound-map__label">Finalidade / Tipo do Item *</label>
              <Dropdown
                v-model="quickCreateForm.item_type"
                :options="ITEM_TYPE_OPTIONS_ALL"
                option-label="label"
                option-value="value"
                class="inbound-map__dropdown"
                @change="onQuickCreateItemTypeChange"
              />
            </div>
            <div class="inbound-map__field">
              <div class="flex items-center justify-between mb-1">
                <label class="inbound-map__label mb-0">Categoria (Opcional)</label>
                <button
                  type="button"
                  class="text-xs text-brand hover:underline font-bold flex items-center gap-1 cursor-pointer bg-transparent border-0 p-0 text-emerald-400"
                  @click="openInlineCategoryModal"
                >
                  <i class="pi pi-plus text-xs" /> Nova Categoria
                </button>
              </div>
              <Dropdown
                v-model="quickCreateForm.category"
                :options="mappingCategories"
                option-label="name"
                option-value="id"
                placeholder="Sem categoria"
                show-clear
                filter
                class="inbound-map__dropdown"
              />
            </div>
          </div>

          <!-- Preços / Custos -->
          <div class="inbound-map__grid-2">
            <div class="inbound-map__field">
              <label class="inbound-map__label">Custo Unitário da NF-e (R$)</label>
              <InputNumber
                v-model="quickCreateForm.estimated_cost"
                mode="currency"
                currency="BRL"
                locale="pt-BR"
                class="inbound-map__input-number"
                input-class="inbound-map__input"
              />
            </div>
            <div class="inbound-map__field">
              <label class="inbound-map__label">
                Preço de Venda / Cardápio (R$)
                <small class="inbound-map__sublabel">Definido pelo gerente (não utiliza o custo da nota)</small>
              </label>
              <InputNumber
                v-model="quickCreateForm.sale_price"
                mode="currency"
                currency="BRL"
                locale="pt-BR"
                placeholder="R$ 0,00"
                class="inbound-map__input-number"
                input-class="inbound-map__input"
              />
            </div>
          </div>

          <!-- Modos de Rastreamento Adicionais -->
          <div class="inbound-map__track-options">
            <span class="inbound-map__track-title">Rastreabilidade & Validade:</span>
            <div class="inbound-map__track-checks">
              <label class="inbound-map__checkbox-label">
                <Checkbox v-model="quickCreateForm.requires_lot_control" :binary="true" />
                <span>Exigir Lote e Data de Validade no Recebimento (FEFO)</span>
              </label>
              <label class="inbound-map__checkbox-label">
                <Checkbox v-model="quickCreateForm.requires_serial_number" :binary="true" />
                <span>Exigir Número de Série (Equipamentos / Ativos)</span>
              </label>
            </div>
          </div>
        </div>

        <div v-else-if="mappingMode === 'asset'" class="inbound-map__quick-form">
          <!-- ── ABA 3: Cadastrar em Patrimônios & Ativos ── -->
          <div class="inbound-map__callout inbound-map__callout--asset">
            <i class="pi pi-building text-cyan-400 text-xl" />
            <div>
              <strong class="text-cyan-300">Destino: Patrimônio e Ativos da Empresa</strong>
              <p class="mt-0.5 text-xs text-neutral-300">
                Este item será registrado diretamente em <strong>Patrimônio e Equipamentos</strong> (ao invés de mercadorias para revenda ou cardápio).
                Na conferência de entrada desta nota, o sistema solicitará os números de série e gerará os bens patrimoniais individuais com histórico e garantia.
              </p>
            </div>
          </div>

          <!-- Nome do Equipamento -->
          <div class="inbound-map__field">
            <label class="inbound-map__label">Nome do Bem Patrimonial / Equipamento *</label>
            <InputText
              v-model="quickAssetForm.name"
              class="inbound-map__input"
              placeholder="Ex: Forno Combinado Industrial 10 GNs Venâncio"
            />
          </div>

          <!-- Classificação & Custo -->
          <div class="inbound-map__grid-2">
            <div class="inbound-map__field">
              <label class="inbound-map__label">Classificação Patrimonial *</label>
              <Dropdown
                v-model="quickAssetForm.item_type"
                :options="ASSET_TYPE_OPTIONS"
                option-label="label"
                option-value="value"
                class="inbound-map__dropdown"
              />
            </div>
            <div class="inbound-map__field">
              <label class="inbound-map__label">Custo Unitário de Aquisição (R$)</label>
              <InputNumber
                v-model="quickAssetForm.purchase_price"
                mode="currency"
                currency="BRL"
                locale="pt-BR"
                class="inbound-map__input-number"
                input-class="inbound-map__input"
              />
            </div>
          </div>

          <!-- Marca & Modelo -->
          <div class="inbound-map__grid-2">
            <div class="inbound-map__field">
              <label class="inbound-map__label">Marca / Fabricante (Opcional)</label>
              <InputText
                v-model="quickAssetForm.brand"
                class="inbound-map__input"
                placeholder="Ex: Venâncio, Metalfrio, Brastemp, Elgin"
              />
            </div>
            <div class="inbound-map__field">
              <label class="inbound-map__label">Modelo / Especificação (Opcional)</label>
              <InputText
                v-model="quickAssetForm.model"
                class="inbound-map__input"
                placeholder="Ex: FC10GN, DA550"
              />
            </div>
          </div>

          <!-- Garantia & Unidade -->
          <div class="inbound-map__grid-2">
            <div class="inbound-map__field">
              <label class="inbound-map__label">Garantia de Fábrica Estimada (Meses)</label>
              <InputNumber
                v-model="quickAssetForm.warranty_months"
                :min="0"
                :max="120"
                class="inbound-map__input-number"
                input-class="inbound-map__input"
                placeholder="12"
              />
            </div>
            <div class="inbound-map__field">
              <label class="inbound-map__label">Unidade Patrimonial</label>
              <InputText
                v-model="quickAssetForm.stock_unit"
                class="inbound-map__input"
                placeholder="UN"
                readonly
              />
            </div>
          </div>

          <!-- Rastreabilidade Serializada -->
          <div class="inbound-map__track-options">
            <span class="inbound-map__track-title">Controle e Rastreabilidade:</span>
            <div class="inbound-map__track-checks">
              <label class="inbound-map__checkbox-label">
                <Checkbox v-model="quickAssetForm.requires_serial_number" :binary="true" />
                <span>Controlar por Número de Série Individual de Fábrica (gera etiqueta QR Code e plaqueta)</span>
              </label>
            </div>
          </div>
        </div>

        <!-- ── Seção de Conversão e Entrada no Estoque (Compartilhada) ── -->
        <div class="inbound-map__conversion-section">
          <div class="inbound-map__section-header">
            <i class="pi pi-sliders-h text-brand" />
            <span>Conversão de Unidade e Entrada no Estoque</span>
          </div>

          <!-- Seletor de Modo de Conversão -->
          <div class="mb-3">
            <label class="inbound-map__label mb-1.5 block">Como esta mercadoria é convertida para o estoque?</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                type="button"
                class="rpro-btn text-xs py-2 px-2 flex items-center justify-center gap-1.5 cursor-pointer"
                :class="mappingForm.conversion_mode === 'multiply' ? 'rpro-btn--primary font-bold shadow' : 'rpro-btn--ghost text-muted border border-neutral-700'"
                @click="onSelectMultiplyMode"
              >
                <i class="pi pi-times text-xs" /> Multiplicador
              </button>
              <button
                type="button"
                class="rpro-btn text-xs py-2 px-2 flex items-center justify-center gap-1.5 cursor-pointer"
                :class="mappingForm.conversion_mode === 'divide' ? 'rpro-btn--primary font-bold shadow' : 'rpro-btn--ghost text-muted border border-neutral-700'"
                @click="mappingForm.conversion_mode = 'divide'"
              >
                <i class="pi pi-percentage text-xs" /> Divisor / Fração
              </button>
              <button
                type="button"
                class="rpro-btn text-xs py-2 px-2 flex items-center justify-center gap-1.5 cursor-pointer"
                :class="mappingForm.conversion_mode === 'direct' ? 'rpro-btn--primary font-bold shadow' : 'rpro-btn--ghost text-muted border border-neutral-700'"
                @click="mappingForm.conversion_mode = 'direct'"
              >
                <i class="pi pi-arrows-h text-xs" /> Direto (1 : 1)
              </button>
            </div>
          </div>

          <div class="inbound-map__grid-2">
            <!-- Unidade de Estoque (SEMPRE EDITÁVEL) -->
            <div class="inbound-map__field">
              <label class="inbound-map__label">
                Unidade no seu Estoque *
                <small class="inbound-map__sublabel">Escolha ou digite (ex: UN, KG, G, L, ML, CX, PCT)</small>
              </label>
              <Dropdown
                v-model="mappingForm.stock_unit"
                :options="['UN', 'KG', 'G', 'L', 'ML', 'CX', 'PCT', 'DZ', 'FD', 'LT', 'BD', 'GL']"
                editable
                placeholder="Ex: UN, KG, G..."
                class="inbound-map__dropdown"
              />
            </div>

            <!-- Fator de Conversão de acordo com o modo -->
            <div class="inbound-map__field">
              <label class="inbound-map__label">
                <span v-if="mappingForm.conversion_mode === 'multiply'">Fator Multiplicador *</span>
                <span v-else-if="mappingForm.conversion_mode === 'divide'">Quantidade da Nota p/ 1 Unidade Estoque *</span>
                <span v-else>Mesma Unidade</span>
                <small class="inbound-map__sublabel">
                  <span v-if="mappingForm.conversion_mode === 'multiply'">Quantos {{ currentStockUnit }} vêm em cada 1 {{ mappingItem.commercial_unit || 'UN' }} da NF-e?</span>
                  <span v-else-if="mappingForm.conversion_mode === 'divide'">Quantos {{ mappingItem.commercial_unit || 'UN' }} formam 1 {{ currentStockUnit }} no estoque?</span>
                  <span v-else>1 {{ mappingItem.commercial_unit || 'UN' }} da nota equivale a 1 {{ currentStockUnit }} no estoque</span>
                </small>
              </label>

              <!-- Modo Multiplicador -->
              <div v-if="mappingForm.conversion_mode === 'multiply'" class="inbound-map__factor-wrapper">
                <span class="inbound-map__factor-prefix">1 {{ mappingItem.commercial_unit || 'UN' }} =</span>
                <InputNumber
                  v-model="mappingForm.conversion_factor"
                  :min="0.000001"
                  :min-fraction-digits="0"
                  :max-fraction-digits="6"
                  placeholder="Ex: 12"
                  class="inbound-map__factor-input"
                  input-class="inbound-map__factor-inner"
                />
                <span class="inbound-map__factor-suffix">{{ currentStockUnit }}</span>
              </div>

              <!-- Modo Divisor / Fração -->
              <div v-else-if="mappingForm.conversion_mode === 'divide'" class="inbound-map__factor-wrapper">
                <span class="inbound-map__factor-prefix">São necessários</span>
                <InputNumber
                  v-model="mappingForm.conversion_divisor"
                  :min="0.000001"
                  :min-fraction-digits="0"
                  :max-fraction-digits="6"
                  placeholder="Ex: 1000"
                  class="inbound-map__factor-input"
                  input-class="inbound-map__factor-inner"
                />
                <span class="inbound-map__factor-suffix">{{ mappingItem.commercial_unit || 'UN' }} p/ 1 {{ currentStockUnit }} (x{{ Number(effectiveConversionFactor.toFixed(4)) }})</span>
              </div>

              <!-- Modo Direto 1:1 -->
              <div v-else class="inbound-map__factor-wrapper bg-neutral-900 border border-neutral-800 rounded p-2 flex items-center justify-between">
                <span class="text-xs text-muted font-mono">1 {{ mappingItem.commercial_unit || 'UN' }} = 1 {{ currentStockUnit }}</span>
                <span class="rpro-badge bg-emerald-950 text-emerald-300 border border-emerald-800 text-xs">Fator 1.0 (Sem conversão)</span>
              </div>
            </div>
          </div>

          <!-- Preview / Simulador da Entrada em Tempo Real -->
          <div class="inbound-map__preview-box">
            <div class="inbound-map__preview-title">
              <i class="pi pi-calculator text-emerald-400" />
              <span>Simulação da Entrada Física no Estoque:</span>
            </div>
            <div class="inbound-map__preview-grid">
              <div class="inbound-map__preview-item">
                <span class="inbound-map__preview-lbl">Comprado na Nota</span>
                <strong class="inbound-map__preview-val">{{ Number(mappingItem.commercial_quantity) }} {{ mappingItem.commercial_unit }}</strong>
              </div>
              <div class="inbound-map__preview-arrow">
                <i class="pi pi-arrow-right" />
              </div>
              <div class="inbound-map__preview-item inbound-map__preview-item--highlight">
                <span class="inbound-map__preview-lbl">Entrada no Estoque</span>
                <strong class="inbound-map__preview-val text-emerald-400">{{ Number(calculatedStockQty.toFixed(4)) }} {{ currentStockUnit }}</strong>
              </div>
              <div class="inbound-map__preview-item">
                <span class="inbound-map__preview-lbl">Custo no Estoque</span>
                <strong class="inbound-map__preview-val">{{ money(calculatedUnitCostInStock) }} / {{ currentStockUnit }}</strong>
              </div>
            </div>
          </div>

          <label class="inbound-map__checkbox-label mt-2">
            <Checkbox v-model="mappingForm.save_supplier_mapping" :binary="true" />
            <span>Lembrar este vínculo automaticamente para as próximas notas deste fornecedor</span>
          </label>
        </div>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="mappingSubmitting" @click="mapItemDialogVisible = false">
          Cancelar
        </button>
        <button
          v-if="mappingMode === 'select'"
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="mappingSubmitting || !selectedTargetProduct"
          @click="submitItemMapping"
        >
          <i :class="mappingSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-check'" /> Salvar Vínculo
        </button>
        <button
          v-else-if="mappingMode === 'create'"
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="mappingSubmitting || !quickCreateForm.name"
          @click="submitQuickCreateAndMap"
        >
          <i :class="mappingSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-bolt'" /> Criar Produto e Vincular
        </button>
        <button
          v-else-if="mappingMode === 'asset'"
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="mappingSubmitting || !quickAssetForm.name"
          @click="submitQuickAssetAndMap"
        >
          <i :class="mappingSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-building'" /> Cadastrar em Patrimônio e Vincular
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
                <th style="width: 90px; text-align: right">Qtd NF-e</th>
                <th style="width: 110px; text-align: center">Fator Conversão</th>
                <th style="width: 130px; text-align: right">Entrada Estoque</th>
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
                  <small class="text-muted ml-1 font-bold">{{ it.commercial_unit }}</small>
                </td>
                <td style="text-align: center">
                  <div class="flex items-center justify-center gap-1">
                    <span class="text-xs text-muted font-bold">x</span>
                    <InputNumber
                      v-model="it.conversion_factor"
                      :min="0.0001"
                      :max-fraction-digits="4"
                      input-class="text-center w-16 p-1 text-xs font-mono font-bold"
                      @update:model-value="(val) => {
                        const f = Number(val || 1);
                        it.received_quantity = Number((Number(it.commercial_quantity) * f).toFixed(4));
                        if (f !== 1 && it.stock_unit === it.commercial_unit) {
                          it.stock_unit = it.product_stock_unit || 'UN';
                        }
                      }"
                    />
                  </div>
                </td>
                <td style="text-align: right">
                  <InputNumber
                    v-model="it.received_quantity"
                    :min-fraction-digits="0"
                    :max-fraction-digits="3"
                    input-class="text-right w-24 p-1 text-sm font-bold"
                  />
                  <div class="text-xs text-muted font-bold mt-0.5">
                    {{ it.stock_unit || 'UN' }}
                  </div>
                  <div v-if="Number(it.received_quantity) !== Number((Number(it.commercial_quantity) * Number(it.conversion_factor || 1)).toFixed(4))" class="text-xs text-amber-600 font-bold mt-1">
                    Divergência: {{ (Number(it.received_quantity) - (Number(it.commercial_quantity) * Number(it.conversion_factor || 1))).toFixed(2) }}
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
          @click="submitReceiveInvoiceFromDetail"
        >
          <i :class="receiveSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-box'" /> Confirmar Recebimento e Estoque
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Criação Rápida de Categoria ── -->
    <Dialog
      v-model:visible="inlineCategoryDialogVisible"
      modal
      header="Nova Categoria de Produto / Cardápio"
      :style="{ width: '420px' }"
    >
      <div class="py-2">
        <label class="rpage__label mb-1 block font-bold">Nome da Categoria *</label>
        <InputText
          v-model="inlineCategoryName"
          placeholder="Ex: Carnes Nobres, Bebidas, Laticínios..."
          class="w-full"
          @keyup.enter="submitInlineCategory"
        />
        <small class="text-xs text-muted block mt-1">
          A nova categoria ficará disponível para todo o cardápio e estoque.
        </small>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="inlineCategoryLoading" @click="inlineCategoryDialogVisible = false">
          Cancelar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="inlineCategoryLoading || !inlineCategoryName.trim()"
          @click="submitInlineCategory"
        >
          <i :class="inlineCategoryLoading ? 'pi pi-spin pi-spinner' : 'pi pi-check'" /> Salvar Categoria
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo Consulta Pontual (consNSU) ── -->
    <Dialog
      v-model:visible="fetchNsuDialogVisible"
      modal
      header="Buscar NSU Específico na SEFAZ"
      :style="{ width: '440px' }"
    >
      <div class="rpro__fetch-nsu-form">
        <p class="rpro-muted text-sm mb-3">
          Recupera uma nota fiscal pontual usando o método oficial <code>consNSU</code> da SEFAZ (limite de até 20 consultas por hora para este CNPJ).
        </p>

        <label class="rpro__bulk-field">
          <span>Número do NSU desejado (ex.: 54)</span>
          <InputText
            v-model="fetchNsuInput"
            type="number"
            min="1"
            placeholder="Ex: 54"
            class="w-full font-mono"
            @keyup.enter="submitFetchSpecificNsu"
          />
        </label>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="fetchingNsu" @click="fetchNsuDialogVisible = false">
          Cancelar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="fetchingNsu || !fetchNsuInput.trim()"
          @click="submitFetchSpecificNsu"
        >
          <i :class="fetchingNsu ? 'pi pi-spin pi-spinner' : 'pi pi-search'" />
          <span>{{ fetchingNsu ? 'Consultando...' : 'Consultar NSU' }}</span>
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo de Confirmação: Ciência da Operação (NF-e) ── -->
    <Dialog
      v-model:visible="scienceConfirmDialogVisible"
      modal
      header="Dar ciência desta NF-e?"
      :style="{ width: '560px', maxWidth: '95vw' }"
      :closable="!scienceSubmitting"
    >
      <div v-if="selectedScienceInvoice" class="rpro__science-modal">
        <div class="rpro__science-info-card">
          <div class="rpro__science-row">
            <span class="text-muted">Chave de Acesso:</span>
            <code class="font-mono text-xs font-bold">{{ selectedScienceInvoice.access_key }}</code>
          </div>
          <div class="rpro__science-row">
            <span class="text-muted">Fornecedor:</span>
            <strong>{{ selectedScienceInvoice.supplier_name || selectedScienceInvoice.supplier_cnpj || '—' }}</strong>
          </div>
          <div class="rpro__science-grid">
            <div>
              <span class="text-muted">Número:</span>
              <strong>{{ selectedScienceInvoice.number || '—' }}</strong>
            </div>
            <div>
              <span class="text-muted">Emissão:</span>
              <strong>{{ dateTime(selectedScienceInvoice.issue_date) }}</strong>
            </div>
            <div>
              <span class="text-muted">Valor da NF-e:</span>
              <strong class="text-emerald-400">{{ money(selectedScienceInvoice.total_invoice) }}</strong>
            </div>
          </div>
        </div>

        <div class="rpro__science-alert">
          <i class="pi pi-info-circle text-2xl text-indigo-400" />
          <div class="rpro__science-alert-text">
            <p>
              A <strong>Ciência da Operação (Evento 210210)</strong> informa oficialmente à SEFAZ que sua empresa tomou conhecimento desta nota fiscal para autorizar o download do XML completo com todos os produtos.
            </p>
            <p class="mt-2 text-xs text-amber-300">
              ⚠️ <strong>Atenção:</strong> Ela <strong>NÃO confirma o recebimento físico</strong> da mercadoria nem lança estoque. O recebimento e conferência física ocorrem em etapa posterior.
            </p>
          </div>
        </div>
      </div>

      <template #footer>
        <button
          class="rpro-btn rpro-btn--ghost"
          type="button"
          :disabled="scienceSubmitting"
          @click="scienceConfirmDialogVisible = false"
        >
          Cancelar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="scienceSubmitting"
          @click="confirmAndSendScience"
        >
          <i :class="scienceSubmitting ? 'pi pi-spin pi-spinner' : 'pi pi-bolt'" />
          <span>{{ scienceSubmitting ? 'Enviando à SEFAZ...' : 'Dar Ciência e Obter XML' }}</span>
        </button>
      </template>
    </Dialog>

    <!-- ── Diálogo de Upload / Importação de XMLs de NF-e ── -->
    <Dialog
      v-model:visible="uploadXmlDialogVisible"
      modal
      header="Importar Arquivos XML de NF-e"
      :style="{ width: 'min(580px, 95vw)' }"
    >
      <div class="rpro__upload-xml-form">
        <p class="rpro-muted text-sm mb-4">
          Faça upload de arquivos <code>.xml</code> de NF-e (ou um arquivo compactado <code>.zip</code> contendo múltiplos XMLs). O sistema identifica a chave de acesso, preenche os dados faltantes das notas existentes e cria os produtos para conferência e entrada no estoque.
        </p>

        <div
          class="rpro__dropzone cursor-pointer"
          :class="{ 'rpro__dropzone--active': isDraggingFiles }"
          @dragover.prevent="isDraggingFiles = true"
          @dragleave.prevent="isDraggingFiles = false"
          @drop.prevent="onFilesDropped"
          @click="$refs.xmlFileInput.click()"
        >
          <input
            ref="xmlFileInput"
            type="file"
            accept=".xml,.zip"
            multiple
            class="hidden"
            style="display: none"
            @change="onXmlFilesSelected"
          />
          <i class="pi pi-cloud-upload text-4xl text-brand mb-2" />
          <strong class="text-sm block">Clique para selecionar ou arraste arquivos aqui</strong>
          <span class="text-xs text-muted">Formatos aceitos: arquivos .XML ou pacotes .ZIP</span>
        </div>

        <!-- Lista de Arquivos Selecionados -->
        <div v-if="selectedXmlFiles.length" class="rpro__selected-files-list mt-4">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-bold uppercase text-muted">
              {{ selectedXmlFiles.length }} arquivo(s) selecionado(s)
            </span>
            <button
              type="button"
              class="rpro-btn rpro-btn--ghost rpro-btn--xs text-red-600"
              @click="selectedXmlFiles = []"
            >
              Limpar seleção
            </button>
          </div>

          <div class="rpro__selected-files-scroll">
            <div
              v-for="(f, idx) in selectedXmlFiles"
              :key="`${f.name}-${idx}`"
              class="rpro__selected-file-item"
            >
              <div class="flex items-center gap-2 overflow-hidden">
                <i :class="f.name.endsWith('.zip') ? 'pi pi-folder' : 'pi pi-file'" class="text-muted" />
                <span class="truncate text-sm font-medium">{{ f.name }}</span>
              </div>
              <small class="text-muted text-xs whitespace-nowrap">{{ (f.size / 1024).toFixed(1) }} KB</small>
            </div>
          </div>
        </div>

        <!-- Resultado do Processamento -->
        <div v-if="uploadXmlResult" class="rpro__upload-result mt-4">
          <div class="p-3 bg-surface-sunken border border-border rounded">
            <strong class="text-emerald-600 text-sm block">
              <i class="pi pi-check-circle" /> {{ uploadXmlResult.message }}
            </strong>
            <small v-if="uploadXmlResult.summary?.results?.length" class="text-xs text-muted block mt-1">
              Notas processadas: {{ uploadXmlResult.summary.results.map(r => `#${r.number || r.access_key.slice(-8)} (${r.action === 'created' ? 'Criada' : 'Atualizada'})`).join(', ') }}
            </small>
            <div v-if="uploadXmlResult.summary?.errors?.length" class="mt-2 text-xs text-red-600">
              <strong>Erros encontrados:</strong>
              <ul class="list-disc pl-4 mt-1">
                <li v-for="(err, i) in uploadXmlResult.summary.errors" :key="i">
                  {{ err.filename }}: {{ err.error }}
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="rpro-btn rpro-btn--ghost" type="button" :disabled="uploadingXml" @click="uploadXmlDialogVisible = false">
          Fechar
        </button>
        <button
          class="rpro-btn rpro-btn--primary"
          type="button"
          :disabled="uploadingXml || !selectedXmlFiles.length"
          @click="submitUploadXmlFiles"
        >
          <i :class="uploadingXml ? 'pi pi-spin pi-spinner' : 'pi pi-upload'" />
          <span>{{ uploadingXml ? 'Processando XMLs...' : 'Processar e Importar' }}</span>
        </button>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
/**
 * Variante "Pro" da listagem (tela-piloto do novo padrão de tabela — mockup).
 * Reaproveita todo o presenter `useResourceList` + `ResourceService`; só muda a
 * apresentação: cabeçalho com ações, cartões de resumo, filtro de período,
 * seleção em massa, filtros avançados, importação/exportação e paginação enxuta.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Checkbox from "primevue/checkbox";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Dialog from "primevue/dialog";
import Dropdown from "primevue/dropdown";
import IconField from "primevue/iconfield";
import InputIcon from "primevue/inputicon";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Menu from "primevue/menu";
import Tag from "primevue/tag";
import Textarea from "primevue/textarea";
import { useToast } from "primevue/usetoast";
import { useConfirm } from "primevue/useconfirm";
import { useResourceList } from "../composables/useResourceList";
import { api } from "../services/api";
import { getBrowserValue } from "../services/browserPersistence";
import { ResourceService } from "../services/ResourceService";
import { dataExchangeService } from "../services/dataExchangeService";
import { formatDateTime, formatMoney, mapLabel, roundUpToCent } from "../utils/format";
import { resolveColumnValue } from "../utils/object";
import { normalizeApiError } from "../utils/apiError";
import { buildBulkPayload, createBulkForm, missingBulkScope } from "../utils/bulkCreate";
import { useAuthStore } from "../stores/auth";
import { useRealtimeResource } from "../composables/useRealtimeResource";
import AppDateRange from "../components/form/AppDateRange.vue";
import InvoiceBulkResendButton from "../components/data/InvoiceBulkResendButton.vue";
import InboundHelpButton from "../components/inbound/InboundHelpButton.vue";
import ResourceAdvancedFiltersDialog from "../components/data/ResourceAdvancedFiltersDialog.vue";
import ResourceDirectFilters from "../components/data/ResourceDirectFilters.vue";
import { ASSET_STATUS_OPTIONS } from "../config/enums";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const toast = useToast();
const confirm = useConfirm();

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  endpoint: { type: String, required: true },
  columns: { type: Array, required: true },
  formFields: { type: Array, default: () => [] },
  defaultParams: { type: Object, default: () => ({}) },
  formEnabled: { type: Boolean, default: false },
  globalScope: { type: Boolean, default: false },
  pro: { type: Object, default: () => ({}) },
});

const proCfg = computed(() => props.pro || {});
const dateField = computed(() => proCfg.value.dateField || null);
const directFilterFields = computed(() => proCfg.value.filterFields || []);
// Ação primária: explícita no config, senão "Novo" quando o recurso tem formulário.
const primaryAction = computed(() => {
  if (proCfg.value.primaryAction) return proCfg.value.primaryAction;
  if (props.formEnabled) return { label: "Novo", icon: "pi pi-plus" };
  return null;
});

// Colunas atreladas a um módulo/permissão só aparecem se a conta tem o módulo
// e o usuário tem o código de permissão declarado.
const visibleColumns = computed(() => props.columns.filter(
  (column) => column.showInList !== false && auth.hasModule(column.module) && auth.hasPermission(column.permission),
));

// ── Estado local dos filtros "pro" ──────────────────────────────────
function initialDateRangeForEndpoint(endpoint) {
  if (endpoint === "/inbound-nfe/") {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);
    return [start, end];
  }
  return null;
}

const dateRange = ref(initialDateRangeForEndpoint(props.endpoint));
const selection = ref([]);
const mobileFiltersOpen = ref(false);
const advancedFiltersVisible = ref(false);
const advancedFilters = reactive({});
const importVisible = ref(false);
const importFile = ref(null);
const exchangeLoading = ref(false);

function ymd(date) {
  if (!(date instanceof Date)) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Params de data → `<param>_after` / `<param>_before` (backend). */
function dateParams() {
  if (!dateField.value || !Array.isArray(dateRange.value)) return {};
  const [start, end] = dateRange.value;
  const params = {};
  if (start) params[`${dateField.value.param}_after`] = ymd(start);
  if (end) params[`${dateField.value.param}_before`] = ymd(end);
  return params;
}

const inboundStatusFilter = ref("all");
const inboundStatusCounts = ref({});
const inboundRestaurantId = computed(() => getBrowserValue("starchef-restaurant-scope") || "");

const INBOUND_FILTER_OPTIONS = [
  { value: "all", label: "Todas as Notas", icon: "pi pi-list" },
  { value: "unmapped", label: "Pendente de Vínculo", icon: "pi pi-exclamation-triangle", tone: "warning" },
  { value: "ready", label: "Pronta p/ Entrada", icon: "pi pi-box", tone: "info" },
  { value: "received", label: "Entrada Concluída", icon: "pi pi-check-circle", tone: "success" },
  { value: "ignored", label: "Ignoradas", icon: "pi pi-eye-slash", tone: "neutral" },
  { value: "summary", label: "Resumo SEFAZ", icon: "pi pi-file", tone: "neutral" },
  { value: "cancelled", label: "Canceladas", icon: "pi pi-ban", tone: "danger" },
];

async function fetchInboundStatusCounts() {
  if (props.endpoint !== "/inbound-nfe/") return;
  try {
    const params = {
      ...dateParams(),
    };
    if (inboundRestaurantId.value) params.restaurant = inboundRestaurantId.value;
    const { data } = await api.get("/inbound-nfe/status-counts/", { params, skipRestaurantScope: true });
    inboundStatusCounts.value = data || {};
  } catch (err) {
    console.warn("Falha ao buscar contagens de status:", err);
  }
}

function setInboundFilter(val) {
  inboundStatusFilter.value = val;
  selection.value = [];
  reload();
  fetchInboundStatusCounts();
}

/** Filtros dinâmicos da tela: período (os demais irão para "filtros avançados"). */
function buildProParams() {
  const params = {
    ...linkFilters.value,
    ...dateParams(),
    ...Object.fromEntries(
      Object.entries(advancedFilters)
        .filter(([, value]) => value !== "" && value != null)
        .map(([key, value]) => [`filter__${key}`, value]),
    ),
  };
  if (props.endpoint === "/inbound-nfe/" && inboundStatusFilter.value && inboundStatusFilter.value !== "all") {
    params.mapping_filter = inboundStatusFilter.value;
  }
  if (props.endpoint === "/inbound-nfe/" && inboundRestaurantId.value) params.restaurant = inboundRestaurantId.value;
  return params;
}

// Presenter genérico: estado + busca + paginação server-side.
const service = new ResourceService({ endpoint: props.endpoint, globalScope: props.globalScope });
const {
  rows, total, page, rowsPerPage, ordering, loading, error, search,
  reload, goToPage, setSort, setPageSize,
} = useResourceList({
  service,
  defaultParams: props.defaultParams,
  buildParams: buildProParams,
  pageSize: proCfg.value.pageSize || 20,
});
// ── Filtros que chegam pela URL ──────────────────────────────────────
// So passam os campos declarados em `pro.linkFilters`: se qualquer query
// param da rota virasse filtro da API, um link com um parametro qualquer
// (ou um `?new=` esquecido) faria a listagem responder 400.
const linkFilterDefs = computed(() => (proCfg.value.linkFilters || [])
  .map((item) => (typeof item === "string" ? { key: item, label: item } : item)));
const activeLinkFilters = computed(() => linkFilterDefs.value.filter((item) => route.query[item.key]));
const linkFilters = computed(() => Object.fromEntries(
  activeLinkFilters.value.map((item) => [item.key, route.query[item.key]]),
));
const linkFilterLabels = computed(() => activeLinkFilters.value.map((item) => item.label));
function clearLinkFilters() {
  router.replace({ name: route.name, query: {} });
}
// A mesma rota pode ser reaberta com outro recorte sem remontar o componente.
// O nome da rota e comparado com o da montagem porque `route` ja aponta para o
// destino enquanto esta tela ainda existe — sem isso, sair da listagem
// dispararia uma busca inutil no caminho.
const listRouteName = route.name;
watch(
  () => route.query,
  () => {
    if (linkFilterDefs.value.length && route.name === listRouteName) loadRows();
  },
  { deep: true },
);

let searchDebounceTimer = null;

function onSearchInput() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    selection.value = [];
    reload();
    if (props.endpoint === "/inbound-nfe/") fetchInboundStatusCounts();
  }, 350);
}

function onSearchSubmit() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  selection.value = [];
  reload();
  if (props.endpoint === "/inbound-nfe/") fetchInboundStatusCounts();
}

function clearSearch() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  search.value = "";
  selection.value = [];
  reload();
  if (props.endpoint === "/inbound-nfe/") fetchInboundStatusCounts();
}

const loadRows = async () => {
  await reload();
  if (props.endpoint === "/inbound-nfe/") {
    fetchInboundStatusCounts();
  }
};
if (proCfg.value.defaultOrdering) ordering.value = proCfg.value.defaultOrdering;
else if (props.endpoint === "/orders/") ordering.value = "-updated_at";
else if (props.endpoint === "/inbound-nfe/") ordering.value = "-issue_date";
const realtimeModelByEndpoint = {
  "/orders/": "orders.order",
  "/tables/": "restaurants.table",
  "/commands/": "restaurants.command",
  "/customers/": "customers.customer",
  "/payments/": "payments.payment",
  "/payments/methods/": "payments.paymentmethod",
  "/menu/products/": "menu.product",
  "/menu/categories/": "menu.productcategory",
  "/menu/addons/": "menu.addon",
  "/stock/items/": "stock.stockitem",
  "/inbound-nfe/": "inbound_nfe.inboundnfe",
};
useRealtimeResource(realtimeModelByEndpoint[props.endpoint] || "*", (payload) => {
  // Unknown endpoint mappings still remain live; mapped lists only react to their model.
  if (realtimeModelByEndpoint[props.endpoint] || payload.resource) reload();
}, { debounce: 180 });
const activeFilterCount = computed(() =>
  Number(Boolean(search.value?.trim()))
  + Number(Boolean(dateRange.value?.length))
  + Object.values(advancedFilters).filter((value) => value !== "" && value != null).length,
);

const advancedFilterFields = computed(() => {
  const excluded = new Set(["textarea", "password", "json", "remote-multiselect"]);
  const fields = (props.formFields || [])
    .filter((field) => !excluded.has(field.type) && field.name !== "restaurants")
    .map((field) => ({ ...field }));
  for (const quick of proCfg.value.quickFilters || []) {
    const [name] = Object.keys(quick.filter || {});
    if (!name) continue;
    let field = fields.find((candidate) => candidate.name === name);
    if (!field) {
      const column = props.columns.find((candidate) => candidate.key === name);
      field = { name, label: column?.label || name, options: [] };
      fields.push(field);
    }
    field.options ||= [];
    if (!field.options.some((option) => option.value === quick.filter[name])) {
      field.options.push({ label: quick.label, value: quick.filter[name] });
    }
  }
  return fields;
});

const totalPages = computed(() => Math.max(1, Math.ceil((total.value || 0) / (rowsPerPage.value || 1))));

/* ── Ordenação server-side ─────────────────────────────────────────── */
const sortField = computed(() => (ordering.value ? ordering.value.replace(/^-/, "") : null));
const sortOrder = computed(() => (ordering.value ? (ordering.value.startsWith("-") ? -1 : 1) : null));
function onSort(event) {
  setSort(event.sortField, event.sortOrder);
}

function onDateRange(value) {
  dateRange.value = value;
  // Aguarda a segunda data do intervalo antes de recarregar.
  if (Array.isArray(value) && value[0] && !value[1]) return;
  selection.value = [];
  reload();
  if (props.endpoint === "/inbound-nfe/") fetchInboundStatusCounts();
}

function onDirectFilterChange({ name, value }) {
  advancedFilters[name] = value;
  selection.value = [];
  reload();
}
function applyMobileFilters() {
  reload();
  mobileFiltersOpen.value = false;
}

function clearMobileFilters() {
  search.value = "";
  dateRange.value = null;
  for (const key of Object.keys(advancedFilters)) advancedFilters[key] = "";
  selection.value = [];
  reload();
}

function applyAdvancedFilters() {
  selection.value = [];
  advancedFiltersVisible.value = false;
  reload();
}

function clearAdvancedFilters() {
  for (const field of advancedFilterFields.value) advancedFilters[field.name] = "";
  applyAdvancedFilters();
}

/* ── Navegação ─────────────────────────────────────────────────────── */
function openDetail(row) {
  if (!row?.id) return;
  if (props.endpoint === "/inbound-nfe/") {
    openInboundDetail(row);
    return;
  }
  // Recursos com tela de documento propria (entrada/saida de estoque) nao tem
  // a rota `--view` gerada: o documento E a tela de detalhe.
  const target = proCfg.value.detailRoute || `${route.name}--view`;
  router.push({ name: target, params: { id: row.id } });
}
function onRowClick(event) {
  const target = event.originalEvent?.target;
  // Não navega ao clicar no checkbox de seleção ou nos botões de ação.
  if (target && target.closest(".p-checkbox, .p-selection-column, .rpro__row-actions")) return;
  openDetail(event.data);
}
function runPrimary() {
  const action = primaryAction.value;
  if (!action) return;
  if (action.route) router.push({ name: action.route });
  else if (props.formEnabled) router.push({ name: `${route.name}--create` });
}

// ── Ações do cabeçalho (config `pro.headerActions`) ───────────────────
const headerActions = computed(() => proCfg.value.headerActions || []);
const syncingSefaz = ref(false);
const dfeSyncInfo = ref(null);
const dfeSyncLoading = ref(false);
const nowTick = ref(Date.now());
let dfeTimerInterval = null;
const dfeMinutesRemaining = computed(() => {
  if (!dfeSyncInfo.value?.next_allowed_at) {
    return dfeSyncInfo.value?.minutes_remaining || 0;
  }
  const target = new Date(dfeSyncInfo.value.next_allowed_at).getTime();
  if (isNaN(target)) return dfeSyncInfo.value?.minutes_remaining || 0;
  const diffMs = target - nowTick.value;
  return diffMs > 0 ? Math.max(1, Math.ceil(diffMs / 60000)) : 0;
});

const isDfeBlocked = computed(() => {
  if (!dfeSyncInfo.value) return false;
  if (dfeMinutesRemaining.value > 0) return true;
  return Boolean(dfeSyncInfo.value.is_blocked && (!dfeSyncInfo.value.next_allowed_at || dfeMinutesRemaining.value > 0));
});

async function loadDfeSyncInfo() {
  if (props.endpoint !== "/inbound-nfe/") return;
  dfeSyncLoading.value = true;
  try {
    const params = inboundRestaurantId.value ? { restaurant: inboundRestaurantId.value } : {};
    const { data } = await api.get("/inbound-nfe/sync/", { params, skipRestaurantScope: true });
    dfeSyncInfo.value = data;
    nowTick.value = Date.now();
  } catch (err) {
    console.error("Erro ao carregar status do DF-e:", err);
  } finally {
    dfeSyncLoading.value = false;
  }
}

function formatDfeDate(isoString) {
  if (!isoString) return "Não sincronizado";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "Não sincronizado";
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoString;
  }
}

async function triggerSefazSync() {
  if (!inboundRestaurantId.value) {
    toast.add({
      severity: "warn",
      summary: "Selecione uma Unidade",
      detail: "Selecione uma unidade específica na barra lateral (menu superior) para sincronizar com a SEFAZ.",
      life: 5000,
    });
    return;
  }
  if (dfeSyncInfo.value?.has_certificate === false) {
    toast.add({
      severity: "warn",
      summary: "Certificado Pendente",
      detail: `Certificado Digital A1 não configurado para ${dfeSyncInfo.value?.restaurant_name || "este restaurante"}. Configure no perfil do restaurante.`,
      life: 6000,
    });
    return;
  }
  if (isDfeBlocked.value) {
    toast.add({
      severity: "warn",
      summary: "Sincronização Bloqueada",
      detail: dfeSyncInfo.value?.blocked_reason || `Aguarde a janela de segurança da SEFAZ até ${formatDfeDate(dfeSyncInfo.value?.next_allowed_at)} (~${dfeMinutesRemaining.value} min restantes).`,
      life: 8000,
    });
    return;
  }
  syncingSefaz.value = true;
  try {
    const { data } = await api.post("/inbound-nfe/sync/", { restaurant: inboundRestaurantId.value }, { skipRestaurantScope: true });
    toast.add({
      severity: data.cstat === "138" ? "success" : data.cstat === "656" ? "warn" : "info",
      summary: "Sincronização SEFAZ",
      detail: data.reason || `Status: ${data.cstat} (ultNSU: ${data.ult_nsu})`,
      life: 7000,
    });
    await loadDfeSyncInfo();
    await reload();
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Sincronização Bloqueada / Erro",
      detail: norm.message,
      life: 8000,
    });
    await loadDfeSyncInfo();
  } finally {
    syncingSefaz.value = false;
  }
}

function runHeaderAction(headerAction) {
  if (headerAction.type === "bulk-create") openBulk(headerAction.bulkType);
  else if (headerAction.type === "route") {
    router.push({ name: headerAction.routeName, query: headerAction.query || {} });
  }
  else if (headerAction.type === "sync-sefaz") triggerSefazSync();
  else if (headerAction.type === "upload-xml") openUploadXmlDialog();
}

// ── Detalhes da NF-e de Entrada (Itens, Valores e Tributos) ───────────
const inboundDetailVisible = ref(false);
const inboundDetailLoading = ref(false);
const inboundDetailData = ref(null);

async function openInboundDetail(row) {
  if (!row?.id) return;
  inboundDetailVisible.value = true;
  inboundDetailLoading.value = true;
  inboundDetailData.value = null;
  try {
    const { data } = await api.get(`/inbound-nfe/${row.id}/`);
    inboundDetailData.value = data;
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro ao carregar detalhes da NF-e",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
    inboundDetailVisible.value = false;
  } finally {
    inboundDetailLoading.value = false;
  }
}

function copyAccessKey(key) {
  if (!key) return;
  navigator.clipboard.writeText(key);
  toast.add({
    severity: "success",
    summary: "Chave copiada",
    detail: "Chave de acesso copiada para a área de transferência.",
    life: 2500,
  });
}

// ── Vínculo de Item da NF-e (DE/PARA com Autocomplete & Criação Rápida) ─
const mapItemDialogVisible = ref(false);
const mappingItem = ref(null);
const mappingMode = ref("select"); // "select" | "create"
const mappingSearch = ref("");
const mappingTypeFilter = ref("ALL");
const selectedTargetProduct = ref(null);

const mappingForm = reactive({
  targetType: "product", // "ingredient" | "product"
  ingredient_id: null,
  product_id: null,
  stock_unit: "UN",
  conversion_mode: "multiply", // "multiply" | "divide" | "direct"
  conversion_factor: 1,
  conversion_divisor: 1,
  save_supplier_mapping: true,
});

const effectiveConversionFactor = computed(() => {
  if (mappingForm.conversion_mode === "direct") return 1;
  if (mappingForm.conversion_mode === "divide") {
    const div = Number(mappingForm.conversion_divisor) || 1;
    return div > 0 ? 1 / div : 1;
  }
  return Number(mappingForm.conversion_factor) || 1;
});

watch(effectiveConversionFactor, (factor) => {
  const rawCost = Number(mappingItem.value?.commercial_unit_value) || 0;
  if (rawCost > 0 && factor > 0) {
    quickCreateForm.estimated_cost = roundUpToCent(rawCost / factor);
  }
});

const quickCreateForm = reactive({
  name: "",
  item_type: "INGREDIENT",
  category: null,
  stock_unit: "UN",
  estimated_cost: 0,
  sale_price: 0,
  requires_lot_control: false,
  requires_serial_number: false,
});

const inlineCategoryDialogVisible = ref(false);
const inlineCategoryName = ref("");
const inlineCategoryLoading = ref(false);

function openInlineCategoryModal() {
  inlineCategoryName.value = "";
  inlineCategoryDialogVisible.value = true;
}

async function submitInlineCategory() {
  const name = inlineCategoryName.value.trim();
  if (!name) return;
  inlineCategoryLoading.value = true;
  try {
    const { data } = await api.post("/menu/categories/", {
      name,
      display_order: mappingCategories.value.length + 1,
      is_active: true,
    });
    mappingCategories.value.push(data);
    quickCreateForm.category = data.id;
    inlineCategoryDialogVisible.value = false;
    toast.add({ severity: "success", summary: "Categoria Criada", detail: `Categoria '${name}' criada com sucesso.`, life: 3000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao criar categoria", detail: normalizeApiError(err).message, life: 5000 });
  } finally {
    inlineCategoryLoading.value = false;
  }
}

const ASSET_TYPE_OPTIONS = [
  { label: "🔌 Equipamento Operacional (Fornos, Freezers, Balanças, PDVs)", value: "EQUIPMENT" },
  { label: "🏢 Ativo Fixo / Imobilizado (Móveis, Computadores, Mobília)", value: "FIXED_ASSET" },
  { label: "🍽️ Material Reutilizável (Bandejas, Utensílios de Cozinha)", value: "REUSABLE_MATERIAL" },
];

const quickAssetForm = reactive({
  name: "",
  item_type: "EQUIPMENT",
  brand: "",
  model: "",
  purchase_price: 0,
  warranty_months: 12,
  requires_serial_number: true,
  stock_unit: "UN",
});

const mappingCategories = ref([]);
const mappingIngredients = ref([]);
const mappingProducts = ref([]);
const mappingLoading = ref(false);
const mappingSubmitting = ref(false);

const ITEM_TYPE_OPTIONS_ALL = [
  { label: "🥗 Insumo / Matéria-Prima (Perecíveis & Ingredientes)", value: "INGREDIENT" },
  { label: "🛒 Mercadoria p/ Venda / Cardápio", value: "RESALE_PRODUCT" },
  { label: "🧻 Material de Consumo (Limpeza, Descartáveis)", value: "CONSUMABLE" },
  { label: "📦 Embalagens", value: "PACKAGING" },
  { label: "🍽️ Material Reutilizável (Pratos, Copos, Talheres)", value: "REUSABLE_MATERIAL" },
  { label: "🔌 Equipamento / Ativo Imobilizado (Maquinários & POS)", value: "EQUIPMENT" },
];

const mappingTypeFilters = [
  { label: "Todos os Itens", value: "ALL" },
  { label: "🏢 Patrimônio & Ativos", value: "ASSET_ALL" },
  { label: "🥗 Insumos", value: "INGREDIENT" },
  { label: "🛒 Venda / Cardápio", value: "RESALE_PRODUCT" },
  { label: "🧻 Consumo", value: "CONSUMABLE" },
  { label: "🍽️ Utensílios", value: "REUSABLE_MATERIAL" },
];

function getItemTypeLabel(type) {
  const map = {
    INGREDIENT: "Insumo",
    RAW_MATERIAL_INGREDIENT: "Insumo",
    RESALE_PRODUCT: "Venda",
    MERCHANDISE_FOR_SALE: "Venda",
    CONSUMABLE: "Consumo",
    PACKAGING: "Embalagem",
    REUSABLE_MATERIAL: "Utensílio",
    EQUIPMENT: "Equipamento",
    FIXED_ASSET: "Patrimônio",
  };
  return map[type] || type || "Item";
}

// eslint-disable-next-line no-unused-vars
function getItemTypeBadgeClass(type) {
  const map = {
    INGREDIENT: "bg-emerald-950 text-emerald-300 border border-emerald-800",
    RAW_MATERIAL_INGREDIENT: "bg-emerald-950 text-emerald-300 border border-emerald-800",
    RESALE_PRODUCT: "bg-blue-950 text-blue-300 border border-blue-800",
    MERCHANDISE_FOR_SALE: "bg-blue-950 text-blue-300 border border-blue-800",
    CONSUMABLE: "bg-amber-950 text-amber-300 border border-amber-800",
    PACKAGING: "bg-orange-950 text-orange-300 border border-orange-800",
    REUSABLE_MATERIAL: "bg-purple-950 text-purple-300 border border-purple-800",
    EQUIPMENT: "bg-cyan-950 text-cyan-300 border border-cyan-800",
    FIXED_ASSET: "bg-cyan-950 text-cyan-300 border border-cyan-800",
  };
  return map[type] || "bg-neutral-800 text-neutral-300";
}

const allNormalizedItems = computed(() => {
  const list = [];
  for (const p of mappingProducts.value) {
    list.push({
      id: p.id,
      name: p.name,
      type: "product",
      item_type: p.item_type || "RESALE_PRODUCT",
      category_name: p.category_name,
      stock_unit: p.stock_unit || "UN",
      internal_code: p.internal_code,
      gtin: p.gtin,
      sale_price: p.sale_price,
    });
  }
  for (const ing of mappingIngredients.value) {
    list.push({
      id: ing.id,
      name: ing.name,
      type: "ingredient",
      item_type: "INGREDIENT",
      category_name: "Ingredientes",
      stock_unit: (ing.unit || "UN").toUpperCase(),
      internal_code: ing.internal_code || "-",
      gtin: "",
      sale_price: ing.cost_per_unit || 0,
    });
  }
  return list;
});

const filteredMappingProducts = computed(() => {
  let list = allNormalizedItems.value;
  if (mappingTypeFilter.value === "ASSET_ALL") {
    list = list.filter((it) => ["EQUIPMENT", "FIXED_ASSET", "REUSABLE_MATERIAL"].includes(it.item_type));
  } else if (mappingTypeFilter.value !== "ALL") {
    list = list.filter((it) => it.item_type === mappingTypeFilter.value);
  }
  const q = (mappingSearch.value || "").trim().toLowerCase();
  if (q) {
    list = list.filter(
      (it) =>
        (it.name || "").toLowerCase().includes(q) ||
        (it.internal_code || "").toLowerCase().includes(q) ||
        (it.gtin || "").toLowerCase().includes(q) ||
        (it.category_name || "").toLowerCase().includes(q)
    );
  }
  return list;
});

const currentStockUnit = computed(() => {
  if (mappingForm.stock_unit) {
    return mappingForm.stock_unit.toUpperCase();
  }
  if (mappingMode.value === "create") {
    return (quickCreateForm.stock_unit || "UN").toUpperCase();
  }
  if (mappingMode.value === "asset") {
    return (quickAssetForm.stock_unit || "UN").toUpperCase();
  }
  return (selectedTargetProduct.value?.stock_unit || "UN").toUpperCase();
});

const calculatedStockQty = computed(() => {
  if (!mappingItem.value) return 0;
  const commQty = Number(mappingItem.value.commercial_quantity) || 0;
  return commQty * effectiveConversionFactor.value;
});

const calculatedUnitCostInStock = computed(() => {
  if (!mappingItem.value) return 0;
  const total = Number(mappingItem.value.product_total) || 0;
  const finalQty = calculatedStockQty.value;
  if (!finalQty || finalQty <= 0) return 0;
  return roundUpToCent(total / finalQty);
});

async function loadMappingOptions() {
  mappingLoading.value = true;
  try {
    const [ingRes, prodRes, catRes] = await Promise.all([
      api.get("/menu/ingredients/", { params: { page_size: 300 } }),
      api.get("/menu/products/", { params: { page_size: 500 } }),
      api.get("/menu/categories/", { params: { page_size: 200 } }),
    ]);
    mappingIngredients.value = ingRes.data.results || ingRes.data || [];
    mappingProducts.value = prodRes.data.results || prodRes.data || [];
    mappingCategories.value = catRes.data.results || catRes.data || [];
  } catch (err) {
    console.error("Erro ao carregar opções de mapeamento:", err);
  } finally {
    mappingLoading.value = false;
  }
}

function selectTargetProduct(prod) {
  selectedTargetProduct.value = prod;
  mappingForm.targetType = prod.type;
  mappingForm.product_id = prod.type === "product" ? prod.id : null;
  mappingForm.ingredient_id = prod.type === "ingredient" ? prod.id : null;
  if (prod.stock_unit) {
    mappingForm.stock_unit = prod.stock_unit.toUpperCase();
  }
}

function onQuickCreateItemTypeChange(ev) {
  const val = ev.value;
  if (val === "EQUIPMENT") {
    quickCreateForm.requires_serial_number = true;
    quickCreateForm.requires_lot_control = false;
  } else {
    quickCreateForm.requires_lot_control = false;
    quickCreateForm.requires_serial_number = false;
  }
}

function onSelectMultiplyMode() {
  mappingForm.conversion_mode = "multiply";
  const commU = (mappingItem.value?.commercial_unit || "").toUpperCase().trim();
  if (!mappingForm.stock_unit || mappingForm.stock_unit.toUpperCase().trim() === commU) {
    mappingForm.stock_unit = "UN";
    quickCreateForm.stock_unit = "UN";
  }
}

function switchToQuickCreate() {
  mappingMode.value = "create";
  quickCreateForm.name = (mappingSearch.value || mappingItem.value?.description || "").trim();
  quickCreateForm.item_type = "INGREDIENT";
  quickCreateForm.category = null;
  const factor = effectiveConversionFactor.value || 1;
  const commU = (mappingItem.value?.commercial_unit || "UN").toUpperCase().trim();
  const isPackage = ["CX", "FD", "DZ", "PCT", "CXA", "FARDO", "PACOTE", "ROLO"].includes(commU);
  if (mappingForm.stock_unit && mappingForm.stock_unit !== commU) {
    quickCreateForm.stock_unit = mappingForm.stock_unit.toUpperCase().slice(0, 8);
  } else {
    quickCreateForm.stock_unit = (factor !== 1 || isPackage ? "UN" : commU).slice(0, 8);
  }
  const unitCost = Number(mappingItem.value?.commercial_unit_value) || 0;
  quickCreateForm.estimated_cost = factor > 0 ? roundUpToCent(unitCost / factor) : roundUpToCent(unitCost);
  quickCreateForm.sale_price = 0;
  quickCreateForm.requires_lot_control = false;
  quickCreateForm.requires_serial_number = false;
}

function switchToQuickAsset() {
  mappingMode.value = "asset";
  quickAssetForm.name = (mappingSearch.value || mappingItem.value?.description || "").trim();
  quickAssetForm.item_type = "EQUIPMENT";
  quickAssetForm.brand = "";
  quickAssetForm.model = "";
  quickAssetForm.purchase_price = roundUpToCent(Number(mappingItem.value?.commercial_unit_value) || 0);
  quickAssetForm.warranty_months = 12;
  quickAssetForm.requires_serial_number = true;
  quickAssetForm.stock_unit = (mappingItem.value?.commercial_unit || "UN").toUpperCase().slice(0, 8);
  mappingForm.conversion_factor = 1;
}

async function openMapModal(item) {
  mappingItem.value = item;
  mappingSearch.value = "";
  mappingTypeFilter.value = "ALL";
  selectedTargetProduct.value = null;
  mappingMode.value = "select";

  mappingForm.targetType = item.product ? "product" : (item.ingredient ? "ingredient" : "product");
  mappingForm.ingredient_id = item.ingredient || null;
  mappingForm.product_id = item.product || null;
  const factor = Number(item.conversion_factor) || 1;
  let rawStockUnit = item.product_stock_unit || (item.ingredient_unit?.toUpperCase() === "UNIT" ? "UN" : item.ingredient_unit);
  const commU = (item.commercial_unit || "UN").toUpperCase().trim();
  const isPackage = ["CX", "FD", "DZ", "PCT", "CXA", "FARDO", "PACOTE", "ROLO"].includes(commU);
  if (factor !== 1 && rawStockUnit && rawStockUnit.toUpperCase().trim() === commU) {
    rawStockUnit = "UN";
  }
  const resolvedStockU = (rawStockUnit || (factor !== 1 || isPackage ? "UN" : commU) || "UN").toUpperCase();
  mappingForm.stock_unit = resolvedStockU;
  if (factor === 1) {
    mappingForm.conversion_mode = "direct";
    mappingForm.conversion_factor = 1;
    mappingForm.conversion_divisor = 1;
  } else if (factor < 1 && factor > 0) {
    mappingForm.conversion_mode = "divide";
    mappingForm.conversion_divisor = Math.round((1 / factor) * 10000) / 10000;
    mappingForm.conversion_factor = factor;
  } else {
    mappingForm.conversion_mode = "multiply";
    mappingForm.conversion_factor = factor;
    mappingForm.conversion_divisor = factor;
  }
  mappingForm.save_supplier_mapping = true;

  quickCreateForm.name = (item.description || "").trim();
  quickCreateForm.item_type = "INGREDIENT";
  quickCreateForm.category = null;
  quickCreateForm.stock_unit = resolvedStockU.slice(0, 8);
  const unitCost = Number(item.commercial_unit_value) || 0;
  quickCreateForm.estimated_cost = factor > 0 ? roundUpToCent(unitCost / factor) : roundUpToCent(unitCost);
  quickCreateForm.sale_price = 0;
  quickCreateForm.requires_lot_control = false;
  quickCreateForm.requires_serial_number = false;

  mapItemDialogVisible.value = true;
  await loadMappingOptions();

  // Se já tinha vínculo prévio, localiza e seleciona
  if (item.product || item.ingredient) {
    const existing = allNormalizedItems.value.find(
      (it) => (item.product && it.type === "product" && it.id === item.product) ||
              (item.ingredient && it.type === "ingredient" && it.id === item.ingredient)
    );
    if (existing) {
      selectTargetProduct(existing);
      mappingForm.stock_unit = (existing.stock_unit || mappingForm.stock_unit).toUpperCase();
    }
  } else if (item.ean && item.ean !== "Sem GTIN") {
    const cleanEan = item.ean.trim();
    const existingByEan = allNormalizedItems.value.find(
      (it) => it.gtin && it.gtin.trim() === cleanEan
    );
    if (existingByEan) {
      selectTargetProduct(existingByEan);
      mappingForm.stock_unit = (existingByEan.stock_unit || mappingForm.stock_unit).toUpperCase();
    }
  }
}

async function submitItemMapping() {
  if (!mappingItem.value?.id) return;
  if (!selectedTargetProduct.value) {
    toast.add({ severity: "warn", summary: "Selecione um item", detail: "Escolha um produto ou insumo para vincular.", life: 3000 });
    return;
  }
  mappingSubmitting.value = true;
  try {
    const chosenUnit = (mappingForm.stock_unit || "UN").toUpperCase();
    // Atualiza a unidade de estoque do produto/insumo caso o usuário tenha ajustado
    if (chosenUnit && chosenUnit !== selectedTargetProduct.value.stock_unit) {
      try {
        if (selectedTargetProduct.value.type === "product") {
          await api.patch(`/menu/products/${selectedTargetProduct.value.id}/`, { stock_unit: chosenUnit });
        } else if (selectedTargetProduct.value.type === "ingredient") {
          await api.patch(`/menu/ingredients/${selectedTargetProduct.value.id}/`, { unit: chosenUnit.toLowerCase() });
        }
      } catch (err) {
        void err;
      }
    }

    await api.post(`/inbound-nfe-items/${mappingItem.value.id}/map/`, {
      product_id: selectedTargetProduct.value.type === "product" ? selectedTargetProduct.value.id : null,
      ingredient_id: selectedTargetProduct.value.type === "ingredient" ? selectedTargetProduct.value.id : null,
      conversion_factor: effectiveConversionFactor.value,
      save_supplier_mapping: mappingForm.save_supplier_mapping,
    });

    toast.add({
      severity: "success",
      summary: "Vínculo salvo",
      detail: `Item vinculado a '${selectedTargetProduct.value.name}' com sucesso.`,
      life: 4000,
    });

    mapItemDialogVisible.value = false;
    await loadMappingOptions();
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao salvar vínculo", detail: normalizeApiError(err).message, life: 5000 });
  } finally {
    mappingSubmitting.value = false;
  }
}

async function submitQuickCreateAndMap() {
  if (!quickCreateForm.name || !quickCreateForm.name.trim()) {
    toast.add({ severity: "warn", summary: "Informe o nome", detail: "O nome do produto é obrigatório.", life: 3000 });
    return;
  }
  mappingSubmitting.value = true;
  try {
    let tracking_mode = "QUANTITY";
    if (quickCreateForm.requires_serial_number) tracking_mode = "SERIALIZED";
    else if (quickCreateForm.requires_lot_control) tracking_mode = "LOT";

    const gtinVal = (mappingItem.value?.ean && mappingItem.value.ean !== "Sem GTIN") ? mappingItem.value.ean.trim() : "";
    const targetRestaurant = inboundDetailData.value?.restaurant || inboundRestaurantId.value;
    const stockUnit = (mappingForm.stock_unit || quickCreateForm.stock_unit || "UN").toUpperCase();

    if (quickCreateForm.item_type === "INGREDIENT") {
      let chosenUnit = stockUnit.toLowerCase();
      if (chosenUnit === "un") chosenUnit = "unit";
      if (!["unit", "kg", "g", "l", "ml"].includes(chosenUnit)) {
        chosenUnit = "unit";
      }
      const ingredientPayload = {
        name: quickCreateForm.name.trim(),
        unit: chosenUnit,
        average_cost: roundUpToCent(quickCreateForm.estimated_cost || 0),
        is_active: true,
      };
      if (targetRestaurant) {
        ingredientPayload.restaurant = targetRestaurant;
      }
      let newIng;
      try {
        const resp = await api.post("/menu/ingredients/", ingredientPayload);
        newIng = resp.data;
      } catch (createErr) {
        const findResp = await api.get(`/menu/ingredients/?search=${encodeURIComponent(quickCreateForm.name.trim())}&page_size=10`);
        const foundList = findResp.data?.results || findResp.data || [];
        newIng = foundList.find((it) => it.name.toLowerCase() === quickCreateForm.name.trim().toLowerCase());
        if (!newIng) throw createErr;
      }

      await api.post(`/inbound-nfe-items/${mappingItem.value.id}/map/`, {
        product_id: null,
        ingredient_id: newIng.id,
        conversion_factor: effectiveConversionFactor.value,
        save_supplier_mapping: mappingForm.save_supplier_mapping,
      });

      toast.add({
        severity: "success",
        summary: "Ingrediente Criado e Vinculado!",
        detail: `'${newIng.name}' cadastrado como ingrediente e associado ao item da nota fiscal.`,
        life: 4000,
      });

      mapItemDialogVisible.value = false;
      await loadMappingOptions();
      if (inboundDetailData.value?.id) {
        await openInboundDetail(inboundDetailData.value);
      }
      await reload();
      return;
    }

    const productPayload = {
      name: quickCreateForm.name.trim(),
      item_type: quickCreateForm.item_type || "PRODUCT",
      category: quickCreateForm.category || null,
      gtin: gtinVal,
      stock_unit: stockUnit,
      estimated_cost: roundUpToCent(quickCreateForm.estimated_cost || 0),
      sale_price: quickCreateForm.sale_price || 0,
      tracking_mode,
      requires_lot_control: quickCreateForm.requires_lot_control,
      requires_expiration_control: quickCreateForm.requires_lot_control,
      requires_serial_number: quickCreateForm.requires_serial_number,
      controls_stock: true,
      is_active: true,
    };
    if (targetRestaurant) {
      productPayload.restaurant = targetRestaurant;
      productPayload.restaurants = [targetRestaurant];
    }

    let newProd;
    try {
      const resp = await api.post("/menu/products/", productPayload);
      newProd = resp.data;
    } catch (createErr) {
      // Se já existe produto com o mesmo GTIN, localiza o existente para vincular
      if (gtinVal) {
        let existing = allNormalizedItems.value.find((it) => it.gtin && it.gtin.trim() === gtinVal);
        if (!existing) {
          try {
            const findResp = await api.get(`/menu/products/?search=${encodeURIComponent(gtinVal)}&page_size=10`);
            const foundList = findResp.data?.results || findResp.data || [];
            existing = foundList.find((it) => it.gtin && it.gtin.trim() === gtinVal);
          } catch (err) {
            void err;
          }
        }
        if (existing) {
          toast.add({
            severity: "info",
            summary: "Produto Existente Localizado",
            detail: `O produto '${existing.name}' já possui este código de barras e foi vinculado.`,
            life: 5000,
          });
          newProd = existing;
        } else {
          throw createErr;
        }
      } else {
        throw createErr;
      }
    }

    // Imediatamente vincula o produto ao item da NF-e com o fator de conversão efetivo
    await api.post(`/inbound-nfe-items/${mappingItem.value.id}/map/`, {
      product_id: newProd.id,
      ingredient_id: null,
      conversion_factor: effectiveConversionFactor.value,
      save_supplier_mapping: mappingForm.save_supplier_mapping,
    });

    toast.add({
      severity: "success",
      summary: "Produto Criado e Vinculado!",
      detail: `'${newProd.name}' cadastrado e associado ao item da nota fiscal.`,
      life: 4000,
    });

    mapItemDialogVisible.value = false;
    await loadMappingOptions();
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro no cadastro rápido",
      detail: normalizeApiError(err).message,
      life: 6000,
    });
  } finally {
    mappingSubmitting.value = false;
  }
}

async function submitQuickAssetAndMap() {
  if (!quickAssetForm.name || !quickAssetForm.name.trim()) {
    toast.add({ severity: "warn", summary: "Informe o nome", detail: "O nome do patrimônio/equipamento é obrigatório.", life: 3000 });
    return;
  }
  mappingSubmitting.value = true;
  try {
    const gtinVal = (mappingItem.value?.ean && mappingItem.value.ean !== "Sem GTIN") ? mappingItem.value.ean.trim() : "";
    const targetRestaurant = inboundDetailData.value?.restaurant || inboundRestaurantId.value;
    const payload = {
      name: quickAssetForm.name.trim(),
      item_type: quickAssetForm.item_type,
      brand: (quickAssetForm.brand || "").trim(),
      model: (quickAssetForm.model || "").trim(),
      stock_unit: (mappingForm.stock_unit || quickAssetForm.stock_unit || "UN").toUpperCase(),
      estimated_cost: roundUpToCent(quickAssetForm.purchase_price || 0),
      sale_price: 0,
      pricing_unit: "unit",
      product_type: "input",
      gtin: gtinVal,
      tracking_mode: quickAssetForm.requires_serial_number ? "SERIALIZED" : "QUANTITY",
      requires_serial_number: quickAssetForm.requires_serial_number,
      requires_lot_control: false,
      requires_expiration_control: false,
      default_useful_life_months: quickAssetForm.warranty_months || 12,
      controls_stock: true,
      is_active: false,
      available_for_table: false,
      available_for_counter: false,
      available_for_delivery: false,
    };
    if (targetRestaurant) {
      payload.restaurant = targetRestaurant;
      payload.restaurants = [targetRestaurant];
    }

    const { data: newProd } = await api.post("/menu/products/", payload);

    await api.post(`/inbound-nfe-items/${mappingItem.value.id}/map/`, {
      product_id: newProd.id,
      ingredient_id: null,
      conversion_factor: effectiveConversionFactor.value,
      save_supplier_mapping: mappingForm.save_supplier_mapping,
    });

    toast.add({
      severity: "success",
      summary: "Patrimônio Cadastrado e Vinculado!",
      detail: `'${newProd.name}' cadastrado em Patrimônio & Ativos e vinculado à nota fiscal.`,
      life: 5000,
    });

    mapItemDialogVisible.value = false;
    await loadMappingOptions();
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro ao cadastrar patrimônio",
      detail: normalizeApiError(err).message,
      life: 6000,
    });
  } finally {
    mappingSubmitting.value = false;
  }
}

// ── Recebimento Físico / Entrada no Estoque ───────────────────────────
const receiveDialogVisible = ref(false);
const receiveStockLocations = ref([]);
const receiveLocationsLoading = ref(false);
const receiveSubmitting = ref(false);
const receiveForm = reactive({
  location_id: null,
  notes: "",
  items: [],
});

async function openReceiveModalFromDetail() {
  if (inboundDetailData.value?.fiscal_status === "CANCELLED" || inboundDetailData.value?.status === "cancelled") {
    toast.add({
      severity: "error",
      summary: "Nota Fiscal Cancelada",
      detail: "Esta nota fiscal foi cancelada na SEFAZ e não pode ser recebida no estoque.",
      life: 6000,
    });
    return;
  }
  if (inboundDetailData.value?.status === "ignored") {
    toast.add({
      severity: "warn",
      summary: "Nota Fiscal Ignorada",
      detail: "Esta nota fiscal está marcada como ignorada. Reative-a antes de dar entrada no estoque.",
      life: 6000,
    });
    return;
  }

  const allItems = inboundDetailData.value?.items || [];
  const items = allItems.filter((it) => !it.is_ignored);
  if (items.length === 0) {
    toast.add({
      severity: "warn",
      summary: "Todos os itens estão ignorados",
      detail: "Não há itens ativos para dar entrada no estoque.",
      life: 6000,
    });
    return;
  }

  const unmapped = items.filter((it) => !it.ingredient && !it.product);
  if (unmapped.length > 0) {
    toast.add({
      severity: "warn",
      summary: "Itens sem vínculo",
      detail: `Existem ${unmapped.length} item(ns) ativos sem produto/ingrediente vinculado. Vincule ou ignore os itens antes de dar entrada no estoque.`,
      life: 6000,
    });
  }

  receiveForm.notes = "";
  receiveForm.items = items.map((it) => {
    const factor = Number(it.conversion_factor) || 1;
    const stockQty = Number((Number(it.commercial_quantity) * factor).toFixed(4));
    let rawStockUnit = it.product_stock_unit || (it.ingredient_unit?.toUpperCase() === "UNIT" ? "UN" : it.ingredient_unit);
    if (factor !== 1 && rawStockUnit && it.commercial_unit && rawStockUnit.toUpperCase().trim() === it.commercial_unit.toUpperCase().trim()) {
      rawStockUnit = "UN";
    }
    const resolvedStockUnit = (
      rawStockUnit ||
      (factor !== 1 ? "UN" : it.commercial_unit) ||
      "UN"
    ).toUpperCase();
    return {
      item_id: it.id,
      description: it.description,
      supplier_code: it.supplier_code,
      target_name: it.product_name ? `Produto: ${it.product_name}` : (it.ingredient_name ? `Ingrediente: ${it.ingredient_name}` : "Não vinculado"),
      tracking_mode: it.product_tracking_mode || "QUANTITY",
      requires_lot: it.product_requires_lot_control || false,
      requires_serial: it.product_requires_serial_number || false,
      commercial_quantity: it.commercial_quantity,
      commercial_unit: it.commercial_unit,
      product_stock_unit: it.product_stock_unit,
      stock_unit: resolvedStockUnit,
      conversion_factor: factor,
      received_quantity: stockQty,
      accepted_quantity: stockQty,
      rejected_quantity: 0,
      lot_number: "",
      expiration_date: "",
      serials_text: "",
    };
  });

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

async function submitReceiveInvoiceFromDetail() {
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
        conversion_factor: it.conversion_factor || 1,
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
    const { data } = await api.post(`/inbound-nfe/${inboundDetailData.value.id}/receive/`, payload);
    toast.add({
      severity: "success",
      summary: "Entrada Concluída!",
      detail: `Conferência ${data.receipt_number || ""} gerada e estoque atualizado com sucesso.`,
      life: 5000,
    });
    receiveDialogVisible.value = false;
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
  } catch (err) {
    toast.add({ severity: "error", summary: "Erro ao dar entrada no estoque", detail: normalizeApiError(err).message, life: 6000 });
  } finally {
    receiveSubmitting.value = false;
  }
}

// ── Consulta Pontual por NSU (consNSU) ────────────────────────────────
const fetchNsuDialogVisible = ref(false);
const fetchNsuInput = ref("");
const fetchingNsu = ref(false);

function openFetchNsuDialog() {
  fetchNsuInput.value = "";
  fetchNsuDialogVisible.value = true;
}

async function submitFetchSpecificNsu() {
  if (!fetchNsuInput.value || !fetchNsuInput.value.trim()) return;
  const scopedRestaurant = inboundRestaurantId.value;
  fetchingNsu.value = true;
  try {
    const { data } = await api.post("/inbound-nfe/fetch-nsu/", {
      nsu: fetchNsuInput.value.trim(),
      restaurant: scopedRestaurant,
    }, { skipRestaurantScope: true });
    toast.add({
      severity: data.summary?.cstat === "138" ? "success" : "info",
      summary: `NSU ${fetchNsuInput.value} consultado`,
      detail: `${data.summary?.reason || "Sucesso"}. Documentos salvos: ${data.summary?.saved_count || 0}.`,
      life: 6000,
    });
    fetchNsuDialogVisible.value = false;
    await reload();
    await loadDfeSyncInfo();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro na consulta consNSU",
      detail: normalizeApiError(err).message,
      life: 6000,
    });
  } finally {
    fetchingNsu.value = false;
  }
}

async function fetchSpecificNsuDirect(nsu) {
  if (!nsu) return;
  const scopedRestaurant = inboundRestaurantId.value;
  fetchingNsu.value = true;
  try {
    const { data } = await api.post("/inbound-nfe/fetch-nsu/", {
      nsu: String(nsu).trim(),
      restaurant: scopedRestaurant,
    }, { skipRestaurantScope: true });
    toast.add({
      severity: data.summary?.cstat === "138" ? "success" : "info",
      summary: `NSU ${Number(nsu)} consultado`,
      detail: `${data.summary?.reason || "Sucesso"}. Documentos salvos: ${data.summary?.saved_count || 0}.`,
      life: 6000,
    });
    await reload();
    await loadDfeSyncInfo();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro na consulta consNSU",
      detail: normalizeApiError(err).message,
      life: 6000,
    });
  } finally {
    fetchingNsu.value = false;
  }
}

function formatNsuDisplay(val) {
  if (!val) return "—";
  const num = Number(val);
  if (isNaN(num)) return val;
  return `#${num.toString().padStart(3, "0")}`;
}

// ── Ciência da Operação (210210) & Busca de XML Completo (consChNFe) ─
const scienceConfirmDialogVisible = ref(false);
const scienceSubmitting = ref(false);
const selectedScienceInvoice = ref(null);

function openScienceConfirmDialog(invoice) {
  selectedScienceInvoice.value = invoice;
  scienceConfirmDialogVisible.value = true;
}

async function confirmAndSendScience() {
  if (!selectedScienceInvoice.value) return;
  scienceSubmitting.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe/${selectedScienceInvoice.value.id}/register-science/`);
    toast.add({
      severity: data.success ? "success" : "warn",
      summary: "Ciência da Operação",
      detail: data.message || "Evento registrado na SEFAZ.",
      life: 8000,
    });
    scienceConfirmDialogVisible.value = false;
    await reload();
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Falha na Manifestação SEFAZ",
      detail: norm.message,
      life: 8000,
    });
  } finally {
    scienceSubmitting.value = false;
  }
}

async function retryFetchFullXmlDirect(invoice) {
  if (!invoice) return;
  toast.add({
    severity: "info",
    summary: "Consultando SEFAZ",
    detail: `Buscando XML completo para a nota nº ${invoice.number || invoice.access_key.slice(-8)}...`,
    life: 4000,
  });
  try {
    const { data } = await api.post(`/inbound-nfe/${invoice.id}/fetch-full-xml/`);
    toast.add({
      severity: data.success ? "success" : "warn",
      summary: "Consulta XML SEFAZ",
      detail: data.message,
      life: 7000,
    });
    await reload();
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Falha na Consulta de XML",
      detail: norm.message,
      life: 7000,
    });
  }
}

// ── Consulta Pontual e Reconciliação de Situação na SEFAZ (consSitNFe) ──
const checkingSefazId = ref(null);
const reconcileLoading = ref(false);

async function checkSefazStatusDirect(invoice) {
  if (!invoice?.id) return;
  checkingSefazId.value = invoice.id;
  try {
    const { data } = await api.post(`/inbound-nfe/${invoice.id}/check-status/`);
    const res = data.result || data;
    const isCancelled = data.fiscal_status === "CANCELLED" || data.status === "cancelled" || res.fiscal_status === "CANCELLED" || res.is_cancelled;
    const isSuccess = data.success ?? res.success;
    const cstat = data.cstat || res.cstat || data.invoice?.last_status_cstat;
    const reason = data.reason || res.reason || data.invoice?.last_status_reason;
    const message = data.message || res.message;

    if (isCancelled) {
      toast.add({
        severity: "warn",
        summary: "NF-e Cancelada na SEFAZ",
        detail: data.cancellation_reason ? `Nota CANCELADA na SEFAZ. Justificativa: ${data.cancellation_reason}` : (message || `A nota fiscal está CANCELADA na SEFAZ (cStat ${cstat || '101'} - ${reason || 'Cancelamento homologado'}).`),
        life: 8000,
      });
    } else if (isSuccess && (cstat === "100" || res.is_authorized)) {
      toast.add({
        severity: "success",
        summary: "Situação SEFAZ",
        detail: `NF-e regular e autorizada na SEFAZ (cStat 100 - ${reason || 'Autorizado o uso da NF-e'}).`,
        life: 5000,
      });
    } else {
      toast.add({
        severity: "info",
        summary: "Situação SEFAZ",
        detail: message || `Retorno SEFAZ: cStat ${cstat || '---'} - ${reason || 'Sem mensagem adicional'}`,
        life: 6000,
      });
    }
    await reload();
    await fetchInboundStatusCounts();
    if (inboundDetailVisible.value && inboundDetailData.value?.id === invoice.id) {
      await openInboundDetail(invoice);
    }
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Falha ao consultar situação na SEFAZ",
      detail: norm.message,
      life: 7000,
    });
  } finally {
    checkingSefazId.value = null;
  }
}

async function reconcileSelectedSefaz() {
  if (!selection.value.length) return;
  reconcileLoading.value = true;
  const nfeIds = selection.value.map((r) => r.id);
  try {
    const { data } = await api.post("/inbound-nfe/reconcile-status/", {
      nfe_ids: nfeIds,
    });
    const { queried = 0, cancelled = 0, authorized = 0, errors = 0 } = data;
    let detailMsg = `${queried} nota(s) consultada(s): ${authorized} autorizada(s)`;
    if (cancelled > 0) {
      detailMsg += `, ${cancelled} cancelada(s) identificada(s)`;
    }
    if (errors > 0) {
      detailMsg += `, ${errors} com erro`;
    }
    toast.add({
      severity: cancelled > 0 ? "warn" : "success",
      summary: "Reconciliação SEFAZ Concluída",
      detail: detailMsg,
      life: 7000,
    });
    selection.value = [];
    await reload();
    await fetchInboundStatusCounts();
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Falha na Reconciliação SEFAZ",
      detail: norm.message,
      life: 7000,
    });
  } finally {
    reconcileLoading.value = false;
  }
}

// ── Cancelamento / Invalidação Manual de NF-e ──────────────────────────
const manualCancelDialogVisible = ref(false);
const manualCancelInvoice = ref(null);
const manualCancelReason = ref("");
const manualCancelLoading = ref(false);

function openManualCancelDialog(invoice) {
  if (!invoice) return;
  manualCancelInvoice.value = invoice;
  manualCancelReason.value = "";
  manualCancelDialogVisible.value = true;
}

async function confirmManualCancel() {
  if (!manualCancelInvoice.value?.id) return;
  const reason = (manualCancelReason.value || "").trim();
  if (!reason) {
    toast.add({
      severity: "warn",
      summary: "Informe a justificativa",
      detail: "Descreva o motivo do cancelamento manual da nota fiscal.",
      life: 5000,
    });
    return;
  }

  manualCancelLoading.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe/${manualCancelInvoice.value.id}/cancel-manual/`, {
      reason,
      protocol: "MANUAL",
    });
    toast.add({
      severity: "success",
      summary: "NF-e Cancelada",
      detail: data.message || "A nota fiscal foi marcada como cancelada e o recebimento de estoque bloqueado.",
      life: 7000,
    });
    manualCancelDialogVisible.value = false;
    await reload();
    await fetchInboundStatusCounts();
    if (inboundDetailVisible.value && inboundDetailData.value?.id === manualCancelInvoice.value.id) {
      await openInboundDetail(manualCancelInvoice.value);
    }
  } catch (err) {
    const norm = normalizeApiError(err);
    toast.add({
      severity: "error",
      summary: "Falha ao cancelar nota fiscal",
      detail: norm.message,
      life: 7000,
    });
  } finally {
    manualCancelLoading.value = false;
  }
}

// ── Ignorar / Reativar Notas Fiscais e Itens ─────────────────────────
const ignoreInvoiceDialogVisible = ref(false);
const ignoreInvoiceTarget = ref(null);
const ignoreInvoiceReason = ref("");
const ignoreInvoiceLoading = ref(false);

const ignoreItemDialogVisible = ref(false);
const ignoreItemTarget = ref(null);
const ignoreItemReason = ref("");
const ignoreItemLoading = ref(false);

const bulkIgnoreDialogVisible = ref(false);
const bulkIgnoreReason = ref("");
const bulkIgnoreLoading = ref(false);

const inboundActionLoading = ref(false);

function openIgnoreInvoiceDialog(invoice) {
  if (!invoice) return;
  ignoreInvoiceTarget.value = invoice;
  ignoreInvoiceReason.value = "";
  ignoreInvoiceDialogVisible.value = true;
}

async function confirmIgnoreInvoice() {
  if (!ignoreInvoiceTarget.value?.id) return;
  ignoreInvoiceLoading.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe/${ignoreInvoiceTarget.value.id}/ignore/`, {
      reason: (ignoreInvoiceReason.value || "").trim(),
    });
    toast.add({
      severity: "info",
      summary: "Nota Fiscal Ignorada",
      detail: data.message || "A nota fiscal foi marcada como ignorada.",
      life: 5000,
    });
    ignoreInvoiceDialogVisible.value = false;
    await reload();
    await fetchInboundStatusCounts();
    if (inboundDetailVisible.value && inboundDetailData.value?.id === ignoreInvoiceTarget.value.id) {
      await openInboundDetail(ignoreInvoiceTarget.value);
    }
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao ignorar nota",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    ignoreInvoiceLoading.value = false;
  }
}

async function unignoreInvoice(invoice) {
  if (!invoice?.id) return;
  inboundActionLoading.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe/${invoice.id}/unignore/`);
    toast.add({
      severity: "success",
      summary: "Nota Fiscal Reativada",
      detail: data.message || "A nota fiscal foi reativada com sucesso.",
      life: 5000,
    });
    await reload();
    await fetchInboundStatusCounts();
    if (inboundDetailVisible.value && inboundDetailData.value?.id === invoice.id) {
      await openInboundDetail(invoice);
    }
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao reativar nota",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    inboundActionLoading.value = false;
  }
}

function openIgnoreItemDialog(item) {
  if (!item) return;
  ignoreItemTarget.value = item;
  ignoreItemReason.value = "";
  ignoreItemDialogVisible.value = true;
}

async function confirmIgnoreItem() {
  if (!ignoreItemTarget.value?.id) return;
  ignoreItemLoading.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe-items/${ignoreItemTarget.value.id}/ignore/`, {
      reason: (ignoreItemReason.value || "").trim(),
    });
    toast.add({
      severity: "info",
      summary: "Item Ignorado",
      detail: data.message || "O item foi ignorado e não dará entrada no estoque.",
      life: 5000,
    });
    ignoreItemDialogVisible.value = false;
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
    await fetchInboundStatusCounts();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao ignorar item",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    ignoreItemLoading.value = false;
  }
}

async function unignoreItem(item) {
  if (!item?.id) return;
  inboundActionLoading.value = true;
  try {
    const { data } = await api.post(`/inbound-nfe-items/${item.id}/unignore/`);
    toast.add({
      severity: "success",
      summary: "Item Reativado",
      detail: data.message || "O item foi reativado para dar entrada no estoque.",
      life: 5000,
    });
    if (inboundDetailData.value?.id) {
      await openInboundDetail(inboundDetailData.value);
    }
    await reload();
    await fetchInboundStatusCounts();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao reativar item",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    inboundActionLoading.value = false;
  }
}

function openBulkIgnoreDialog() {
  if (!selection.value.length) return;
  bulkIgnoreReason.value = "";
  bulkIgnoreDialogVisible.value = true;
}

async function confirmBulkIgnore() {
  if (!selection.value.length) return;
  bulkIgnoreLoading.value = true;
  try {
    const ids = selection.value.map((r) => r.id);
    const { data } = await api.post("/inbound-nfe/bulk-ignore/", {
      ids,
      reason: (bulkIgnoreReason.value || "").trim() || "Ignorado em lote pelo usuário",
    });
    toast.add({
      severity: "info",
      summary: "Notas Ignoradas",
      detail: `${data.updated_count || ids.length} nota(s) ignorada(s) com sucesso.`,
      life: 5000,
    });
    bulkIgnoreDialogVisible.value = false;
    selection.value = [];
    await reload();
    await fetchInboundStatusCounts();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao ignorar notas em lote",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    bulkIgnoreLoading.value = false;
  }
}

// ── Upload e Importação Manual de XML / ZIP ──────────────────────────
const uploadXmlDialogVisible = ref(false);
const selectedXmlFiles = ref([]);
const uploadingXml = ref(false);
const isDraggingFiles = ref(false);
const uploadXmlResult = ref(null);

function openUploadXmlDialog() {
  selectedXmlFiles.value = [];
  uploadXmlResult.value = null;
  uploadXmlDialogVisible.value = true;
}

function onXmlFilesSelected(event) {
  const files = Array.from(event.target.files || []);
  if (files.length) {
    selectedXmlFiles.value = [...selectedXmlFiles.value, ...files];
  }
}

function onFilesDropped(event) {
  isDraggingFiles.value = false;
  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length) {
    selectedXmlFiles.value = [...selectedXmlFiles.value, ...files];
  }
}

async function submitUploadXmlFiles() {
  if (!selectedXmlFiles.value.length) return;
  const scopedRestaurant = inboundRestaurantId.value;
  uploadingXml.value = true;
  uploadXmlResult.value = null;

  try {
    const formData = new FormData();
    for (const f of selectedXmlFiles.value) {
      formData.append("files", f);
    }
    if (scopedRestaurant) {
      formData.append("restaurant", scopedRestaurant);
    }

    const { data } = await api.post("/inbound-nfe/upload-xml/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      skipRestaurantScope: true,
    });

    uploadXmlResult.value = data;
    toast.add({
      severity: "success",
      summary: "Importação Concluída",
      detail: data.message || "Arquivos XML processados com sucesso.",
      life: 6000,
    });
    await reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro na importação de XML",
      detail: normalizeApiError(err).message,
      life: 6000,
    });
  } finally {
    uploadingXml.value = false;
  }
}

// ── Ações em massa (config `pro.bulkActions`) ─────────────────────────
const hasActiveField = computed(() => props.formFields.some((field) => field.name === "is_active"));
const bulkActions = computed(() => {
  const actions = [...(proCfg.value.bulkActions || [])];
  if (props.formEnabled && hasActiveField.value) {
    actions.push(
      { key: "activate", label: "Ativar", icon: "pi pi-check", type: "patch", payload: { is_active: true } },
      { key: "deactivate", label: "Desativar", icon: "pi pi-ban", type: "patch", payload: { is_active: false } },
    );
  }
  if (props.formEnabled) actions.push({ key: "delete", label: "Excluir", icon: "pi pi-trash", type: "delete" });
  return actions;
});
function runBulkAction(bulkAction) {
  if (bulkAction.type === "print-codes") openLabels();
  else if (bulkAction.type === "asset-bulk-status") openAssetBulkStatus();
  else if (bulkAction.type === "asset-bulk-location") openAssetBulkLocation();
  else if (bulkAction.type === "patch") executeBulkMutation(bulkAction);
  else if (bulkAction.type === "delete") {
    confirm.require({
      message: `Excluir ${selection.value.length} itens selecionados?`,
      header: "Confirmar exclusão em massa",
      icon: "pi pi-exclamation-triangle",
      acceptLabel: "Excluir",
      rejectLabel: "Cancelar",
      accept: () => executeBulkMutation(bulkAction),
    });
  }
}

function setAdvancedFilter({ name, value }) {
  advancedFilters[name] = value;
}

function onInvoiceBulkCompleted() {
  selection.value = [];
  reload();
}

async function executeBulkMutation(action) {
  const selected = [...selection.value];
  if (!selected.length) return;
  exchangeLoading.value = true;
  let success = 0;
  if (action.type === "patch" && proCfg.value.bulkUpdateEndpoint) {
    try {
      const { data } = await api.post(proCfg.value.bulkUpdateEndpoint, {
        ids: selected.map((row) => row.id),
        changes: action.payload,
      });
      success = data.updated || 0;
    } catch (error) {
      toast.add({ severity: "error", summary: "Não foi possível atualizar em lote", detail: normalizeApiError(error).message, life: 5000 });
    }
    selection.value = [];
    exchangeLoading.value = false;
    if (success) toast.add({ severity: "success", summary: `${success} itens atualizados`, life: 4000 });
    reload();
    return;
  }
  if (action.type === "delete" && proCfg.value.bulkDeleteEndpoint) {
    try {
      const { data } = await api.post(proCfg.value.bulkDeleteEndpoint, { ids: selected.map((row) => row.id) });
      success = data.deleted || 0;
    } catch (error) {
      toast.add({ severity: "error", summary: "Não foi possível excluir as comandas", detail: normalizeApiError(error).message, life: 5000 });
    }
    selection.value = [];
    exchangeLoading.value = false;
    if (success) toast.add({ severity: "success", summary: `${success} comandas excluídas`, life: 4000 });
    reload();
    return;
  }
  for (let index = 0; index < selected.length; index += 10) {
    const batch = selected.slice(index, index + 10);
    const results = await Promise.allSettled(batch.map((row) =>
      action.type === "delete" ? service.remove(row.id) : service.update(row.id, action.payload),
    ));
    success += results.filter((result) => result.status === "fulfilled").length;
  }
  selection.value = [];
  exchangeLoading.value = false;
  toast.add({
    severity: success === selected.length ? "success" : "warn",
    summary: `${success} de ${selected.length} itens processados`,
    life: 4000,
  });
  reload();
}

// Duplo clique no checkbox do CABEÇALHO → seleciona TODOS os itens do filtro
// atual (todas as páginas), não só os da página visível.
const selectingAll = ref(false);
function onTableDblClick(event) {
  const target = event.target;
  if (!target || selectingAll.value) return;
  if (target.closest(".p-datatable-thead") && target.closest(".p-checkbox")) {
    selectAllMatching();
  }
}
async function selectAllMatching() {
  selectingAll.value = true;
  try {
    const baseParams = { ...props.defaultParams, ...buildProParams() };
    if (search.value) baseParams.search = search.value;
    if (ordering.value) baseParams.ordering = ordering.value;
    const all = [];
    let pageNum = 1;
    // Backend limita page_size a 100 → pagina até cobrir o total.
    for (;;) {
      const data = await service.list({ ...baseParams, page: pageNum, page_size: 100 });
      const results = data.results || data || [];
      all.push(...results);
      const count = data.count ?? all.length;
      if (all.length >= count || results.length === 0) break;
      pageNum += 1;
      if (pageNum > 200) break; // trava de segurança (20k itens)
    }
    selection.value = all;
    toast.add({
      severity: "success",
      summary: `${all.length} ${all.length === 1 ? "item selecionado" : "itens selecionados"}`,
      detail: "Todos os itens do filtro atual (todas as páginas).",
      life: 3000,
    });
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível selecionar todos", detail: normalizeApiError(error).message, life: 4000 });
  } finally {
    selectingAll.value = false;
  }
}

// Impressão em lote das etiquetas (QR ou código de barras) dos selecionados.
async function fetchAllMatching() {
  const params = { ...props.defaultParams, ...buildProParams() };
  if (search.value) params.search = search.value;
  if (ordering.value) params.ordering = ordering.value;
  const all = [];
  for (let pageNumber = 1; pageNumber <= 100; pageNumber += 1) {
    const data = await service.list({ ...params, page: pageNumber, page_size: 100 });
    const results = data.results || data || [];
    all.push(...results);
    if (all.length >= (data.count ?? all.length) || !results.length) return all;
  }
  throw new Error("O limite de exportação é de 10.000 registros.");
}

const exchangeFields = computed(() => (props.formFields || [])
  .filter((field) => !["password", "json"].includes(field.type))
  .map((field) => ({ ...field, key: field.name })));
const exportColumns = computed(() => (
  exchangeFields.value.length ? exchangeFields.value : visibleColumns.value
).map((field) => ({ key: field.key, label: field.label })));
const importFieldLabels = computed(() => exchangeFields.value.map((field) => field.label).join(", "));

async function exportRows() {
  exchangeLoading.value = true;
  try {
    const exportableRows = selection.value.length ? selection.value : await fetchAllMatching();
    const filename = `${String(route.name || "dados").replaceAll("/", "-")}.csv`;
    await dataExchangeService.exportCsv({ filename, columns: exportColumns.value, rows: exportableRows });
    toast.add({ severity: "success", summary: `${exportableRows.length} itens exportados`, life: 3000 });
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível exportar", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    exchangeLoading.value = false;
  }
}

const exportInboundLoading = ref(false);
const isExportingAll = ref(false);

async function exportInboundXml(exportAll = false) {
  if (!exportAll && !selection.value.length) {
    toast.add({
      severity: "warn",
      summary: "Nenhuma nota selecionada",
      detail: "Selecione as notas desejadas nas caixas de seleção da tabela ou use o botão 'Exportar Tudo (XML)'.",
      life: 5000,
    });
    return;
  }

  exportInboundLoading.value = true;
  isExportingAll.value = exportAll;

  try {
    const payload = exportAll
      ? { all: true, ...props.defaultParams, ...buildProParams() }
      : { ids: selection.value.map((item) => item.id) };

    const response = await api.post("/inbound-nfe/export-xml/", payload, {
      responseType: "blob",
    });

    let filename = exportAll || selection.value.length > 1 ? "notas_fiscais_xml.zip" : "nota_fiscal.xml";
    const disposition = response.headers?.["content-disposition"] || "";
    const filenameMatch = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (filenameMatch && filenameMatch[1]) {
      filename = filenameMatch[1].replace(/['"]/g, "").trim();
    }

    const blob = new Blob([response.data], {
      type: response.headers?.["content-type"] || "application/octet-stream",
    });
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);

    const countDesc = exportAll ? "Todas as notas fiscais filtradas" : `${selection.value.length} nota(s) selecionada(s)`;
    toast.add({
      severity: "success",
      summary: "Exportação em XML concluída",
      detail: `${countDesc} foram exportadas com sucesso (${filename}).`,
      life: 5000,
    });
  } catch (error) {
    let msg = normalizeApiError(error).message;
    if (error?.response?.data instanceof Blob) {
      try {
        const parsed = JSON.parse(await error.response.data.text());
        msg = parsed.error || parsed.detail || msg;
      } catch {
        // Ignora erro de parse e mantém msg padronizada se o blob não for JSON
      }
    }
    toast.add({
      severity: "error",
      summary: "Não foi possível exportar os XMLs",
      detail: msg,
      life: 6000,
    });
  } finally {
    exportInboundLoading.value = false;
    isExportingAll.value = false;
  }
}

function onImportFile(event) {
  [importFile.value] = event.target.files || [];
}

function castImportedValue(value, field) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  if (field.type === "number") return Number.parseInt(text, 10);
  if (field.type === "decimal") return Number(text.replace(",", "."));
  if (field.type === "boolean") return ["1", "true", "sim", "yes"].includes(text.toLowerCase());
  if (field.type === "remote-multiselect") return text.split("|").map((item) => item.trim()).filter(Boolean);
  if (field.options?.length) {
    const option = field.options.find((item) =>
      String(item.value) === text || String(item.label).toLowerCase() === text.toLowerCase());
    return option ? option.value : text;
  }
  return text;
}

async function importRows() {
  if (!importFile.value) return;
  exchangeLoading.value = true;
  try {
    const parsed = await dataExchangeService.parseCsv(importFile.value);
    const fieldByHeader = new Map();
    for (const field of exchangeFields.value) {
      fieldByHeader.set(field.name.toLowerCase(), field);
      fieldByHeader.set(String(field.label).toLowerCase(), field);
    }
    const payloads = parsed.rows.map((row) => Object.fromEntries(
      Object.entries(row)
        .map(([header, value]) => [fieldByHeader.get(header.trim().toLowerCase()), value])
        .filter(([field, value]) => field && String(value ?? "").trim() !== "")
        .map(([field, value]) => [field.name, castImportedValue(value, field)]),
    )).filter((payload) => Object.keys(payload).length);

    let imported = 0;
    const errors = [];
    for (const payload of payloads) {
      try {
        await service.create(payload);
        imported += 1;
      } catch (error) {
        errors.push(normalizeApiError(error).message);
      }
    }
    toast.add({
      severity: errors.length ? "warn" : "success",
      summary: `${imported} de ${payloads.length} itens importados`,
      detail: errors[0] || undefined,
      life: 5000,
    });
    if (!errors.length) {
      importVisible.value = false;
      importFile.value = null;
    }
    reload();
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível importar", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    exchangeLoading.value = false;
  }
}

const labelsVisible = ref(false);
const labelsLoading = ref(false);
const labelKind = ref("qr");
const labelLayout = ref("sheet"); // "sheet" (vários/folha, flui p/ próxima) | "single" (um por página)
const labelCutlines = ref(true); // linhas de corte pontilhadas
function openLabels() {
  if (!selection.value.length) return;
  labelKind.value = "qr";
  labelsVisible.value = true;
}
async function printLabels() {
  if (!selection.value.length) return;
  labelsLoading.value = true;
  try {
    const ids = selection.value.map((row) => row.id);
    const { data } = await api.post(`${props.endpoint}codes-batch/`, { ids, kind: labelKind.value });
    renderLabelsSheet(data.items || [], data.kind, { layout: labelLayout.value, cutlines: labelCutlines.value });
    labelsVisible.value = false;
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível gerar as etiquetas", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    labelsLoading.value = false;
  }
}
function renderLabelsSheet(items, kind, { layout = "sheet", cutlines = true } = {}) {
  const win = window.open("", "_blank", "width=820,height=920");
  if (!win) {
    toast.add({ severity: "warn", summary: "Permita pop-ups", detail: "Libere pop-ups para imprimir as etiquetas.", life: 4000 });
    return;
  }
  const single = layout === "single";
  // Um por página → código maior; vários por folha → tamanho compacto.
  const imgHeight = single ? (kind === "barcode" ? "120px" : "300px") : kind === "barcode" ? "48px" : "112px";
  const border = cutlines ? "1px dashed #999" : "none";

  const cards = items
    .map(
      (it) => `<div class="lbl">
        <div class="lbl-n">${it.number}</div>
        ${it.uri ? `<img class="lbl-img" src="${it.uri}"/>` : `<div class="lbl-empty">sem código</div>`}
        <div class="lbl-c">${it.code || ""}</div>
      </div>`,
    )
    .join("");

  // sheet: grade que flui para a próxima página quando não cabe (page-break-inside
  // evita cortar uma etiqueta ao meio). single: cada etiqueta ocupa uma página.
  const layoutCss = single
    ? `.sheet{display:block}
       .lbl{min-height:calc(100vh - 24px);display:flex;flex-direction:column;align-items:center;justify-content:center;page-break-after:always}
       .lbl:last-child{page-break-after:auto}
       .lbl-n{font-size:40px}
       .lbl-c{font-size:16px}`
    : `.sheet{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
       .lbl{page-break-inside:avoid}
       .lbl-n{font-size:18px}
       .lbl-c{font-size:11px}`;

  win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Etiquetas</title>
    <style>
      *{box-sizing:border-box}
      body{font-family:system-ui,sans-serif;margin:12px}
      .lbl{border:${border};border-radius:8px;padding:10px 8px;text-align:center}
      .lbl-n{font-weight:800;line-height:1.1}
      .lbl-img{max-width:100%;height:${imgHeight};object-fit:contain;margin:6px 0}
      .lbl-empty{color:#999;font-size:12px;margin:14px 0}
      .lbl-c{font-family:ui-monospace,monospace;color:#555;letter-spacing:1px}
      ${layoutCss}
      @media print{@page{margin:8mm}}
    </style></head><body>
    <div class="sheet">${cards}</div>
    <script>window.onload=function(){window.focus();window.print();}\x3C/script>
    </body></html>`);
  win.document.close();
}

// ── Ações em lote para Patrimônio e Equipamentos (Status e Local de Estoque) ──
const assetBulkStatusVisible = ref(false);
const assetBulkStatusLoading = ref(false);
const assetBulkStatusTarget = ref("IN_USE");

function openAssetBulkStatus() {
  if (!selection.value.length) return;
  assetBulkStatusTarget.value = "IN_USE";
  assetBulkStatusVisible.value = true;
}

async function submitAssetBulkStatus() {
  if (!selection.value.length) return;
  assetBulkStatusLoading.value = true;
  try {
    const ids = selection.value.map((r) => r.id);
    const { data } = await api.post("/assets/bulk-update-status/", {
      ids,
      status: assetBulkStatusTarget.value,
    });
    const statusObj = ASSET_STATUS_OPTIONS.find((opt) => opt.value === assetBulkStatusTarget.value);
    const statusLabel = statusObj ? statusObj.label : assetBulkStatusTarget.value;
    toast.add({
      severity: "success",
      summary: "Status atualizado em lote",
      detail: `${data.updated || ids.length} ativo(s) alterado(s) para "${statusLabel}".`,
      life: 4000,
    });
    selection.value = [];
    assetBulkStatusVisible.value = false;
    reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Não foi possível alterar status",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    assetBulkStatusLoading.value = false;
  }
}

const assetBulkLocationVisible = ref(false);
const assetBulkLocationLoading = ref(false);
const assetBulkLocationsLoading = ref(false);
const assetBulkLocationTarget = ref(null);
const assetBulkLocationReason = ref("Transferência em lote");
const assetStockLocations = ref([]);

async function openAssetBulkLocation() {
  if (!selection.value.length) return;
  assetBulkLocationTarget.value = null;
  assetBulkLocationReason.value = "Transferência em lote";
  assetBulkLocationVisible.value = true;
  assetBulkLocationsLoading.value = true;
  try {
    const { data } = await api.get("/stock/locations/", { params: { page_size: 100 } });
    assetStockLocations.value = data.results || data || [];
    if (assetStockLocations.value.length && !assetBulkLocationTarget.value) {
      assetBulkLocationTarget.value = assetStockLocations.value[0].id;
    }
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Erro ao carregar locais de estoque",
      detail: normalizeApiError(err).message,
      life: 4000,
    });
  } finally {
    assetBulkLocationsLoading.value = false;
  }
}

async function submitAssetBulkLocation() {
  if (!selection.value.length) return;
  if (!assetBulkLocationTarget.value) {
    toast.add({
      severity: "warn",
      summary: "Selecione o local de destino",
      life: 3000,
    });
    return;
  }
  assetBulkLocationLoading.value = true;
  try {
    const ids = selection.value.map((r) => r.id);
    const { data } = await api.post("/assets/bulk-transfer/", {
      ids,
      to_location: assetBulkLocationTarget.value,
      reason: assetBulkLocationReason.value,
    });
    const targetLocationName = data.to_location?.name || "novo local";
    toast.add({
      severity: "success",
      summary: "Local de estoque atualizado",
      detail: `${data.transferred || ids.length} ativo(s) movido(s) para "${targetLocationName}".`,
      life: 4000,
    });
    selection.value = [];
    assetBulkLocationVisible.value = false;
    reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Não foi possível mover os ativos",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    assetBulkLocationLoading.value = false;
  }
}

// ── Diálogo "Criar em lote" (comandas e mesas) ────────────────────────────────
const bulkVisible = ref(false);
const bulkSubmitting = ref(false);
const bulkType = ref("commands");
const bulkRestaurants = ref([]);
const bulkSectors = ref([]);
const bulkRestaurantsLoading = ref(false);
const bulkSectorsLoading = ref(false);
const bulkForm = ref(createBulkForm());
let bulkSectorRequestId = 0;

async function loadBulkSectors(restaurantId) {
  const requestId = ++bulkSectorRequestId;
  bulkSectors.value = [];
  bulkForm.value.sector_id = null;
  if (!restaurantId) {
    bulkSectorsLoading.value = false;
    return;
  }

  bulkSectorsLoading.value = true;
  try {
    const { data } = await api.get("/tables/sectors/", {
      params: { restaurant: restaurantId, is_active: true, page_size: 200 },
      // O restaurante é informado explicitamente acima. Isso também funciona
      // quando o seletor global está em "Todos".
      skipRestaurantScope: true,
    });
    if (requestId === bulkSectorRequestId && bulkForm.value.restaurant_id === restaurantId) {
      bulkSectors.value = data.results || data || [];
    }
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar os setores", detail: normalizeApiError(error).message, life: 4000 });
  } finally {
    if (requestId === bulkSectorRequestId) bulkSectorsLoading.value = false;
  }
}

function onBulkRestaurantChange() {
  if (bulkType.value === "tables") return loadBulkSectors(bulkForm.value.restaurant_id);
}

async function openBulk(type) {
  bulkType.value = type || "commands";
  bulkRestaurants.value = [];
  bulkSectors.value = [];
  const scopedRestaurant = getBrowserValue("starchef-restaurant-scope") || null;
  // Se o topo já tem uma unidade, ela vem pré-selecionada. Em "Todos", o
  // restaurante fica obrigatório e explícito para mesas e comandas.
  bulkForm.value = createBulkForm(scopedRestaurant);
  bulkVisible.value = true;
  bulkRestaurantsLoading.value = true;
  try {
    const { data } = await api.get("/restaurants/", {
      params: { is_active: true, page_size: 200 },
      skipRestaurantScope: true,
    });
    bulkRestaurants.value = data.results || data || [];
    if (bulkType.value === "tables" && scopedRestaurant) {
      await loadBulkSectors(scopedRestaurant);
    }
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar os restaurantes", detail: normalizeApiError(error).message, life: 4000 });
  } finally {
    bulkRestaurantsLoading.value = false;
  }
}

async function submitBulk() {
  const { from_number, to_number } = bulkForm.value;
  const missingScope = missingBulkScope(bulkType.value, bulkForm.value);
  if (missingScope === "restaurant") {
    toast.add({ severity: "warn", summary: "Selecione o restaurante", life: 3000 });
    return;
  }
  if (missingScope === "sector") {
    toast.add({ severity: "warn", summary: "Selecione o setor", life: 3000 });
    return;
  }
  if (!to_number || to_number < 1) {
    toast.add({ severity: "warn", summary: "Informe o número final", life: 3000 });
    return;
  }
  const start = Number(from_number || 1);
  const maxLimit = bulkType.value === "commands" ? 200 : 100;
  if (Number(to_number) - start + 1 > maxLimit) {
    toast.add({ severity: "warn", summary: `Limite de ${maxLimit} registros por lote`, life: 4000 });
    return;
  }
  bulkSubmitting.value = true;
  try {
    const payload = buildBulkPayload(bulkType.value, bulkForm.value);
    const { data } = await api.post(`${props.endpoint}bulk-create/`, payload);
    toast.add({
      severity: "success",
      summary: bulkType.value === "commands" ? "Comandas criadas" : "Mesas criadas",
      detail: `${data.created} criadas${data.skipped ? `, ${data.skipped} já existiam` : ""}.`,
      life: 4000,
    });
    bulkVisible.value = false;
    reload();
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível criar em lote", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    bulkSubmitting.value = false;
  }
}

/* ── Menu de ações da linha (3 pontinhos) ──────────────────────────── */
const rowMenu = ref(null);
const menuRow = ref(null);
const rowMenuItems = computed(() => {
  const items = [{ label: "Ver detalhe", icon: "pi pi-eye", command: () => openDetail(menuRow.value) }];
  // Ações extras declaradas no config (`pro.rowActions`) — ex.: "Ver códigos",
  // "Configuração fiscal". `module` esconde a ação em contas sem o módulo.
  if (props.endpoint === "/inbound-nfe/") {
    const row = menuRow.value;
    if (row) {
      items.push({
        label: "Verificar Situação SEFAZ",
        icon: "pi pi-shield",
        command: () => checkSefazStatusDirect(row),
      });
      if (row.status === "ignored") {
        items.push({
          label: "Reativar Nota Fiscal",
          icon: "pi pi-undo",
          command: () => unignoreInvoice(row),
        });
      } else if (row.status !== "received" && row.fiscal_status !== "CANCELLED" && row.status !== "cancelled") {
        items.push({
          label: "Ignorar Nota Fiscal",
          icon: "pi pi-eye-slash",
          command: () => openIgnoreInvoiceDialog(row),
        });
      }
      if (row.fiscal_status !== "CANCELLED" && row.status !== "cancelled") {
        items.push({
          label: "Marcar como Cancelada / Substituída",
          icon: "pi pi-ban",
          class: "rpro-menu-danger",
          command: () => openManualCancelDialog(row),
        });
        if ((row.status === "summary" || row.xml_status === "summary_only" || (!row.items_count && row.xml_status !== "full_xml_available")) && row.manifestation_status !== "science_registered" && row.manifestation_status !== "confirmed") {
          items.push({
            label: "Dar ciência e obter XML",
            icon: "pi pi-bolt",
            command: () => openScienceConfirmDialog(row),
          });
        }
        if ((row.manifestation_status === "science_registered" || row.manifestation_status === "confirmed") && row.xml_status !== "full_xml_available") {
          items.push({
            label: "Buscar XML Completo (SEFAZ)",
            icon: "pi pi-cloud-download",
            command: () => retryFetchFullXmlDirect(row),
          });
        }
        if (row.nsu) {
          items.push({
            label: `Buscar XML Completo (NSU ${Number(row.nsu)})`,
            icon: "pi pi-search",
            command: () => fetchSpecificNsuDirect(row.nsu),
          });
        }
      }
    }
  }
  if (props.endpoint === "/assets/reusables/") {
    const row = menuRow.value;
    if (row) {
      items.push({
        label: "Registrar Quebra / Baixa",
        icon: "pi pi-minus-circle",
        command: () => openReusableLossDialog(row),
      });
      items.push({
        label: "Histórico de Movimentações",
        icon: "pi pi-history",
        command: () => openReusableHistoryDialog(row),
      });
      items.push({ separator: true });
    }
  }
  // Ações extras declaradas no config (`pro.rowActions`) — ex.: "Ver códigos".
  for (const rowAction of proCfg.value.rowActions || []) {
    if (!auth.hasModule(rowAction.module) || !auth.hasPermission(rowAction.permission)) continue;
    if (rowAction.visible && !rowAction.visible(menuRow.value)) continue;
    items.push({ label: rowAction.label, icon: rowAction.icon, command: () => runRowAction(rowAction, menuRow.value) });
  }
  if (props.formEnabled) {
    items.push({ label: "Editar", icon: "pi pi-pencil", command: () => goToEdit(menuRow.value) });
    items.push({ separator: true });
    items.push({ label: "Remover", icon: "pi pi-trash", class: "rpro-menu-danger", command: () => confirmDelete(menuRow.value) });
  }
  return items;
});

// ── Diálogo "Ver códigos" (QR + código de barras) ─────────────────────
const codesVisible = ref(false);
const codesLoading = ref(false);
const codesData = ref(null);
const codesTitle = ref("");

// ── Diálogo "Versões" (histórico + restaurar) ──────────────────────────
// Genérico: qualquer recurso pode declarar `rowActions: [{ type: "versions" }]`
// desde que a API exponha `{endpoint}{id}/versions/` (GET, lista) e
// `{endpoint}{id}/versions/{versionId}/restore/` (POST) — hoje só as páginas
// do storefront usam, mas nada aqui é específico delas.
const versionsVisible = ref(false);
const versionsLoading = ref(false);
const versionsData = ref([]);
const versionsRow = ref(null);
const versionsRowAction = ref(null);
const restoringVersionId = ref("");

async function openVersions(rowAction, row) {
  versionsRowAction.value = rowAction;
  versionsRow.value = row;
  versionsData.value = [];
  versionsVisible.value = true;
  versionsLoading.value = true;
  try {
    const data = await service.detailAction(row.id, "versions");
    versionsData.value = data.results || data || [];
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar as versões", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    versionsLoading.value = false;
  }
}

async function restoreVersion(version, { publish = false } = {}) {
  if (!versionsRow.value?.id) return;
  restoringVersionId.value = version.id;
  try {
    await api.post(`${props.endpoint}${versionsRow.value.id}/versions/${version.id}/restore/`, { publish });
    toast.add({
      severity: "success",
      summary: publish ? "Versão restaurada e publicada" : "Versão restaurada no rascunho",
      detail: `Versão v${version.number} de ${formatDateTime(version.created_at)}.`,
      life: 4500,
    });
    versionsVisible.value = false;
    await reload();
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível restaurar esta versão", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    restoringVersionId.value = "";
  }
}

// ── Diálogo "Itens resolvidos" ──────────────────────────────────────────
// Genérico: qualquer recurso cujo detalhe exponha uma sub-rota que devolva
// `{ items: [...] }` pode declarar `rowActions: [{ type: "resolved" }]`. Hoje
// serve aos menus, cujo conteúdo pode vir de uma consulta (mais vendidos, todas
// as categorias) — e nesse caso não há item cadastrado para olhar no formulário.
const resolvedVisible = ref(false);
const resolvedLoading = ref(false);
const resolvedData = ref(null);
const resolvedTitle = ref("");

async function openResolved(rowAction, row) {
  resolvedTitle.value = rowLabel(row);
  resolvedData.value = null;
  resolvedVisible.value = true;
  resolvedLoading.value = true;
  try {
    resolvedData.value = await service.detailAction(row.id, rowAction.endpointSuffix || "resolved");
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar os itens", detail: normalizeApiError(error).message, life: 5000 });
    resolvedVisible.value = false;
  } finally {
    resolvedLoading.value = false;
  }
}

// ── Diálogo "Aplicar modelo" ────────────────────────────────────────────
// Também genérico: `rowActions: [{ type: "apply-template", templatesEndpoint }]`.
// Busca os modelos de outro endpoint (o catálogo é um recurso à parte) e
// aplica em `{endpoint}{id}/apply-template/{templateId}/`.
const templateVisible = ref(false);
const templateLoading = ref(false);
const templateOptions = ref([]);
const templateSelected = ref("");
const templateRow = ref(null);
const templateRowAction = ref(null);
const applyingTemplate = ref(false);

async function openApplyTemplate(rowAction, row) {
  templateRowAction.value = rowAction;
  templateRow.value = row;
  templateSelected.value = "";
  templateVisible.value = true;
  templateLoading.value = true;
  try {
    const { data } = await api.get(rowAction.templatesEndpoint);
    templateOptions.value = (data.results || data || []).map((template) => ({
      label: template.name,
      value: template.id,
      description: template.description,
    }));
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar os modelos", detail: normalizeApiError(error).message, life: 5000 });
  } finally {
    templateLoading.value = false;
  }
}

const templateSelectedDescription = computed(
  () => templateOptions.value.find((option) => option.value === templateSelected.value)?.description || "",
);

async function confirmApplyTemplate() {
  if (!templateRow.value?.id || !templateSelected.value) return;
  applyingTemplate.value = true;
  try {
    await api.post(`${props.endpoint}${templateRow.value.id}/apply-template/${templateSelected.value}/`);
    toast.add({ severity: "success", summary: "Modelo aplicado ao rascunho", life: 4000 });
    templateVisible.value = false;
    await reload();
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível aplicar o modelo", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    applyingTemplate.value = false;
  }
}

async function runRowAction(rowAction, row) {
  if (rowAction.type === "codes") return openCodes(row);
  // Duplicar: abre a tela de NOVO documento pedindo a copia deste registro.
  if (rowAction.type === "duplicate" && row?.id) {
    return router.push({ name: rowAction.routeName, query: { copy: row.id } });
  }
  // Ação que só leva pra outra página do registro (ex.: configuração fiscal).
  if (rowAction.type === "route" && row?.id) {
    return router.push({ name: rowAction.routeName, params: { id: row.id } });
  }
  // Link externo (ex.: abrir o editor visual do storefront, outra aplicação).
  if (rowAction.type === "external" && row?.id) {
    const href = rowAction.href?.(row);
    if (href) window.open(href, "_blank", "noopener");
    return;
  }
  if (rowAction.type === "versions" && row?.id) return openVersions(rowAction, row);
  if (rowAction.type === "resolved" && row?.id) return openResolved(rowAction, row);
  if (rowAction.type === "apply-template" && row?.id) return openApplyTemplate(rowAction, row);
  // Ação genérica: POST numa sub-rota de detalhe (`{endpoint}{id}/{action}/`),
  // com confirmação antes e toast depois. O rótulo/mensagem de sucesso e o
  // payload são declarados no recurso (`rowAction.*`); os defaults abaixo
  // preservam o comportamento original (pensado para o reenvio de notas fiscais).
  if (rowAction.type === "post-detail" && row?.id) {
    confirm.require({
      header: rowAction.label,
      message: rowAction.confirmMessage || `Executar esta ação em "${rowLabel(row)}"?`,
      icon: "pi pi-exclamation-triangle",
      acceptLabel: rowAction.confirmAcceptLabel || "Confirmar",
      rejectLabel: "Cancelar",
      accept: async () => {
        try {
          const { data } = await api.post(`${props.endpoint}${row.id}/${rowAction.action}/`, rowAction.payload || {});
          const summary = rowAction.successSummary ? rowAction.successSummary(data, row) : "Ação concluída";
          const detail = rowAction.successDetail ? rowAction.successDetail(data, row) : "";
          toast.add({ severity: rowAction.successSeverity?.(data) || "success", summary, detail, life: 4500 });
          await reload();
        } catch (error) {
          toast.add({
            severity: "error",
            summary: rowAction.errorSummary || "Não foi possível concluir a ação",
            detail: normalizeApiError(error).message,
            life: 7000,
          });
          await reload();
        }
      },
    });
  }
}

async function openCodes(row) {
  codesTitle.value = row?.number ? `#${row.number}` : rowLabel(row);
  codesData.value = null;
  codesVisible.value = true;
  codesLoading.value = true;
  try {
    codesData.value = await service.detailAction(row.id, "codes");
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível carregar os códigos", detail: normalizeApiError(error).message, life: 4000 });
    codesVisible.value = false;
  } finally {
    codesLoading.value = false;
  }
}

function printCodes() {
  const win = window.open("", "_blank", "width=420,height=560");
  if (!win || !codesData.value) return;
  const { qr_uri, barcode_uri, code } = codesData.value;
  win.document.write(`<!doctype html><title>${codesTitle.value}</title>
    <div style="font-family:sans-serif;text-align:center;padding:24px">
      <h2 style="margin:0 0 4px">${codesTitle.value}</h2>
      <div style="color:#666;margin-bottom:16px">${code || ""}</div>
      ${barcode_uri ? `<img src="${barcode_uri}" style="max-width:100%"/>` : ""}
      <div style="height:16px"></div>
      ${qr_uri ? `<img src="${qr_uri}" width="180" height="180"/>` : ""}
    </div>`);
  win.document.close();
  win.focus();
  win.print();
}
function openRowMenu(event, row) {
  menuRow.value = row;
  rowMenu.value.toggle(event);
}
function goToEdit(row) {
  if (row?.id) router.push({ name: `${route.name}--edit`, params: { id: row.id } });
}
function rowLabel(row) {
  return row.name || row.trade_name || row.username || row.number || `#${row.id}`;
}
function confirmDelete(row) {
  if (!row?.id) return;
  confirm.require({
    header: "Excluir registro?",
    message: `Tem certeza que deseja excluir "${rowLabel(row)}"? Esta ação não pode ser desfeita.`,
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Excluir",
    rejectLabel: "Cancelar",
    acceptClass: "p-button-danger",
    accept: () => removeRow(row),
  });
}
async function removeRow(row) {
  try {
    await service.remove(row.id);
    toast.add({ severity: "success", summary: "Registro excluído", life: 2500 });
    // Se a página ficou vazia após excluir, recua uma página.
    if (rows.value.length === 1 && page.value > 1) goToPage(page.value - 1);
    else reload();
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível excluir", detail: normalizeApiError(err).message, life: 5000 });
  }
}

// ── Vasilhames & Reutilizáveis (Perdas, Quebras e Histórico) ───────
const reusableLossVisible = ref(false);
const reusableLossLoading = ref(false);
const reusableLossTarget = ref(null);
const reusableLossTypes = [
  { label: "Quebra / Avaria (Garrafa trincada/quebrada, copo quebrado)", value: "BREAKAGE" },
  { label: "Extravio / Sumiço (Vasilhame não devolvido / perda)", value: "LOSS" },
  { label: "Desgaste / Fim de Vida Útil (Descarte por velhice)", value: "ASSET_DISPOSAL" },
];
const reusableLossForm = ref({
  movement_type: "BREAKAGE",
  quantity: 1,
  notes: "",
});

function openReusableLossDialog(row) {
  reusableLossTarget.value = row;
  reusableLossForm.value = {
    movement_type: "BREAKAGE",
    quantity: 1,
    notes: "",
  };
  reusableLossVisible.value = true;
}

async function submitReusableLoss() {
  if (!reusableLossTarget.value?.id) return;
  reusableLossLoading.value = true;
  try {
    const res = await api.post(`/assets/reusables/${reusableLossTarget.value.id}/record-loss/`, {
      movement_type: reusableLossForm.value.movement_type,
      quantity: reusableLossForm.value.quantity,
      notes: reusableLossForm.value.notes,
    });
    toast.add({
      severity: "success",
      summary: "Baixa registrada",
      detail: res?.data?.message || "Movimentação registrada com sucesso.",
      life: 3500,
    });
    reusableLossVisible.value = false;
    reload();
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao registrar baixa",
      detail: normalizeApiError(err).message,
      life: 5000,
    });
  } finally {
    reusableLossLoading.value = false;
  }
}

const reusableHistoryVisible = ref(false);
const reusableHistoryLoading = ref(false);
const reusableHistoryTarget = ref(null);
const reusableHistoryMovements = ref([]);

async function openReusableHistoryDialog(row) {
  reusableHistoryTarget.value = row;
  reusableHistoryMovements.value = [];
  reusableHistoryVisible.value = true;
  reusableHistoryLoading.value = true;
  try {
    const res = await api.get(`/assets/reusables/${row.id}/history/`);
    reusableHistoryMovements.value = Array.isArray(res.data) ? res.data : (res.data?.results || []);
  } catch (err) {
    toast.add({
      severity: "error",
      summary: "Falha ao obter histórico",
      detail: normalizeApiError(err).message,
      life: 4000,
    });
  } finally {
    reusableHistoryLoading.value = false;
  }
}

/* ── Helpers de exibição ───────────────────────────────────────────── */
const value = resolveColumnValue;
const label = mapLabel;
const money = formatMoney;
const dateTime = formatDateTime;
/** Tamanho de arquivo legível — a API devolve bytes crus. */
function bytes(value) {
  const size = Number(value);
  if (!Number.isFinite(size) || size <= 0) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function columnBodyStyle(column) {
  return {
    textAlign: column.align === "right" ? "right" : "left",
    whiteSpace: column.type === "badges" ? "normal" : "nowrap",
  };
}

function badgeValues(rawValue) {
  if (Array.isArray(rawValue)) {
    return rawValue.map((item) => String(item).trim()).filter(Boolean);
  }
  if (rawValue === null || rawValue === undefined || rawValue === "") return [];
  if (typeof rawValue === "string" && rawValue.trim().startsWith("[")) {
    try {
      const parsed = JSON.parse(rawValue);
      if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean);
    } catch {
      // Mantém o valor original quando uma API antiga retornar texto inválido.
    }
  }
  return [String(rawValue).trim()].filter(Boolean);
}

const KDS_PROGRESS = {
  idle: "Não enviado",
  sent_to_kitchen: "Etapa 1 de 5",
  preparing: "Etapa 2 de 5",
  partially_ready: "Etapa 3 de 5",
  ready: "Etapa 4 de 5",
  delivered: "Etapa 5 de 5",
};
function kdsProgressLabel(status) {
  return KDS_PROGRESS[status] || "Sem andamento";
}

// Tom (cor) de cada status — subtil, funciona bem no dark.
const STATUS_TONE = {
  paid: "success", ready: "success", delivered: "success", issued: "success", in: "success", free: "success",
  pending: "warning", awaiting_payment: "warning", cleaning: "warning", adjustment: "warning",
  partial: "info", partially_ready: "info", open: "info", preparing: "info", sent_to_kitchen: "info", out_for_delivery: "info", reserved: "info",
  refunded: "danger", cancelled: "danger", failed: "danger", error: "danger", occupied: "danger", out: "danger",
  idle: "neutral", draft: "neutral", closed: "neutral", ignored: "neutral", IGNORED: "neutral",
  IN_USE: "success", IN_STOCK: "info", IN_MAINTENANCE: "warning", BROKEN: "danger", DISPOSED: "danger",
  LOST: "danger", STOLEN: "danger", LOANED: "neutral", TRANSFERRED: "neutral", INACTIVE: "neutral",
  CONFIRMED: "success", DIVERGENT: "warning", DRAFT: "neutral", CANCELLED: "danger",
};
function statusTone(v, map) {
  if (map && map[v] && map[v].tone) return map[v].tone;
  return STATUS_TONE[v] || "neutral";
}

onMounted(() => {
  loadRows();
  if (props.endpoint === "/inbound-nfe/") {
    loadDfeSyncInfo();
    fetchInboundStatusCounts();
    if (!dfeTimerInterval) {
      dfeTimerInterval = setInterval(() => {
        nowTick.value = Date.now();
        if (dfeSyncInfo.value?.next_allowed_at) {
          const target = new Date(dfeSyncInfo.value.next_allowed_at).getTime();
          if (target && Date.now() >= target && dfeSyncInfo.value.is_blocked) {
            loadDfeSyncInfo();
          }
        }
      }, 10000);
    }
  }
});

onBeforeUnmount(() => {
  if (dfeTimerInterval) {
    clearInterval(dfeTimerInterval);
    dfeTimerInterval = null;
  }
});
</script>

<style scoped>
.rpro {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rpro__head,
.rpro__toolbar,
.rpro__panel { animation: soft-pop var(--motion-slow) var(--motion-spring) both; }
.rpro__toolbar { animation-delay: 45ms; }
.rpro__panel { animation-delay: 90ms; }

:deep(.p-datatable-loading-overlay) {
  background: color-mix(in srgb, var(--surface-card) 82%, transparent);
  backdrop-filter: blur(2px);
  animation: soft-pop var(--motion-base) ease both;
}

:deep(.p-datatable-loading-icon) {
  color: var(--brand);
  filter: drop-shadow(0 3px 8px color-mix(in srgb, var(--brand) 24%, transparent));
}

:deep(.p-datatable-tbody > tr) {
  transition: background-color var(--motion-fast) ease, transform var(--motion-fast) var(--motion-spring);
}

:deep(.p-datatable-tbody > tr:hover) { transform: translateX(2px); }

/* ── Cabeçalho ──────────────────────────────────────────────────────── */
.rpro__head {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.rpro__head-top {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.rpro__head-copy h1 { margin: 0; color: var(--text-strong); font: var(--weight-extra) 26px/1.15 var(--font-sans); }
.rpro__head-copy p { margin: 4px 0 0; color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); }
.rpro__head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rpro__head-banner { width: 100%; }

/* ── Botões ─────────────────────────────────────────────────────────── */
.rpro-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  height: 38px; padding: 0 14px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 13px/1 var(--font-sans); cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.rpro-btn:hover:not(:disabled) { background: var(--surface-hover); border-color: var(--border-strong); color: var(--text-strong); }
.rpro-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rpro-btn .pi { font-size: 14px; }
.rpro-btn--primary { background: var(--brand); border-color: var(--brand); color: var(--on-brand); }
.rpro-btn--primary:hover:not(:disabled) { background: var(--brand-hover); border-color: var(--brand-hover); color: var(--on-brand); }
.rpro-btn--ghost { background: var(--surface-card); }
.rpro-btn--icon { width: 38px; padding: 0; }
.rpro-btn--sm { height: 32px; padding: 0 12px; font-size: 12.5px; }

/* ── Aviso do filtro vindo por link ──────────────────────────────────── */
.rpro__linkfilter {
  display: flex; align-items: center; gap: 9px; padding: 10px 14px;
  border: 1px solid var(--info); border-radius: var(--radius-md);
  background: var(--info-subtle); color: var(--info-text); font-size: 12.5px;
}
.rpro__linkfilter button {
  margin-left: auto; padding: 0; border: 0; background: none; cursor: pointer;
  color: inherit; font: var(--weight-bold) 12.5px/1 var(--font-sans); text-decoration: underline;
}

/* ── Toolbar ────────────────────────────────────────────────────────── */
.rpro__toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
}
.rpro__toolbar-left { display: flex; align-items: center; gap: 4px; flex: 1 1 auto; flex-wrap: wrap; }
.rpro__toolbar-right { display: flex; align-items: center; gap: 8px; }
.rpro__mobile-filter-trigger,
.rpro__mobile-drawer-head,
.rpro__mobile-file-actions,
.rpro__mobile-drawer-footer { display: none; }
.rpro__search { position: relative; flex: 1 1 240px; min-width: 0; }
.rpro__search :deep(.p-inputtext) { width: 100%; height: var(--control-h); border-radius: 4px; padding-right: 2.2rem; }
.rpro__search-clear {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 11px;
  transition: all 0.15s ease;
  z-index: 2;
}
.rpro__search-clear:hover {
  color: var(--text-strong);
  background: var(--surface-hover);
}
.rpro__daterange { flex: 0 0 auto; width: 232px; }
.rpro__daterange :deep(.p-inputtext) { height: var(--control-h); border-radius: 4px; }

/* ── Erro ───────────────────────────────────────────────────────────── */
.rpro__error {
  display: flex; align-items: center; gap: 9px; padding: 12px 14px;
  color: var(--danger-text); background: var(--danger-subtle);
  border: 1px solid color-mix(in srgb, var(--danger) 24%, transparent); border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

/* ── Painel + tabela ────────────────────────────────────────────────── */
.rpro__panel {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  background: var(--surface-card); box-shadow: var(--shadow-sm);
}

.rpro__table { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.rpro__table :deep(.p-datatable-wrapper) { flex: 1; min-height: 0; }
.rpro__table :deep(.p-datatable-thead > tr > th) {
  padding: 11px 12px;
  border-color: var(--border-subtle);
  color: var(--text-subtle);
  background: var(--surface-sunken);
  font: var(--weight-bold) 11.5px/1 var(--font-table);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.rpro__table :deep(.p-datatable-tbody > tr) { background: var(--surface-card); color: var(--text-body); cursor: pointer; }
.rpro__table :deep(.p-datatable-tbody > tr > td) {
  padding: 11px 12px; border-color: var(--border-subtle);
  font: var(--weight-regular) 14px/1.35 var(--font-table); color: var(--text-body);
}
.rpro__table :deep(.p-datatable-tbody > tr:hover) { background: var(--surface-hover); }
.rpro__table :deep(.p-datatable-tbody > tr.p-highlight) { background: var(--brand-subtle); }
.rpro__table :deep(.p-datatable-tbody > tr.p-datatable-emptymessage > td),
.rpro__table :deep(.p-datatable-tbody > tr.p-datatable-emptymessage:hover) { border: none; cursor: default; background: var(--surface-card); }
.rpro__table :deep(.dt-col-right .p-column-header-content) { justify-content: flex-end; }
.rpro__table :deep(.p-sortable-column .p-sortable-column-icon) { width: 11px; height: 11px; font-size: 11px; margin-left: 4px; }

.rpro-num { color: var(--text-strong); font-weight: var(--weight-bold); }
.rpro-muted { color: var(--text-muted); }
.rpro-cell { max-width: 260px; display: inline-block; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }

.rpro-badges { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 4px; max-width: 320px; vertical-align: middle; }
.rpro-badge {
  display: inline-flex; align-items: center; min-height: 22px; padding: 2px 7px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--surface-sunken); color: var(--text-body);
  font: var(--weight-semibold) 11.5px/1.25 var(--font-sans); white-space: nowrap;
}
.rpro-kds { display: inline-flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.rpro-kds small { color: var(--text-muted); font: var(--weight-semibold) 10.5px/1 var(--font-sans); white-space: nowrap; }

/* Status pill — subtil (tint + texto colorido), legível no light e no dark */
.rpro-chip {
  display: inline-flex; align-items: center;
  padding: 3px 8px; border-radius: 4px;
  border: 1px solid transparent;
  font: var(--weight-bold) 11px/1.35 var(--font-sans); white-space: nowrap;
  background: var(--surface-sunken); color: var(--text-muted);
}
.rpro-chip[data-tone="success"] { background: var(--success-subtle); color: var(--success-text); border-color: color-mix(in srgb, var(--success) 26%, transparent); }
.rpro-chip[data-tone="warning"] { background: var(--warning-subtle); color: var(--warning-text); border-color: color-mix(in srgb, var(--warning) 26%, transparent); }
.rpro-chip[data-tone="info"]    { background: var(--info-subtle);    color: var(--info-text);    border-color: color-mix(in srgb, var(--info) 26%, transparent); }
.rpro-chip[data-tone="danger"]  { background: var(--danger-subtle);  color: var(--danger-text);  border-color: color-mix(in srgb, var(--danger) 26%, transparent); }
.rpro-chip[data-tone="neutral"] { background: var(--surface-sunken);  color: var(--text-muted);   border-color: var(--border); }

.rpro__row-actions { display: inline-flex; justify-content: flex-end; }
.rpro__row-btn {
  width: 30px; height: 30px; display: inline-grid; place-items: center;
  border: none; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer;
}
.rpro__row-btn:hover { background: var(--surface-hover); color: var(--text-strong); }

/* ── Diálogo de códigos (QR + barcode) ──────────────────────────────── */
.rpro__codes { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 4px 0; }
.rpro__codes--loading { flex-direction: row; color: var(--text-muted); padding: 20px; }
.rpro__codes-value { font: var(--weight-semibold) 14px/1 var(--font-mono, monospace); color: var(--text-strong); letter-spacing: 1px; }
.rpro__codes-barcode { max-width: 100%; height: auto; }
.rpro-thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border); display: block; }
.rpro__versions { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; max-height: 420px; overflow-y: auto; }
.rpro__versions-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; }
.rpro__versions-info { display: flex; flex-direction: column; gap: 2px; }
.rpro__versions-info small { color: var(--text-muted); }
.rpro__versions-actions { display: flex; gap: 8px; flex-shrink: 0; }
.rpro__dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* ── Barra de ações em massa ────────────────────────────────────────── */
.rpro__bulkbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 10px 14px; border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
}
.rpro__bulkbar-count { display: inline-flex; align-items: center; gap: 10px; color: var(--text-strong); font: var(--weight-semibold) 13px/1 var(--font-sans); }
.rpro__bulkbar-all {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--text-brand); font: var(--weight-bold) 12.5px/1 var(--font-sans);
  text-decoration: underline; text-underline-offset: 2px;
}
.rpro__bulkbar-all:disabled { opacity: 0.6; cursor: default; }
.rpro__bulkbar-actions { display: inline-flex; gap: 8px; flex-wrap: wrap; }

/* ── Estado vazio ───────────────────────────────────────────────────── */
.rpro__empty {
  min-height: 200px; display: grid; place-items: center; align-content: center; gap: 8px;
  padding: 28px; color: var(--text-muted); text-align: center;
}
.rpro__empty i { color: var(--text-subtle); font-size: 28px; }
.rpro__empty strong { color: var(--text-strong); font: var(--weight-bold) 15px/1.2 var(--font-sans); }
.rpro__empty span { font: var(--weight-medium) 13px/1.4 var(--font-sans); }

/* Banner de Alerta / Info para Visão Global e Falta de Certificado */
.rpro__dfe-alert {
  display: flex; align-items: flex-start; gap: 16px;
  padding: 16px 20px; border-radius: var(--radius-lg);
  border: 1px solid transparent;
}
.rpro__dfe-alert--info {
  background: color-mix(in srgb, #0ea5e9 8%, var(--surface-card));
  border-color: color-mix(in srgb, #0ea5e9 25%, transparent);
}
.rpro__dfe-alert--warning {
  background: color-mix(in srgb, #f59e0b 8%, var(--surface-card));
  border-color: color-mix(in srgb, #f59e0b 25%, transparent);
}
.rpro__dfe-alert-icon {
  width: 40px; height: 40px; border-radius: var(--radius-md);
  display: grid; place-items: center; font-size: 18px; flex-shrink: 0;
}
.rpro__dfe-alert--info .rpro__dfe-alert-icon { background: rgba(14, 165, 233, 0.15); color: #0ea5e9; }
.rpro__dfe-alert--warning .rpro__dfe-alert-icon { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.rpro__dfe-alert-info { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 0; }
.rpro__dfe-alert-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rpro__dfe-alert-head strong { font: var(--weight-bold) 14px/1.3 var(--font-sans); color: var(--text-strong); }
.rpro__dfe-pill {
  font-size: 10px; font-weight: var(--weight-bold); text-transform: uppercase;
  padding: 2px 7px; border-radius: 99px;
  background: rgba(14, 165, 233, 0.15); color: #0284c7;
}
.rpro__dfe-pill--warning { background: rgba(245, 158, 11, 0.15); color: #d97706; }
.rpro__dfe-alert p {
  margin: 0; font: var(--weight-medium) 12.5px/1.5 var(--font-sans); color: var(--text-muted);
}

@media (max-width: 720px) {
  .rpro__toolbar-left { flex: 1 1 100%; gap: 8px; }
  .rpro__search, .rpro__daterange { flex: 1 1 100%; width: 100%; }
  .rpro__toolbar-right { width: 100%; justify-content: space-between; }
}

@media (max-width: 900px) {
  .rpro { gap: 10px; }
  .rpro__head { align-items: center; }
  .rpro__head-copy h1 { font-size: 20px; }
  .rpro__head-actions { display: none; }
  .rpro__mobile-filter-trigger {
    width: 100%; height: 42px; padding: 0 14px;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    border: 1px solid var(--border); border-radius: var(--radius-md);
    background: var(--surface-card); color: var(--text-body);
    font: var(--weight-bold) 13px/1 var(--font-sans);
  }
  .rpro__mobile-filter-trigger small {
    min-width: 20px; height: 20px; padding: 0 6px; display: inline-flex; align-items: center; justify-content: center;
    border-radius: 99px; background: var(--brand); color: #fff; font-size: 10px;
  }
  .rpro__toolbar {
    position: fixed; inset: 0; z-index: 140;
    display: flex; flex-direction: column; align-items: stretch; justify-content: flex-start; gap: 18px;
    padding: max(18px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
    overflow-y: auto; background: var(--surface-card);
    visibility: hidden; opacity: 0; transform: translateY(100%);
    transition: transform .22s var(--ease-out), opacity .18s ease, visibility 0s linear .22s;
  }
  .rpro__toolbar--mobile-open {
    visibility: visible; opacity: 1; transform: translateY(0); transition-delay: 0s;
  }
  .rpro__mobile-drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .rpro__mobile-drawer-head > div { display: flex; flex-direction: column; gap: 4px; }
  .rpro__mobile-drawer-head span { color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans); text-transform: uppercase; letter-spacing: .08em; }
  .rpro__mobile-drawer-head h2 { margin: 0; color: var(--text-strong); font: var(--weight-extra) 21px/1.1 var(--font-sans); }
  .rpro__mobile-drawer-head > button {
    width: 40px; height: 40px; display: grid; place-items: center;
    border: 0; border-radius: 50%; background: var(--surface-sunken); color: var(--text-body);
  }
  .rpro__toolbar-left { width: 100%; flex: none; display: flex; flex-direction: column; align-items: stretch; gap: 12px; }
  .rpro__search, .rpro__daterange { width: 100%; flex: none; }
  .rpro__search :deep(.p-inputtext), .rpro__daterange :deep(.p-inputtext) { height: 48px; }
  .rpro__toolbar-right { width: 100%; display: grid; grid-template-columns: 1fr 48px; gap: 10px; }
  .rpro__toolbar-right .rpro-btn { height: 46px; }
  .rpro__toolbar-right .rpro-btn--icon { width: 48px; }
  .rpro__mobile-file-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding-top: 16px; border-top: 1px solid var(--border-subtle); }
  .rpro__mobile-file-actions .rpro-btn { height: 46px; }
  .rpro__mobile-drawer-footer {
    margin-top: auto; display: grid; grid-template-columns: 1fr 1.4fr; gap: 10px;
    position: sticky; bottom: 0; padding-top: 14px; background: var(--surface-card);
  }
  .rpro__mobile-drawer-footer .rpro-btn { height: 48px; }
}

/* ── Estilos do Diálogo de Detalhes da NF-e de Entrada ─────────────── */
.rpro__inbound-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.rpro__inbound-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 0;
  color: var(--text-muted);
}

.rpro__inbound-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rpro__inbound-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.rpro__inbound-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.rpro__inbound-card--highlight {
  border-color: color-mix(in srgb, var(--brand) 30%, var(--border));
  background: color-mix(in srgb, var(--brand) 5%, var(--surface-sunken));
}

.rpro__inbound-card-label {
  font-size: 11px;
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
  color: var(--text-subtle);
}

.rpro__inbound-card-val {
  font-size: 15px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.rpro__inbound-card-sub {
  font-size: 11.5px;
  color: var(--text-muted);
}

.rpro__inbound-key-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
}

.rpro__inbound-key-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.rpro__inbound-key-label {
  font-size: 12px;
  font-weight: var(--weight-semibold);
  color: var(--text-muted);
}

.rpro__inbound-key-val {
  font-size: 12.5px;
  font-weight: var(--weight-medium);
  color: var(--text-strong);
  letter-spacing: 0.05em;
  word-break: break-all;
}

.rpro__inbound-items-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rpro__inbound-items-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.rpro__inbound-table-wrapper {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.rpro__inbound-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.rpro__inbound-table thead {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface-sunken);
}

.rpro__inbound-table th {
  padding: 9px 10px;
  font-size: 11px;
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
  color: var(--text-subtle);
  border-bottom: 1px solid var(--border);
}

.rpro__inbound-table td {
  padding: 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-body);
  vertical-align: top;
}

.rpro__inbound-table tbody tr:hover {
  background: var(--surface-hover);
}

.rpro__code-pill {
  display: inline-block;
  padding: 2px 6px;
  background: var(--surface-sunken);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
}

.rpro__inbound-row--has-taxes td {
  border-bottom: none !important;
  padding-bottom: 4px !important;
}

.rpro__inbound-tax-subrow td {
  padding: 0 10px 8px 10px !important;
  border-bottom: 1px solid var(--border-subtle);
}

.rpro__inbound-tax-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 4px 10px;
  background: color-mix(in srgb, var(--surface-sunken) 70%, transparent);
  border: 1px dashed var(--border-subtle);
  border-radius: 4px;
}

.rpro__inbound-tax-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  font-weight: var(--weight-bold);
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.rpro__inbound-tax-tag {
  display: inline-flex;
  align-items: center;
  padding: 1.5px 7px;
  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

/* ── Estilos de Upload de XML de NF-e ──────────────────────────────── */
.rpro__dfe-card-icon--upload {
  background: color-mix(in srgb, #0ea5e9 12%, var(--surface-sunken));
  color: #0284c7;
}

.rpro__dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 20px;
  border: 2px dashed var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  text-align: center;
  transition: all 0.2s ease;
}

.rpro__dropzone:hover,
.rpro__dropzone--active {
  border-color: var(--brand);
  background: color-mix(in srgb, var(--brand) 5%, var(--surface-sunken));
}

.rpro__selected-files-scroll {
  max-height: 180px;
  overflow-y: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-card);
}

.rpro__selected-file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.rpro__selected-file-item:last-child {
  border-bottom: none;
}

/* ── Modal de Vínculo de Itens (inbound-map) ────────────────────────── */
.inbound-map {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inbound-map__summary {
  padding: 12px 14px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.inbound-map__summary-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.inbound-map__summary-label {
  font-size: 11px;
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
  color: var(--text-muted);
}

.inbound-map__summary-price {
  font-size: 13.5px;
  font-weight: var(--weight-bold);
  font-family: monospace;
  color: #10b981;
}

.inbound-map__summary-title {
  font-size: 14px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
  display: block;
}

.inbound-map__summary-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 6px;
}

.inbound-map__summary-meta code {
  padding: 1px 4px;
  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  font-family: monospace;
  color: var(--text-strong);
}

.inbound-map__tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  gap: 6px;
}

.inbound-map__tab-btn {
  padding: 8px 14px;
  font-size: 13px;
  font-weight: var(--weight-semibold);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}

.inbound-map__tab-btn:hover {
  color: var(--text-strong);
}

.inbound-map__tab-btn--active {
  border-bottom-color: var(--brand);
  color: var(--brand);
  font-weight: var(--weight-bold);
}

.inbound-map__tab-btn--asset.inbound-map__tab-btn--active {
  border-bottom-color: #06b6d4;
  color: #22d3ee;
}

.inbound-map__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.inbound-map__filter-btn {
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 11.5px;
  font-weight: var(--weight-medium);
  border: 1px solid var(--border);
  background: var(--surface-sunken);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.inbound-map__filter-btn:hover {
  border-color: var(--text-muted);
  color: var(--text-strong);
}

.inbound-map__filter-btn--active {
  background: color-mix(in srgb, var(--brand) 15%, var(--surface-sunken));
  border-color: var(--brand);
  color: var(--brand);
  font-weight: var(--weight-bold);
}

.inbound-map__search-box {
  position: relative;
  margin-bottom: 10px;
}

.inbound-map__search-input {
  width: 100%;
  height: 38px;
  padding-left: 34px;
  padding-right: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-strong);
  font-size: 13px;
  box-sizing: border-box;
}

.inbound-map__search-input:focus {
  outline: none;
  border-color: var(--brand);
}

.inbound-map__search-icon {
  position: absolute;
  left: 10px;
  top: 12px;
  color: var(--text-muted);
  font-size: 13px;
}

.inbound-map__search-clear {
  position: absolute;
  right: 10px;
  top: 11px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
}

.inbound-map__list {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
}

.inbound-map__list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.15s ease;
}

.inbound-map__list-item:last-child {
  border-bottom: none;
}

.inbound-map__list-item:hover {
  background: var(--surface-hover);
}

.inbound-map__list-item--selected {
  background: color-mix(in srgb, var(--brand) 10%, var(--surface-card));
  border-left: 3px solid var(--brand);
}

.inbound-map__item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.inbound-map__item-name {
  font-size: 13px;
  color: var(--text-strong);
}

.inbound-map__item-meta {
  display: flex;
  gap: 12px;
  font-size: 11.5px;
  color: var(--text-muted);
}

.inbound-map__item-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.inbound-map__tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: var(--weight-bold);
  text-transform: uppercase;
}

.inbound-map__tag--RAW_MATERIAL_INGREDIENT {
  background: rgba(6, 78, 59, 0.4);
  color: #6ee7b7;
  border: 1px solid #047857;
}

.inbound-map__tag--MERCHANDISE_FOR_SALE {
  background: rgba(30, 58, 138, 0.4);
  color: #93c5fd;
  border: 1px solid #1d4ed8;
}

.inbound-map__tag--CONSUMABLE {
  background: rgba(120, 53, 15, 0.4);
  color: #fde68a;
  border: 1px solid #b45309;
}

.inbound-map__tag--REUSABLE_MATERIAL {
  background: rgba(88, 28, 135, 0.4);
  color: #e9d5ff;
  border: 1px solid #7e22ce;
}

.inbound-map__tag--EQUIPMENT,
.inbound-map__tag--FIXED_ASSET {
  background: rgba(22, 78, 99, 0.4);
  color: #67e8f9;
  border: 1px solid #0e7490;
}

.inbound-map__empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

.inbound-map__quick-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.inbound-map__callout {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: color-mix(in srgb, var(--brand) 10%, var(--surface-sunken));
  border: 1px solid color-mix(in srgb, var(--brand) 30%, var(--border));
  border-radius: var(--radius-md);
  font-size: 12.5px;
  color: var(--text-body);
}

.inbound-map__callout--asset {
  background: rgba(8, 51, 68, 0.45);
  border-color: rgba(6, 182, 212, 0.4);
}

.inbound-map__field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.inbound-map__label {
  font-size: 12px;
  font-weight: var(--weight-semibold);
  color: var(--text-strong);
}

.inbound-map__sublabel {
  display: block;
  font-size: 11px;
  font-weight: normal;
  color: var(--text-muted);
  margin-top: 2px;
}

.inbound-map__input {
  width: 100% !important;
  height: 38px !important;
  box-sizing: border-box !important;
  background: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  padding: 0 10px !important;
  color: var(--text-strong) !important;
  font-size: 13px !important;
}

.inbound-map__input:focus {
  border-color: var(--brand) !important;
  outline: none !important;
}

.inbound-map__dropdown {
  width: 100% !important;
  height: 38px !important;
  box-sizing: border-box !important;
  background: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  display: flex !important;
  align-items: center !important;
}

.inbound-map__input-number {
  width: 100% !important;
  display: flex !important;
}

.inbound-map__grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.inbound-map__track-options {
  padding: 10px 14px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.inbound-map__track-title {
  font-size: 12px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.inbound-map__track-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}

.inbound-map__checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-body);
  cursor: pointer;
}

.inbound-map__conversion-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-top: 6px;
}

.inbound-map__section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.inbound-map__readonly-unit {
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 38px;
  padding: 0 12px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 13px;
}

.inbound-map__readonly-unit strong {
  color: var(--brand);
}

.inbound-map__readonly-unit small {
  font-size: 10.5px;
  color: var(--text-muted);
}

.inbound-map__factor-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.inbound-map__factor-prefix {
  font-size: 12px;
  font-weight: var(--weight-semibold);
  color: var(--text-muted);
  white-space: nowrap;
}

.inbound-map__factor-suffix {
  font-size: 13px;
  font-weight: var(--weight-bold);
  color: var(--brand);
  white-space: nowrap;
}

:deep(.inbound-map__factor-input) {
  display: inline-flex;
  flex: 1;
  min-width: 90px;
}

:deep(.inbound-map__factor-inner),
:deep(.inbound-map__factor-input .p-inputnumber-input) {
  text-align: center !important;
  font-weight: bold !important;
  font-size: 15px !important;
  height: 38px !important;
  width: 100% !important;
  background: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  color: var(--text-strong) !important;
}

:deep(.inbound-map__factor-inner:focus),
:deep(.inbound-map__factor-input .p-inputnumber-input:focus) {
  border-color: var(--brand) !important;
  box-shadow: 0 0 0 1px var(--brand) !important;
  outline: none !important;
}

:deep(.inbound-map__input-number) {
  width: 100%;
  display: inline-flex;
}

:deep(.inbound-map__input-number .p-inputnumber-input) {
  width: 100% !important;
  height: 38px !important;
  background: var(--surface-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  color: var(--text-strong) !important;
  padding: 0 12px !important;
}

.inbound-map__preview-box {
  background: color-mix(in srgb, #10b981 10%, var(--surface-card));
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.inbound-map__preview-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: var(--weight-bold);
  color: #34d399;
}

.inbound-map__preview-grid {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.inbound-map__preview-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.inbound-map__preview-lbl {
  font-size: 10.5px;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: var(--weight-semibold);
}

.inbound-map__preview-val {
  font-size: 13.5px;
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.inbound-map__preview-arrow {
  color: var(--text-muted);
  font-size: 14px;
}

/* ── Filtros de Status da NF-e (Inbound Filters) ────────────────────── */
.rpro__inbound-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-sunken);
}

.rpro__inbound-filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 9999px;
  font-size: 11.5px;
  font-weight: var(--weight-medium);
  border: 1px solid var(--border);
  background: var(--surface-card);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.rpro__inbound-filter-pill:hover {
  border-color: var(--text-muted);
  color: var(--text-strong);
}

.rpro__inbound-filter-pill--active {
  background: color-mix(in srgb, var(--brand) 15%, var(--surface-card));
  border-color: var(--brand);
  color: var(--brand);
  font-weight: var(--weight-bold);
}

.rpro__inbound-filter-pill--warning.rpro__inbound-filter-pill--active {
  background: rgba(245, 158, 11, 0.15);
  border-color: #f59e0b;
  color: #fbbf24;
}

.rpro__inbound-filter-pill--info.rpro__inbound-filter-pill--active {
  background: rgba(59, 130, 246, 0.15);
  border-color: #3b82f6;
  color: #60a5fa;
}

.rpro__inbound-filter-pill--success.rpro__inbound-filter-pill--active {
  background: rgba(16, 185, 129, 0.15);
  border-color: #10b981;
  color: #34d399;
}

.rpro__inbound-filter-pill--danger.rpro__inbound-filter-pill--active {
  background: rgba(239, 68, 68, 0.15);
  border-color: #ef4444;
  color: #f87171;
}

.rpro__inbound-cancelled-banner {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: var(--radius-md);
  color: var(--text-strong);
  margin-bottom: 16px;
}

.rpro__inbound-cancelled-icon {
  color: #ef4444;
  flex-shrink: 0;
  margin-top: 2px;
}

.rpro__inbound-cancelled-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.rpro__inbound-cancelled-info strong {
  color: #ef4444;
  font-size: 13.5px;
  letter-spacing: 0.04em;
}

.rpro__inbound-cancelled-info p {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-body);
  line-height: 1.4;
}

.rpro__inbound-cancelled-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed rgba(239, 68, 68, 0.25);
  font-size: 11.5px;
  color: var(--text-muted);
}

.rpro__inbound-cancelled-meta strong {
  color: var(--text-strong);
  font-size: 11.5px;
}

.rpro__inbound-cancelled-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  font-weight: var(--weight-bold);
  font-size: 12px;
}

.rpro__inbound-ignored-banner {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: var(--radius-md);
  color: var(--text-strong);
  margin-bottom: 16px;
}

.rpro__inbound-ignored-icon {
  color: #94a3b8;
  flex-shrink: 0;
  margin-top: 2px;
}

.rpro__inbound-ignored-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
  font-weight: var(--weight-bold);
  font-size: 12px;
}

.rpro__inbound-row--ignored {
  opacity: 0.55;
  background: rgba(0, 0, 0, 0.08);
}

.rpro__inbound-row--ignored .rpro__inbound-item-desc {
  text-decoration: line-through;
  color: var(--text-muted);
}

.rpro-nfe-ignored-pill {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: var(--weight-semibold);
  border-radius: 9999px;
  background: rgba(148, 163, 184, 0.15);
  color: #94a3b8;
  border: 1px solid rgba(148, 163, 184, 0.25);
}

.rpro__manual-cancel-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-strong);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.4;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s ease;
}

.rpro__manual-cancel-textarea:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand);
}

.rpro__inbound-filter-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  height: 16px;
  border-radius: 9999px;
  background: var(--surface-hover, rgba(0, 0, 0, 0.08));
  color: var(--text-muted);
  font-size: 10px;
  font-weight: var(--weight-bold);
  min-width: 18px;
  line-height: 1;
}

.rpro__inbound-filter-pill--active .rpro__inbound-filter-count {
  background: rgba(255, 255, 255, 0.22);
  color: inherit;
}

.rpro-nfe-status-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.rpro-nfe-pending-pill {
  display: inline-block;
  padding: 1px 6px;
  background: rgba(245, 158, 11, 0.2);
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: #fbbf24;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: var(--weight-semibold);
}

/* ── Modal de Confirmação de Ciência da Operação ─────────────── */
.rpro__science-modal {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}

.rpro__science-info-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.rpro__science-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.rpro__science-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
  font-size: 12.5px;
}

.rpro__science-alert {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: var(--radius-md);
  color: var(--text-body);
  font-size: 13px;
  line-height: 1.5;
}

.rpro__science-alert-text p {
  margin: 0;
}

/* ── Paginação e Seletor de Registros por Página ────────────────────── */
.rpro__pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-card);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.rpro__pager-nav {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.rpro__pager-info {
  color: var(--text-muted);
  font: var(--weight-medium) 12.5px/1 var(--font-sans);
}

.rpro__pager-size {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.rpro__pager-size-label {
  font-size: 12px;
  font-weight: var(--weight-medium);
  color: var(--text-muted);
}

.rpro__pager-size-select {
  padding: 4px 8px;
  font-size: 12px;
  font-weight: var(--weight-medium);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-sunken);
  color: var(--text-strong);
  cursor: pointer;
  outline: none;
}

.rpro__pager-size-select:focus {
  border-color: var(--brand);
}

/* ── Estilos Vasilhames & Reutilizáveis ────────────────────────────── */
.rpro__row-btn--danger {
  color: #f43f5e;
}
.rpro__row-btn--danger:hover {
  background: color-mix(in srgb, #f43f5e 14%, transparent);
  color: #fb7185;
}
.rpro__row-btn--info {
  color: #6366f1;
}
.rpro__row-btn--info:hover {
  background: color-mix(in srgb, #6366f1 14%, transparent);
  color: #818cf8;
}

.rpro__reusable-info-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}
.rpro__reusable-info-item span {
  display: block;
  font-size: 11.5px;
  color: var(--text-muted);
}
.rpro__reusable-info-item strong {
  font-size: 15px;
  color: var(--text-strong);
}

.rpro__reusable-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.rpro__reusable-field label {
  font-size: 12.5px;
  font-weight: var(--weight-semibold);
  color: var(--text-strong);
}
.rpro__reusable-field small {
  font-size: 11.5px;
  color: var(--text-muted);
}

.rpro__reusable-history-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  text-align: center;
}
.rpro__reusable-history-card span {
  display: block;
  font-size: 11.5px;
  color: var(--text-muted);
}
.rpro__reusable-history-card strong {
  font-size: 16px;
  font-weight: var(--weight-bold);
}
.rpro__reusable-table-wrap {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.rpro__reusable-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.rpro__reusable-table th {
  position: sticky;
  top: 0;
  background: var(--surface-card);
  padding: 10px 12px;
  font-weight: var(--weight-semibold);
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  text-align: left;
  z-index: 1;
}
.rpro__reusable-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-body);
}
.rpro__reusable-table tr:hover td {
  background: var(--surface-hover);
}
</style>
<style scoped src="../styles/inbound-nfe-list.css"></style>
