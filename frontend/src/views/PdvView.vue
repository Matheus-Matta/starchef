<template>
  <div class="pdv">
    <div v-if="pdvGateLoading" class="pdv__gate"><i class="pi pi-spin pi-spinner" /><h2>Verificando o caixa...</h2></div>
    <div v-else-if="pdvBlocked" class="pdv__gate pdv__gate--blocked"><span><i class="pi pi-lock" /></span><h2>PDV bloqueado</h2><p>{{ pdvBlockedReason }}</p><button class="pdv__btn pdv__btn--primary" type="button" @click="router.push({name:'caixa'})">Ir para o controle de caixa</button></div>
    <div v-else-if="!browserOnline" class="pdv__gate pdv__gate--blocked"><span><i class="pi pi-wifi" /></span><h2>PDV web sem conexão</h2><p>O navegador precisa do servidor para registrar vendas. Para operar offline, utilize o aplicativo StarChef PDV Desktop.</p></div>
    <!-- ── STEP 0: Selecionar restaurante (admin em "Todos") ──────── -->
    <div v-if="step === 'restaurant'" class="pdv__step pdv__step--type">
      <div class="pdv__step-header">
        <h2>Selecione o restaurante</h2>
        <p>Você está em "Todos os restaurantes". Escolha um para abrir o pedido.</p>
      </div>
      <div v-if="loadingRestaurants" class="pdv__loading">Carregando restaurantes...</div>
      <div v-else class="pdv__type-grid">
        <button
          v-for="r in restaurants"
          :key="r.id"
          class="pdv__type-card"
          type="button"
          @click="selectRestaurant(r)"
        >
          <span class="pdv__type-icon"><i class="pi pi-building" /></span>
          <strong>{{ r.trade_name }}</strong>
          <small>{{ r.city || r.legal_name || "" }}</small>
        </button>
        <div v-if="!restaurants.length" class="pdv__empty">Nenhum restaurante disponível.</div>
      </div>
    </div>

    <!-- ── STEP 1: Escolher tipo de pedido ───────────────────────── -->
    <div v-if="step === 'type'" class="pdv__step pdv__step--type">
      <div class="pdv__step-header">
        <button
          v-if="isAdmin && currentRestaurantName"
          class="pdv__back"
          type="button"
          @click="navigateStep('restaurant')"
        >
          <AppIcon name="store" :size="15" /> {{ currentRestaurantName }} · trocar
        </button>
        <h2>Novo pedido</h2>
        <p>Selecione o tipo de atendimento para comecar.</p>
      </div>
      <div class="pdv__type-grid">
        <button
          v-for="t in orderTypes"
          :key="t.value"
          class="pdv__type-card"
          :class="{ 'pdv__type-card--selected': orderType === t.value }"
          type="button"
          @click="selectType(t.value)"
        >
          <span class="pdv__type-icon"><i :class="`pi ${t.icon}`" /></span>
          <strong>{{ t.label }}</strong>
          <small>{{ t.hint }}</small>
        </button>
      </div>
    </div>

    <!-- ── STEP 2: Selecionar comanda, mesa vinculada ou cliente ── -->
    <div v-if="step === 'context'" class="pdv__step pdv__step--context">
      <div class="pdv__step-header">
        <button class="pdv__back" type="button" @click="navigateStep('type')">
          <AppIcon name="arrow-left" :size="16" /> Voltar
        </button>
        <h2>{{ contextTitle }}</h2>
      </div>

      <!-- Seleção de comanda (self-service) -->
      <div v-if="orderType === 'command'" class="pdv__tables">
        <div v-if="loadingCommands" class="pdv__loading">Carregando comandas...</div>
        <template v-else>
          <div class="pdv__tables-bar">
            <span class="pdv__tables-count">
              <span class="pdv__dot pdv__dot--free" />
              {{ freeCommands.length }} {{ freeCommands.length === 1 ? "comanda livre" : "comandas livres" }} · toque numa em uso para editar o pedido
            </span>
            <div class="pdv__search-box pdv__search-box--sm">
              <AppIcon name="search" :size="15" />
              <input v-model="commandSearch" placeholder="Buscar por número, código ou cliente..." />
            </div>
          </div>
          <div class="pdv__table-grid">
            <button
              v-for="command in selectableCommands"
              :key="command.id"
              class="pdv__table-card"
              :class="[
                `pdv__table-card--${command.status || 'free'}`,
                { 'pdv__table-card--selected': selectedCommand?.id === command.id },
                { 'pdv__table-card--busy': creatingOrder && selectedCommand?.id === command.id },
              ]"
              type="button"
              :disabled="creatingOrder"
              @click="pickCommand(command)"
            >
              <span class="pdv__table-top">
                <strong class="pdv__table-number">{{ command.number }}</strong>
                <span class="pdv__table-status">{{ pdvCommandStatus(command.status) }}</span>
              </span>
              <span class="pdv__table-meta">
                <small>{{ command.code }}</small>
                <small>{{ command.customer_name || "—" }}</small>
              </span>
            </button>
            <div v-if="!selectableCommands.length" class="pdv__empty">
              {{ allCommands.length ? "Nenhuma comanda encontrada." : "Nenhuma comanda cadastrada." }}
            </div>
          </div>
        </template>
      </div>

      <!-- Seleção de cliente (delivery/takeaway) -->
      <div v-if="['delivery', 'takeaway'].includes(orderType)" class="pdv__customer-search">
        <div class="pdv__customer-searchbar">
          <div class="pdv__search-box">
            <AppIcon name="search" :size="16" />
            <input v-model="customerSearch" placeholder="Buscar cliente por nome ou telefone..." @input="searchCustomers" />
          </div>
          <button class="pdv__btn pdv__btn--secondary" type="button" @click="openCustomerModal">
            <AppIcon name="plus" :size="15" /> Cadastrar
          </button>
        </div>
        <div v-if="customers.length" class="pdv__customer-list">
          <button
            v-for="c in customers"
            :key="c.id"
            class="pdv__customer-option"
            :class="{ 'pdv__customer-option--selected': selectedCustomer?.id === c.id }"
            type="button"
            @click="selectedCustomer = c"
          >
            <strong>{{ c.name }}</strong>
            <small>{{ c.phone || c.email || "Sem contato" }}</small>
          </button>
        </div>
        <div v-if="customerSearch && !customers.length" class="pdv__empty">
          <span>Nenhum cliente encontrado.</span>
          <button class="pdv__link-btn" type="button" @click="openCustomerModal">Cadastrar “{{ customerSearch }}”</button>
        </div>
      </div>

      <div v-if="orderType !== 'command'" class="pdv__step-footer">
        <button
          class="pdv__btn pdv__btn--primary"
          type="button"
          :disabled="!canProceedContext || creatingOrder"
          @click="startOrder"
        >
          {{ creatingOrder ? "Abrindo pedido..." : "Abrir pedido" }}
        </button>
      </div>
    </div>

    <!-- ── STEP 3: Montar pedido ─────────────────────────────────── -->
    <div v-if="step === 'order'" class="pdv__order" :class="{ 'pdv__order--editing': editMode }">
      <div v-if="editMode" class="pdv__edit-banner">
        <i class="pi pi-pencil" />
        <span><strong>Editar pedido #{{ currentOrder?.sequence }}</strong><small>Inclua ou remova itens deste pedido.</small></span>
      </div>
      <!-- Coluna esquerda: cardápio -->
      <div class="pdv__menu-col">
        <div class="pdv__menu-top">
          <div class="pdv__search-box">
            <AppIcon name="search" :size="16" />
            <input v-model="productSearch" placeholder="Buscar produto..." />
          </div>
          <select v-model="activeCategory" class="pdv__category-select" aria-label="Filtrar por categoria">
            <option :value="null">Todas as categorias</option>
            <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
          </select>
        </div>

        <div class="pdv__products">
          <div v-if="loadingProducts" class="pdv__loading">Carregando produtos...</div>
          <div v-else class="pdv__product-grid">
            <button
              v-for="product in filteredProducts"
              :key="product.id"
              class="pdv__product-card"
              type="button"
              :disabled="!product.is_active"
              @click="addItem(product)"
            >
              <span class="pdv__product-card-head">
                <span class="pdv__product-card-name">{{ product.name }}</span>
                <small v-if="!product.is_active" class="pdv__inactive">Inativo</small>
              </span>
              <span class="pdv__product-card-foot">
                <span class="pdv__product-card-price">
                  {{ money(product.current_price) }}<template v-if="product.pricing_unit === 'kg'">/kg</template>
                </span>
                <span class="pdv__product-add"><AppIcon name="plus" :size="14" /></span>
              </span>
            </button>
            <div v-if="!filteredProducts.length" class="pdv__empty">Nenhum produto encontrado.</div>
          </div>
        </div>
      </div>

      <!-- Coluna direita: resumo do pedido -->
      <button
        class="pdv__mobile-panel-trigger pdv__mobile-panel-trigger--cart"
        type="button"
        :aria-expanded="mobileCartOpen"
        @click="mobileCartOpen = true"
      >
        <span><AppIcon name="shopping-cart" :size="17" /> Ver pedido <small>{{ cartItems.length }} {{ cartItems.length === 1 ? 'item' : 'itens' }}</small></span>
        <strong>{{ money(currentOrder?.total) }}</strong>
      </button>
      <div class="pdv__cart-col" :class="{ 'pdv__cart-col--mobile-open': mobileCartOpen }">
        <div class="pdv__cart-header">
          <div class="pdv__order-info">
            <strong>Pedido #{{ currentOrder?.sequence }}</strong>
            <span>{{ orderTypeLabel }}{{ tableLabel }}</span>
          </div>
          <div v-if="currentOrder" class="pdv__order-badges">
            <span class="pdv__badge pdv__badge--prod" :class="`pdv__prod--${currentOrder.production_status}`">
              {{ prodStatusLabel(currentOrder.production_status) }}
            </span>
          </div>
          <button class="pdv__mobile-panel-close" type="button" aria-label="Fechar resumo do pedido" @click="mobileCartOpen = false">
            <AppIcon name="chevron-down" :size="18" />
          </button>
        </div>

        <div class="pdv__cart-items">
          <div v-if="!cartItems.length" class="pdv__cart-empty">
            <i class="pi pi-shopping-cart" style="font-size:28px;opacity:0.3" />
            <span>Nenhum item adicionado</span>
          </div>

          <!-- Itens já enviados (em produção) -->
          <template v-if="sentItems.length">
            <div class="pdv__cart-section-label">
              <AppIcon name="soup" :size="12" />Em producao ({{ sentItems.length }})
            </div>
            <div v-for="item in sentItems" :key="item.id" class="pdv__cart-item pdv__cart-item--sent">
              <div class="pdv__cart-item-info">
                <strong>{{ item.product_name }}</strong>
                <small v-if="itemExtras(item)">{{ itemExtras(item) }}</small>
                <small v-if="item.customer_note">{{ item.customer_note }}</small>
                <div class="pdv__cart-item-meta">
                  <span v-if="item.batch_number" class="pdv__batch-tag">Rodada {{ item.batch_number }}</span>
                  <span class="pdv__cart-item-status" :class="`pdv__status--${item.status}`">
                    {{ itemStatusLabel(item.status) }}
                  </span>
                </div>
              </div>
              <div class="pdv__cart-item-price">
                <span>{{ qtyLabel(item) }} {{ money(item.unit_price) }}{{ item.pricing_unit === 'kg' ? '/kg' : '' }}</span>
                <strong :class="{ 'pdv__price--comped': item.status === 'comped' }">{{ money(item.total_price) }}</strong>
              </div>
            </div>
          </template>

          <!-- Itens pendentes (rodada atual) -->
          <template v-if="pendingItems.length">
            <div class="pdv__cart-section-label pdv__cart-section-label--pending">
              <AppIcon name="clock" :size="12" />Aguardando envio ({{ pendingItems.length }})
            </div>
            <div v-for="item in pendingItems" :key="item.id" class="pdv__cart-item">
              <div class="pdv__cart-item-info">
                <strong>{{ item.product_name }}</strong>
                <small v-if="itemExtras(item)">{{ itemExtras(item) }}</small>
                <small v-if="item.customer_note">{{ item.customer_note }}</small>
              </div>
              <div class="pdv__cart-item-right">
                <div class="pdv__cart-item-price">
                  <span>{{ qtyLabel(item) }} {{ money(item.unit_price) }}{{ item.pricing_unit === 'kg' ? '/kg' : '' }}</span>
                  <strong>{{ money(item.total_price) }}</strong>
                </div>
                <button class="pdv__void-btn" type="button" title="Cancelar item" @click="voidItem(item)">
                  <AppIcon name="x" :size="13" />
                </button>
              </div>
            </div>
          </template>
        </div>

        <Teleport to="body">
          <div v-if="configuringProduct" class="pdv__overlay" @click.self="closeProductOptions">
            <div class="pdv__modal pdv__modal--options">
              <h3>Personalizar {{ configuringProduct.name }}</h3>
              <div v-if="activeVariations.length" class="pdv__option-group">
                <h4>Variação <small v-if="requiresVariation">Obrigatória</small></h4>
                <label v-for="variation in activeVariations" :key="variation.id" class="pdv__option-row">
                  <input v-model="selectedVariationId" type="radio" name="product-variation" :value="variation.id" />
                  <span>{{ variation.name }}</span><strong>+ {{ money(variation.price_delta) }}</strong>
                </label>
              </div>
              <p v-else-if="requiresVariation" class="pdv__option-warning">
                Este produto exige uma variação, mas não possui opções ativas cadastradas.
              </p>
              <div v-if="activeAddons.length" class="pdv__option-group">
                <h4>Adicionais</h4>
                <label v-for="addon in activeAddons" :key="addon.id" class="pdv__option-row">
                  <input v-model="selectedAddonIds" type="checkbox" :value="addon.id" />
                  <span>{{ addon.name }}</span><strong>+ {{ money(addon.price) }}</strong>
                </label>
              </div>
              <div v-if="configuringProduct.pricing_unit !== 'kg'" class="pdv__option-group">
                <h4>Quantidade</h4>
                <div class="pdv__quantity-control">
                  <button type="button" aria-label="Diminuir quantidade" :disabled="configuredQuantity <= 1" @click="configuredQuantity--">
                    <i class="pi pi-minus" />
                  </button>
                  <strong>{{ configuredQuantity }}</strong>
                  <button type="button" aria-label="Aumentar quantidade" @click="configuredQuantity++">
                    <i class="pi pi-plus" />
                  </button>
                </div>
              </div>
              <div class="pdv__option-group">
                <h4>Observação <small>Opcional</small></h4>
                <textarea v-model="configuredNote" class="pdv__note-input" rows="3" placeholder="Ex.: sem cebola, bem passado..." />
              </div>
              <div class="pdv__modal-actions">
                <button class="pdv__btn pdv__btn--ghost" type="button" @click="closeProductOptions">Cancelar</button>
                <button class="pdv__btn pdv__btn--primary" type="button" :disabled="requiresVariation && !selectedVariationId" @click="confirmProductOptions">Adicionar</button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- Pesagem (produto por kg) -->
        <Teleport to="body">
          <div v-if="weighingProduct" class="pdv__overlay" @click.self="weighingProduct = null">
            <div class="pdv__modal pdv__modal--weigh">
              <h4>
                <AppIcon name="scale" :size="16" />
                {{ weighingProduct.name }} — {{ money(weighingProduct.current_price) }}/kg
              </h4>

              <div class="pdv__weigh-scale-row">
                <label for="pdv-scale">Balança</label>
                <select id="pdv-scale" v-model="selectedScale" class="pdv__close-input" :disabled="loadingScales" @change="selectScale">
                  <option :value="null">{{ loadingScales ? "Buscando balanças..." : "Selecione a balança" }}</option>
                  <option v-for="s in scales" :key="s.id" :value="s">{{ scaleLabel(s) }}</option>
                </select>
                <small v-if="!loadingScales && !scales.length">Nenhuma balança ativa cadastrada neste restaurante.</small>
              </div>

              <div class="pdv__weigh-display" :class="{ 'pdv__weigh-display--ok': weighKg > 0 }">
                <strong>{{ weighKg > 0 ? weighKg.toFixed(3) : '0.000' }}</strong>
                <span>kg</span>
              </div>

              <div class="pdv__weigh-meta">
                <span v-if="scaleReading">
                  Leitura da balanca{{ scaleReading.is_stable ? '' : ' (instavel)' }}
                  <template v-if="Number(scaleReading.tare_kg) > 0"> — tara {{ Number(scaleReading.tare_kg).toFixed(3) }} kg</template>
                </span>
                <span v-else-if="weighKg > 0">Peso digitado manualmente</span>
                <span v-else>Leia a balanca ou digite o peso</span>
              </div>

              <div class="pdv__weigh-actions">
                <button
                  v-if="selectedScale"
                  class="pdv__btn pdv__btn--secondary"
                  type="button"
                  :disabled="readingScale"
                  @click="readScale"
                >
                  {{ readingScale ? 'Lendo...' : 'Ler balanca' }}
                </button>
                <input
                  v-model="manualWeight"
                  type="number"
                  min="0.001"
                  step="0.001"
                  class="pdv__close-input pdv__weigh-manual"
                  placeholder="Peso manual (kg)"
                  @input="scaleReading = null"
                />
              </div>

              <div class="pdv__weigh-total">
                <span>Total</span>
                <strong>{{ money(weighTotal) }}</strong>
              </div>

              <p v-if="weighError" class="pdv__weigh-error">{{ weighError }}</p>

              <div class="pdv__modal-actions">
                <button class="pdv__btn pdv__btn--ghost" type="button" @click="weighingProduct = null">Cancelar</button>
                <button
                  class="pdv__btn pdv__btn--primary"
                  type="button"
                  :disabled="!weighKg || confirmingWeigh"
                  @click="confirmWeigh"
                >
                  {{ confirmingWeigh ? 'Lancando...' : 'Adicionar item' }}
                </button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- Nota -->
        <Teleport to="body">
          <div v-if="addingNoteFor" class="pdv__overlay" @click.self="addingNoteFor = null">
            <div class="pdv__modal">
              <h4>Observacao para <em>{{ addingNoteFor.product?.name }}</em></h4>
              <textarea v-model="pendingNote" class="pdv__note-input" rows="3" placeholder="Ex: sem cebola, bem passado..." />
              <div class="pdv__modal-actions">
                <button class="pdv__btn pdv__btn--ghost" type="button" @click="addingNoteFor = null; pendingNote = ''">Cancelar</button>
                <button class="pdv__btn pdv__btn--primary" type="button" @click="confirmNote">Confirmar</button>
              </div>
            </div>
          </div>
        </Teleport>

        <div class="pdv__cart-totals">
          <label class="pdv__service-fee-toggle">
            <input v-model="serviceFeeEnabled" type="checkbox" />
            <span>Cobrar taxa de serviço</span>
          </label>
          <div class="pdv__total-row">
            <span>Subtotal</span>
            <strong>{{ money(currentOrder?.subtotal) }}</strong>
          </div>
          <div v-if="serviceFeeEnabled && previewServiceFee > 0" class="pdv__total-row">
            <span>Taxa de serviço</span>
            <strong>{{ money(previewServiceFee) }}</strong>
          </div>
          <div class="pdv__total-row pdv__total-row--total">
            <span>Total</span>
            <strong>{{ money(orderPreviewTotal) }}</strong>
          </div>
        </div>

        <div class="pdv__cart-actions">
          <button
            class="pdv__btn pdv__btn--secondary"
            type="button"
            :disabled="!cartItems.length || printingOrder"
            @click="showReceipt"
          >
            <i class="pi pi-file" /> {{ printingOrder ? "Abrindo recibo..." : "Imprimir recibo de venda" }}
          </button>
          <button
            class="pdv__btn pdv__btn--danger"
            type="button"
            @click="showCancelModal = true"
          >
            Cancelar pedido
          </button>
          <button
            class="pdv__btn pdv__btn--primary"
            type="button"
            :disabled="!cartItems.length || cartItems.every(i => i.status === 'cancelled')"
            @click="goToClose"
          >
            {{ editMode ? 'Ir ao pagamento' : 'Finalizar pedido' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── STEP 4: Pagamento (teclado PDV) ────────────────────────── -->
    <div v-if="step === 'close'" class="pdv__pay">
      <div class="pdv__mobile-payment-actions">
        <button
          class="pdv__mobile-payment-btn pdv__mobile-payment-btn--primary"
          type="button"
          :disabled="remainingAmount > 0 && (!canConfirmKeypad || paying)"
          @click="remainingAmount <= 0 ? confirmPaid() : confirmKeypadPayment()"
        >
          <AppIcon name="plus" :size="16" />
          <span>{{ remainingAmount <= 0 ? 'Finalizar' : (paying ? 'Adicionando...' : 'Adicionar pagamento') }}</span>
        </button>
        <button class="pdv__mobile-payment-btn" type="button" @click="payLater">
          <AppIcon name="clock" :size="16" />
          <span>Pagar depois</span>
        </button>
        <button
          class="pdv__mobile-payment-btn"
          type="button"
          :aria-expanded="mobilePaymentSummaryOpen"
          @click="mobilePaymentSummaryOpen = true"
        >
          <AppIcon name="receipt-text" :size="16" />
          <span>Ver detalhes</span>
        </button>
      </div>
      <!-- Coluna esquerda: resumo do pedido -->
      <div class="pdv__pay-summary" :class="{ 'pdv__pay-summary--mobile-open': mobilePaymentSummaryOpen }">
        <button class="pdv__mobile-panel-close pdv__mobile-panel-close--summary" type="button" aria-label="Fechar resumo do pagamento" @click="mobilePaymentSummaryOpen = false">
          <AppIcon name="chevron-down" :size="18" /> Fechar resumo
        </button>
        <button class="pdv__back" type="button" @click="navigateStep('order')">
          <AppIcon name="arrow-left" :size="16" /> Voltar ao pedido
        </button>
        <div class="pdv__pay-order">
          <div>
            <strong>Pedido #{{ currentOrder?.sequence }}</strong>
            <small>{{ orderTypeLabel }}{{ tableLabel }}</small>
          </div>
          <span v-if="selectedCustomer?.name || currentOrder?.customer_name">{{ selectedCustomer?.name || currentOrder?.customer_name }}</span>
        </div>

        <div class="pdv__pay-items">
          <div
            v-for="item in cartItems.filter(i => i.status !== 'cancelled')"
            :key="item.id"
            class="pdv__pay-item"
            :class="{ 'pdv__pay-item--comped': item.status === 'comped' }"
          >
            <span class="pdv__pay-item-qty">{{ qtyLabel(item) }}</span>
            <span class="pdv__pay-item-info">
              <strong>{{ item.product_name }}</strong>
              <small v-if="itemExtras(item)">{{ itemExtras(item) }}</small>
            </span>
            <strong class="pdv__pay-item-price">{{ item.status === 'comped' ? 'Cortesia' : money(item.total_price) }}</strong>
          </div>
        </div>

        <div class="pdv__pay-totals">
          <div class="pdv__pay-row"><span>Subtotal</span><span>{{ money(currentOrder?.subtotal) }}</span></div>
          <div v-if="currentOrder?.service_fee > 0" class="pdv__pay-row"><span>Taxa de serviço</span><span>{{ money(currentOrder?.service_fee) }}</span></div>
          <div class="pdv__pay-row pdv__pay-row--grand"><span>Total</span><strong>{{ money(finalTotal) }}</strong></div>
        </div>

        <div v-if="registeredPayments.length" class="pdv__pay-registered">
          <span class="pdv__pay-registered-title">Formas de pagamento</span>
          <div v-for="p in registeredPayments" :key="p.id" class="pdv__pay-registered-row pdv__pay-registered-entry">
            <span>
              {{ p.payment_method_name || 'Pagamento' }}
              <small v-if="Number(p.change_amount) > 0">Troco: {{ money(p.change_amount) }}</small>
            </span>
            <strong>{{ money(p.amount) }}</strong>
            <button
              class="pdv__payment-delete"
              type="button"
              :disabled="deletingPaymentId === p.id"
              aria-label="Excluir pagamento"
              title="Excluir pagamento"
              @click="deletePayment(p)"
            >
              <i :class="deletingPaymentId === p.id ? 'pi pi-spin pi-spinner' : 'pi pi-trash'" />
            </button>
          </div>
          <div class="pdv__pay-registered-row pdv__pay-registered-remaining">
            <span>Restante</span>
            <strong :class="remainingAmount <= 0 ? 'pdv__balance--change' : 'pdv__balance--due'">{{ money(remainingAmount) }}</strong>
          </div>
        </div>

        <div class="pdv__pay-balance">
          <div class="pdv__pay-row"><span>Recebido</span><strong>{{ money(creditAmount) }}</strong></div>
          <div class="pdv__pay-row">
            <span>{{ balanceAmount < 0 ? 'Troco' : 'Saldo' }}</span>
            <strong :class="balanceAmount < 0 ? 'pdv__balance--change' : 'pdv__balance--due'">{{ money(Math.abs(balanceAmount)) }}</strong>
          </div>
        </div>

        <button class="pdv__btn pdv__btn--secondary pdv__pay-print" type="button" :disabled="printingOrder" @click="showReceipt">
          <i class="pi pi-print" />
          {{ printingOrder ? "Abrindo recibo..." : "Imprimir recibo" }}
        </button>

        <div class="pdv__pay-summary-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" @click="payLater">Pagar depois</button>
          <button
            class="pdv__btn pdv__btn--primary"
            type="button"
            :disabled="remainingAmount > 0 && (!canConfirmKeypad || paying)"
            @click="remainingAmount <= 0 ? confirmPaid() : confirmKeypadPayment()"
          >
            {{ remainingAmount <= 0 ? 'Finalizar pedido' : (paying ? 'Registrando...' : (willComplete ? 'Confirmar pagamento' : 'Adicionar pagamento')) }}
          </button>
        </div>
      </div>

      <!-- Coluna direita: teclado numérico -->
      <div class="pdv__pay-keypad-col">
        <div class="pdv__payable">
          <div class="pdv__payable-value">
            <small>Valor a pagar</small>
            <strong>{{ money(remainingAmount) }}</strong>
          </div>
        </div>

        <div class="pdv__pay-method-field">
          <label for="pdv-pay-method">Forma de pagamento</label>
          <select id="pdv-pay-method" v-model="selectedPaymentMethod" class="pdv__pay-select">
            <option :value="null" disabled>Selecione a forma</option>
            <option v-for="method in paymentMethods" :key="method.id" :value="method">{{ method.name }}</option>
          </select>
        </div>

        <div class="pdv__pay-display" :class="{ 'pdv__pay-display--empty': padStr === '' }">{{ displayAmount }}</div>

        <div v-if="payError" class="pdv__error">{{ payError }}</div>

        <div class="pdv__keypad">
          <button v-for="k in ['1','2','3','4','5','6','7','8','9']" :key="k" type="button" @click="pressKey(k)">{{ k }}</button>
          <button type="button" @click="pressKey('.')">.</button>
          <button type="button" @click="pressKey('0')">0</button>
          <button type="button" class="pdv__key-back" aria-label="Apagar" @click="backspaceKey"><i class="pi pi-delete-left" /></button>
        </div>
      </div>
    </div>

    <!-- ── STEP 5: Sucesso ───────────────────────────────────────── -->
    <div v-if="step === 'success'" class="pdv__step pdv__step--success">
      <div class="pdv__success-card">
        <div class="pdv__success-icon"><i class="pi pi-check-circle" /></div>
        <div class="pdv__success-copy">
          <h2>Pedido pago!</h2>
          <p>Pedido #{{ lastPaidSequence }} finalizado com sucesso.</p>
        </div>
        <div class="pdv__success-summary">
          <span>Total recebido</span>
          <strong>{{ money(currentOrder?.total) }}</strong>
        </div>
        <div v-if="totalChange > 0" class="pdv__success-summary pdv__success-summary--change">
          <span>Troco para o cliente</span>
          <strong>{{ money(totalChange) }}</strong>
        </div>

        <!-- Imprimir pedido/comanda: comprovante interno, sem valor fiscal. -->
        <button
          class="pdv__btn pdv__btn--secondary pdv__success-fiscal"
          type="button"
          :disabled="printingOrder"
          @click="showReceipt"
        >
          <i class="pi pi-file" /> {{ printingOrder ? "Abrindo nota..." : "Imprimir pedido/comanda" }}
        </button>

        <div class="pdv__success-actions">
          <button class="pdv__btn pdv__btn--primary" type="button" @click="newOrder">
            <i class="pi pi-plus" /> Novo pedido
          </button>
        </div>
      </div>
    </div>

    <!-- Seleção da mesa antes de abrir ou retomar uma comanda -->
    <div
      v-if="showCommandTableDialog"
      class="pdv__overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pdv-command-table-title"
      @click.self="closeCommandTableDialog"
    >
      <div class="pdv__modal pdv__modal--command-table">
        <div class="pdv__command-dialog-title">
          <span class="pdv__command-dialog-icon"><AppIcon name="ticket" :size="18" /></span>
          <span>
            <small>Comanda</small>
            <h3 id="pdv-command-table-title">{{ selectedCommand?.number }}</h3>
          </span>
        </div>
        <p>Selecione a mesa que ficará vinculada a esta comanda antes de abrir o pedido.</p>

        <div v-if="loadingTables" class="pdv__loading">Carregando mesas...</div>
        <div v-else class="pdv__command-table-grid" role="radiogroup" aria-label="Mesa da comanda">
          <button
            type="button"
            class="pdv__command-table-option"
            :class="{ 'pdv__command-table-option--selected': selectedTable === null }"
            :aria-checked="selectedTable === null"
            role="radio"
            :disabled="creatingOrder"
            @click="chooseCommandTable(null)"
          >
            <AppIcon name="minus" :size="16" />
            <span><strong>Sem mesa</strong><small>Abrir somente a comanda</small></span>
          </button>
          <button
            v-for="table in linkableTables"
            :key="table.id"
            type="button"
            class="pdv__command-table-option"
            :class="{ 'pdv__command-table-option--selected': selectedTable?.id === table.id }"
            :aria-checked="selectedTable?.id === table.id"
            role="radio"
            :disabled="creatingOrder"
            @click="chooseCommandTable(table)"
          >
            <AppIcon name="armchair" :size="16" />
            <span>
              <strong>Mesa {{ table.number }}</strong>
              <small>{{ pdvTableStatus(table.status) }}<template v-if="selectedCommand?.current_table === table.id"> · atual</template></small>
            </span>
          </button>
        </div>

        <div class="pdv__modal-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" :disabled="creatingOrder" @click="closeCommandTableDialog">Cancelar</button>
          <button class="pdv__btn pdv__btn--primary" type="button" :disabled="loadingTables || creatingOrder" @click="startOrder">
            {{ creatingOrder ? "Abrindo..." : "Confirmar e abrir" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal cadastrar cliente (delivery/retirada) -->
    <div v-if="showCustomerModal" class="pdv__overlay" @click.self="showCustomerModal = false">
      <div class="pdv__modal">
        <h3>Cadastrar cliente</h3>
        <p>Preencha os dados para cadastrar e já selecionar o cliente.</p>
        <div class="pdv__option-group">
          <label class="pdv__field-label" for="new-cust-name">Nome <small>Obrigatório</small></label>
          <input id="new-cust-name" v-model="newCustomer.name" class="pdv__modal-input" placeholder="Nome completo" @keyup.enter="createCustomer" />
        </div>
        <div class="pdv__field-row">
          <div class="pdv__option-group">
            <label class="pdv__field-label" for="new-cust-phone">Telefone</label>
            <input id="new-cust-phone" v-model="newCustomer.phone" class="pdv__modal-input" inputmode="tel" placeholder="(11) 90000-0000" />
          </div>
          <div class="pdv__option-group">
            <label class="pdv__field-label" for="new-cust-doc">CPF</label>
            <input id="new-cust-doc" v-model="newCustomer.document" class="pdv__modal-input" placeholder="000.000.000-00" />
          </div>
        </div>
        <div class="pdv__option-group">
          <label class="pdv__field-label" for="new-cust-email">Email</label>
          <input id="new-cust-email" v-model="newCustomer.email" class="pdv__modal-input" type="email" placeholder="email@exemplo.com" />
        </div>
        <div class="pdv__modal-section-title">Endereço de entrega</div>
        <div class="pdv__field-row pdv__field-row--address">
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-street">Rua / Avenida</label><input id="new-cust-street" v-model="newCustomer.address.street" class="pdv__modal-input" placeholder="Nome da rua" /></div>
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-number">Número</label><input id="new-cust-number" v-model="newCustomer.address.number" class="pdv__modal-input" placeholder="123" /></div>
        </div>
        <div class="pdv__field-row">
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-district">Bairro</label><input id="new-cust-district" v-model="newCustomer.address.district" class="pdv__modal-input" placeholder="Bairro" /></div>
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-zip">CEP</label><input id="new-cust-zip" v-model="newCustomer.address.zip_code" class="pdv__modal-input" inputmode="numeric" placeholder="00000-000" /></div>
        </div>
        <div class="pdv__field-row pdv__field-row--city">
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-city">Cidade</label><input id="new-cust-city" v-model="newCustomer.address.city" class="pdv__modal-input" placeholder="Cidade" /></div>
          <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-state">UF</label><input id="new-cust-state" v-model="newCustomer.address.state" class="pdv__modal-input" maxlength="2" placeholder="SP" /></div>
        </div>
        <div class="pdv__option-group"><label class="pdv__field-label" for="new-cust-complement">Complemento / referência</label><input id="new-cust-complement" v-model="newCustomer.address.complement" class="pdv__modal-input" placeholder="Apto, bloco ou ponto de referência" /></div>
        <div class="pdv__modal-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" @click="showCustomerModal = false">Cancelar</button>
          <button class="pdv__btn pdv__btn--primary" type="button" :disabled="!newCustomer.name.trim() || creatingCustomer" @click="createCustomer">
            {{ creatingCustomer ? "Cadastrando..." : "Cadastrar e selecionar" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal cancelar item -->
    <div v-if="itemToVoid" class="pdv__overlay" @click.self="closeVoidItemDialog">
      <div class="pdv__modal">
        <h3>Excluir item do pedido?</h3>
        <p>Informe o motivo. A exclusão ficará registrada na auditoria.</p>
        <div class="pdv__reason-options" role="group" aria-label="Motivos rápidos">
          <button
            v-for="reason in ITEM_VOID_REASONS"
            :key="reason"
            type="button"
            class="pdv__reason-option"
            :class="{ 'pdv__reason-option--selected': itemVoidReason === reason }"
            @click="itemVoidReason = reason"
          >
            {{ reason }}
          </button>
        </div>
        <label class="pdv__reason-label" for="item-void-reason">Outro motivo ou observação</label>
        <textarea
          id="item-void-reason"
          v-model="itemVoidReason"
          class="pdv__note-input"
          rows="3"
          autofocus
          placeholder="Ex: cliente desistiu do item..."
          @keydown.esc="closeVoidItemDialog"
        />
        <div class="pdv__modal-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" :disabled="voidingItem" @click="closeVoidItemDialog">Voltar</button>
          <button class="pdv__btn pdv__btn--danger" type="button" :disabled="!itemVoidReason.trim() || voidingItem" @click="confirmVoidItem">
            {{ voidingItem ? "Excluindo..." : "Excluir item" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal cancelar pedido -->
    <div v-if="showCancelModal" class="pdv__overlay" @click.self="showCancelModal = false">
      <div class="pdv__modal">
        <h3>Cancelar pedido?</h3>
        <p>Informe o motivo do cancelamento.</p>
        <textarea v-model="cancelReason" class="pdv__note-input" rows="3" placeholder="Ex: cliente desistiu..." />
        <div class="pdv__modal-actions">
          <button class="pdv__btn pdv__btn--ghost" type="button" @click="showCancelModal = false">Voltar</button>
          <button class="pdv__btn pdv__btn--danger" type="button" :disabled="!cancelReason || cancelling" @click="cancelOrder">
            {{ cancelling ? "Cancelando..." : "Cancelar pedido" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useToast } from "primevue/usetoast";
import AppIcon from "../components/AppIcon.vue";
import { api } from "../services/api";
import { useRealtimeResource } from "../composables/useRealtimeResource";
import { useAuthStore } from "../stores/auth";
import { normalizeApiError } from "../utils/apiError";

const route = useRoute();
const router = useRouter();
const props = defineProps({
  editMode: { type: Boolean, default: false },
  orderId: { type: String, default: null },
});
const editMode = computed(() => props.editMode);

const toast = useToast();
/** Mostra o erro da API normalizado num Toast (substitui os alert()). */
function pdvError(err, summary = "Não foi possível concluir a ação") {
  toast.add({ severity: "error", summary, detail: normalizeApiError(err).message, life: 5000 });
}

// ── State ────────────────────────────────────────────────────────
const step = ref("type");
const PDV_STEPS = new Set(["restaurant", "type", "context", "order", "close", "success"]);

function navigateStep(nextStep, { replace = false, query = {} } = {}) {
  if (!PDV_STEPS.has(nextStep)) return;
  step.value = nextStep;
  const nextQuery = { ...route.query, ...query, step: nextStep };
  for (const [key, value] of Object.entries(nextQuery)) {
    if (value === null || value === undefined || value === "") delete nextQuery[key];
  }
  const navigation = editMode.value
    ? { name: "pedido-editar-itens", params: { id: props.orderId }, query: nextQuery }
    : { name: "pdv", query: nextQuery };
  const promise = replace ? router.replace(navigation) : router.push(navigation);
  promise.catch(() => {});
}
const orderType = ref(null);
const selectedTable = ref(null);
const selectedCustomer = ref(null);
const currentOrder = ref(null);
const cartItems = ref([]);
const lastPaidSequence = ref(null);
const registeredPayments = ref([]);
const mobileCartOpen = ref(false);
const mobilePaymentSummaryOpen = ref(false);

// products
const allProducts = ref([]);
const categories = ref([]);
const activeCategory = ref(null);
const productSearch = ref("");
const loadingProducts = ref(false);

// tables
const allTables = ref([]);
const loadingTables = ref(false);

// comandas (reutilizáveis — self-service)
const allCommands = ref([]);
const loadingCommands = ref(false);
const selectedCommand = ref(null);
const commandSearch = ref("");
const showCommandTableDialog = ref(false);
const commandTableSelectionTouched = ref(false);

// restaurante (contexto do PDV — necessário quando o admin está em "Todos")
const restaurants = ref([]);
const browserOnline = ref(navigator.onLine);
const updateBrowserConnection = () => { browserOnline.value = navigator.onLine; };
const loadingRestaurants = ref(false);
const resolvedRestaurantId = ref(null);
const resolvedBranchId = ref(null);
const RESTAURANT_SCOPE_KEY = "starchef-restaurant-scope";
const isAdmin = ref(false); // definido ao resolver o contexto (a partir do /auth/me)
const currentRestaurantName = computed(() => restaurants.value.find((r) => r.id === resolvedRestaurantId.value)?.trade_name || "");
const currentRestaurant = computed(() => restaurants.value.find((r) => r.id === resolvedRestaurantId.value) || null);
const pdvGateLoading = ref(true);
const pdvBlocked = ref(false);
const pdvBlockedReason = ref("");

// customers
const customers = ref([]);
const customerSearch = ref("");
const showCustomerModal = ref(false);
const creatingCustomer = ref(false);
const newCustomer = reactive({
  name: "", phone: "", email: "", document: "",
  address: { label: "Principal", street: "", number: "", complement: "", district: "", city: "", state: "", zip_code: "", reference: "", is_default: true },
});

// payment
const paymentMethods = ref([]);
const selectedPaymentMethod = ref(null);
const amountReceived = ref(0);
const paying = ref(false);
const deletingPaymentId = ref(null);
const payError = ref("");
// Teclado numérico de pagamento (estilo PDV)
const padStr = ref("");

// misc
const discount = ref(0);
const discountInput = ref("0.00");
const serviceFeeEnabled = ref(true);
const sendingKitchen = ref(false);
const creatingOrder = ref(false);
const showCancelModal = ref(false);
const cancelReason = ref("");
const cancelling = ref(false);
const itemToVoid = ref(null);
const itemVoidReason = ref("");
const voidingItem = ref(false);
const ITEM_VOID_REASONS = [
  "Cliente desistiu do item",
  "Item lançado por engano",
  "Produto indisponível",
  "Pedido duplicado",
  "Erro na quantidade",
  "Troca solicitada pelo cliente",
];
const printingOrder = ref(false);
const addingNoteFor = ref(null);
const pendingNote = ref("");
const configuringProduct = ref(null);
const selectedVariationId = ref(null);
const selectedAddonIds = ref([]);
const configuredQuantity = ref(1);
const configuredNote = ref("");
const pendingConfiguration = ref({ variations: [], addons: [] });

// weighing (produtos por kg)
const weighingProduct = ref(null);
const scales = ref([]);
const selectedScale = ref(null);
const loadingScales = ref(false);
const loadedScaleBranchId = ref(null);
const scaleReading = ref(null);
const manualWeight = ref("");
const readingScale = ref(false);
const weighError = ref("");
const confirmingWeigh = ref(false);

// ── Order types ──────────────────────────────────────────────────
const auth = useAuthStore();
const orderTypes = computed(() => {
  const types = [
    { value: "command", label: "Comanda", icon: "pi-qrcode", hint: "Salão ou cartão de comanda" },
    { value: "counter", label: "Balcao", icon: "pi-building", hint: "Entrega imediata no balcao" },
  ];
  // Delivery/Retirada só quando o módulo de Entrega está ativo.
  if (auth.hasModule("entrega")) {
    types.push({ value: "delivery", label: "Delivery", icon: "pi-truck", hint: "Entrega no endereco do cliente" });
    types.push({ value: "takeaway", label: "Retirada", icon: "pi-send", hint: "Cliente retira no estabelecimento" });
  }
  return types;
});

// ── Computed ─────────────────────────────────────────────────────
const contextTitle = computed(() => {
  if (orderType.value === "command") return "Selecionar comanda";
  if (["delivery", "takeaway"].includes(orderType.value)) return "Selecionar cliente (opcional)";
  return "Confirmar tipo";
});

const canProceedContext = computed(() => {
  if (orderType.value === "command") return !!selectedCommand.value;
  return true;
});

// Comandas ativas, filtradas pela busca (número/código/cliente). Livres para abrir
// e em uso ("occupied") para retomar o pedido aberto.
const selectableCommands = computed(() => {
  const q = commandSearch.value.trim().toLowerCase();
  let list = allCommands.value.filter((c) => c.is_active);
  if (q) {
    list = list.filter(
      (c) =>
        String(c.number).includes(q) ||
        (c.code || "").toLowerCase().includes(q) ||
        (c.customer_name || "").toLowerCase().includes(q),
    );
  }
  return list;
});
const freeCommands = computed(() => allCommands.value.filter((c) => c.status === "free" && c.is_active));
const COMMAND_STATUS = { free: "Livre", occupied: "Em uso" };
function pdvCommandStatus(status) {
  return COMMAND_STATUS[status] || "Livre";
}

const linkableTables = computed(() =>
  allTables.value.filter((table) => table.is_active && table.status !== "cleaning"),
);

const TABLE_STATUS = { free: "Livre", occupied: "Ocupada", reserved: "Reservada", cleaning: "Limpeza" };
function pdvTableStatus(status) {
  return TABLE_STATUS[status] || "Livre";
}

const filteredProducts = computed(() => {
  let list = allProducts.value.filter((p) => p.is_active);
  if (activeCategory.value) list = list.filter((p) => p.category === activeCategory.value);
  if (productSearch.value.trim()) {
    const q = productSearch.value.toLowerCase();
    list = list.filter((p) => p.name.toLowerCase().includes(q) || (p.internal_code || "").toLowerCase().includes(q));
  }
  return list;
});
const activeVariations = computed(() => (configuringProduct.value?.variations || []).filter((v) => v.is_active));
const activeAddons = computed(() => (configuringProduct.value?.addons || []).filter((a) => a.is_active));
const requiresVariation = computed(() => Boolean(configuringProduct.value?.requires_variation));

// Items split by status
const pendingItems = computed(() => cartItems.value.filter((i) => i.status === "pending"));
const sentItems = computed(() => cartItems.value.filter((i) => i.status !== "pending" && i.status !== "cancelled"));

const orderTypeLabel = computed(() =>
  selectedCommand.value
    ? `Comanda ${selectedCommand.value.number}`
    : orderTypes.value.find((t) => t.value === orderType.value)?.label || "",
);
const tableLabel = computed(() => (selectedTable.value ? ` — Mesa ${selectedTable.value.number}` : ""));

const finalTotal = computed(() => Math.max(0, Number(currentOrder.value?.total || 0)));
const previewServiceFee = computed(() => {
  if (!serviceFeeEnabled.value) return 0;
  const current = Number(currentOrder.value?.service_fee || 0);
  if (current > 0) return current;
  const percent = Number(currentRestaurant.value?.default_service_fee_percent || 0);
  // Arredonda a taxa isoladamente, como o backend faz ao gravar, para que o
  // expected_total enviado no fechamento bata com o total recalculado.
  const rawFee = Number(currentOrder.value?.subtotal || 0) * percent / 100;
  return Math.round(rawFee * 100) / 100;
});
const orderPreviewTotal = computed(() => {
  const subtotal = Number(currentOrder.value?.subtotal || 0);
  const delivery = Number(currentOrder.value?.delivery_fee || 0);
  const orderDiscount = Number(currentOrder.value?.discount || 0);
  return Math.max(0, subtotal + delivery + previewServiceFee.value - orderDiscount);
});

const totalPaid = computed(() => registeredPayments.value.reduce((s, p) => s + Number(p.amount), 0));
const totalChange = computed(() => registeredPayments.value.reduce((s, p) => s + Number(p.change_amount || 0), 0));
const remainingAmount = computed(() => Math.max(0, finalTotal.value - totalPaid.value));
const canAddPayment = computed(() => selectedPaymentMethod.value && amountReceived.value > 0);

// ── Teclado de pagamento (PDV) ───────────────────────────────────
const padAmount = computed(() => Number(padStr.value) || 0);
// Vazio = paga o restante exato; digitado = usa o valor teclado.
const effectiveAmount = computed(() => (padStr.value === "" ? Number(remainingAmount.value) : padAmount.value));
const displayAmount = computed(() => money(padStr.value === "" ? remainingAmount.value : padAmount.value));
const creditAmount = computed(() => totalPaid.value + (padStr.value === "" ? 0 : padAmount.value));
// >0 = ainda falta; <0 = troco a devolver.
const balanceAmount = computed(() => Number(finalTotal.value) - creditAmount.value);
const canConfirmKeypad = computed(() => !!selectedPaymentMethod.value && effectiveAmount.value > 0);
// Este valor quita o restante? Se não, é um pagamento parcial (combina formas).
const willComplete = computed(() => effectiveAmount.value >= Number(remainingAmount.value));

// ── Methods ──────────────────────────────────────────────────────
function selectType(type) {
  orderType.value = type;
  navigateStep("context");
  // Atualiza o grid ao entrar no contexto para refletir o status atual
  // (mesa/comanda podem ter mudado desde o carregamento inicial).
  if (type === "command") Promise.all([loadCommands(), loadTables()]);
}

function pickCommand(command) {
  if (creatingOrder.value) return;
  selectedCommand.value = command;
  selectedTable.value =
    allTables.value.find((table) => table.id === command.current_table) || null;
  commandTableSelectionTouched.value = false;
  showCommandTableDialog.value = true;
}

function chooseCommandTable(table) {
  selectedTable.value = table;
  commandTableSelectionTouched.value = true;
}

function closeCommandTableDialog() {
  if (creatingOrder.value) return;
  showCommandTableDialog.value = false;
  commandTableSelectionTouched.value = false;
  selectedCommand.value = null;
  selectedTable.value = null;
}

async function startOrder() {
  if (creatingOrder.value) return;
  creatingOrder.value = true;
  try {
    // Comanda: ação dedicada (cria se livre, retoma se em uso).
    if (orderType.value === "command" && selectedCommand.value) {
      if (selectedTable.value) {
        await api.post(`/commands/${selectedCommand.value.id}/link-table/`, {
          table_id: selectedTable.value.id,
        });
      } else if (selectedCommand.value.current_table) {
        await api.post(`/commands/${selectedCommand.value.id}/unlink-table/`, {});
      }
      const { data: order } = await api.post("/orders/open-command/", { command: selectedCommand.value.id });
      await resumeTableOrder(order);
      showCommandTableDialog.value = false;
      return;
    }

    const payload = {
      order_type: orderType.value,
      restaurant: resolvedRestaurantId.value,
    };
    if (selectedCustomer.value) payload.customer = selectedCustomer.value.id;

    const res = await api.post("/orders/", payload);
    currentOrder.value = res.data;
    cartItems.value = [];
    discount.value = 0;
    discountInput.value = "0.00";
    serviceFeeEnabled.value = true;
    navigateStep("order", { query: { order: currentOrder.value.id } });
  } catch (e) {
    pdvError(e, "Erro ao abrir pedido");
  } finally {
    creatingOrder.value = false;
  }
}

let profileCache = null;
async function loadProfile() {
  if (auth.user) {
    profileCache = auth.user;
    return profileCache;
  }
  if (!profileCache) {
    const res = await api.get("/auth/me/");
    profileCache = res.data;
  }
  return profileCache;
}

async function loadProducts() {
  loadingProducts.value = true;
  try {
    const prodParams = { is_active: true, page_size: 200 };
    if (resolvedRestaurantId.value) prodParams.restaurant = resolvedRestaurantId.value;
    const [prodRes, catRes] = await Promise.all([
      // Produtos são por restaurante; categorias são compartilhadas (nível de conta).
      api.get("/menu/products/", { params: prodParams }),
      api.get("/menu/categories/", { params: { is_active: true, page_size: 100 } }),
    ]);
    allProducts.value = prodRes.data.results || prodRes.data;
    categories.value = catRes.data.results || catRes.data;
  } finally {
    loadingProducts.value = false;
  }
}

async function loadTables() {
  loadingTables.value = true;
  try {
    const params = { page_size: 200 };
    if (resolvedRestaurantId.value) params.restaurant = resolvedRestaurantId.value;
    const res = await api.get("/tables/", { params });
    allTables.value = res.data.results || res.data;
    if (
      showCommandTableDialog.value
      && !commandTableSelectionTouched.value
      && selectedCommand.value?.current_table
    ) {
      selectedTable.value =
        allTables.value.find((table) => table.id === selectedCommand.value.current_table) || null;
    }
  } finally {
    loadingTables.value = false;
  }
}

async function loadCommands() {
  loadingCommands.value = true;
  try {
    const params = { page_size: 500, is_active: true, ordering: "number" };
    if (resolvedRestaurantId.value) params.restaurant = resolvedRestaurantId.value;
    const res = await api.get("/commands/", { params });
    allCommands.value = res.data.results || res.data;
  } finally {
    loadingCommands.value = false;
  }
}

/* ── Contexto de restaurante do PDV ──────────────────────────────────
   Manager: usa restaurante/filial do perfil. Admin em "Todos": pede para
   selecionar um restaurante num step antes de começar. */
async function loadRestaurants() {
  loadingRestaurants.value = true;
  try {
    const res = await api.get("/restaurants/", { params: { is_active: true, page_size: 200 }, skipRestaurantScope: true });
    restaurants.value = res.data.results || res.data;
  } finally {
    loadingRestaurants.value = false;
  }
}

async function applyRestaurant(restaurantId) {
  resolvedRestaurantId.value = restaurantId;
  resolvedBranchId.value = null;
  await validatePdvCashAccess();
  if (pdvBlocked.value) return;
  await Promise.all([loadTables(), loadCommands(), loadProducts()]);
}

async function selectRestaurant(restaurant) {
  await applyRestaurant(restaurant.id, null);
  if (!pdvBlocked.value) navigateStep("type");
}

let cashValidationPromise = null;
let cashValidatedRestaurant = null;
let cashValidatedAt = 0;

async function validatePdvCashAccess({ force = false } = {}) {
  const restaurant = resolvedRestaurantId.value;
  if (!restaurant) {
    pdvGateLoading.value = false;
    return;
  }
  if (!force && cashValidatedRestaurant === restaurant && Date.now() - cashValidatedAt < 15_000) {
    return;
  }
  if (cashValidationPromise) return cashValidationPromise;

  cashValidationPromise = runPdvCashValidation().finally(() => {
    cashValidatedRestaurant = restaurant;
    cashValidatedAt = Date.now();
    cashValidationPromise = null;
  });
  return cashValidationPromise;
}

async function runPdvCashValidation() {
  pdvGateLoading.value = true;
  pdvBlocked.value = false;
  pdvBlockedReason.value = "";
  try {
    const profile = await loadProfile();
    const restaurant = resolvedRestaurantId.value;
    if (!restaurant) return;
    const [stationsResult, sessionResult] = await Promise.allSettled([
      api.get("/cash-stations/", { params: { restaurant, is_active: true, page_size: 100 } }),
      api.get("/cash-register/current/"),
    ]);
    if (stationsResult.status === "rejected") throw stationsResult.reason;
    const stations = stationsResult.value.data.results || stationsResult.value.data;
    const linkedStations = stations.filter((station) => (station.operators || []).map(String).includes(String(profile.id)));
    if (!linkedStations.length) {
      pdvBlocked.value = true;
      pdvBlockedReason.value = "Seu usuário não está vinculado a nenhum caixa ativo deste restaurante. Solicite o vínculo antes de usar o PDV.";
      return;
    }
    if (sessionResult.status === "fulfilled") {
      const session = sessionResult.value.data;
      const linkedSession = linkedStations.some((station) => station.id === session.cash_station);
      if (!linkedSession || session.status !== "open") {
        pdvBlocked.value = true;
        pdvBlockedReason.value = "Abra um dos caixas vinculados ao seu usuário antes de usar o PDV.";
      }
    } else {
      const error = sessionResult.reason;
      if (error.response?.status !== 404) throw error;
      pdvBlocked.value = true;
      pdvBlockedReason.value = "Você não possui uma sessão de caixa aberta. Abra um caixa vinculado antes de usar o PDV.";
    }
  } catch (error) {
    pdvBlocked.value = true;
    pdvBlockedReason.value = normalizeApiError(error).message;
  } finally {
    pdvGateLoading.value = false;
  }
}

/** Descobre o restaurante do PDV; se não houver (admin em "Todos"), abre o step. */
async function resolveContext() {
  const profile = await loadProfile();
  isAdmin.value = Boolean(profile?.is_superuser || profile?.profile_type === "admin" || profile?.profile_type === "owner");
  const scope = localStorage.getItem(RESTAURANT_SCOPE_KEY) || "";
  if (isAdmin.value) {
    // Admin: o contexto vem do seletor do topo. Sem seleção ("Todos") → pede num step.
    await loadRestaurants();
    if (scope) await applyRestaurant(scope, null);
    else navigateStep("restaurant", { replace: true });
    return;
  }
  // Manager/operador: usa restaurante/filial do próprio perfil.
  await applyRestaurant(profile.restaurant_id || scope || "", null);
}

async function loadPaymentMethods() {
  const res = await api.get("/payments/methods/", { params: { restaurant: resolvedRestaurantId.value, is_active: true } });
  paymentMethods.value = res.data.results || res.data;
}

async function searchCustomers() {
  if (!customerSearch.value.trim()) { customers.value = []; return; }
  try {
    const res = await api.get("/customers/", { params: { search: customerSearch.value, page_size: 20 } });
    customers.value = res.data.results || res.data;
  } catch { customers.value = []; }
}

/** Abre o modal de cadastro rápido, pré-preenchendo o nome com a busca atual. */
function openCustomerModal() {
  Object.assign(newCustomer, { name: customerSearch.value.trim(), phone: "", email: "", document: "" });
  Object.assign(newCustomer.address, { label: "Principal", street: "", number: "", complement: "", district: "", city: "", state: "", zip_code: "", reference: "", is_default: true });
  showCustomerModal.value = true;
}
/** Cadastra o cliente e já o seleciona, sem sair da tela. */
async function createCustomer() {
  if (!newCustomer.name.trim()) return;
  creatingCustomer.value = true;
  try {
    const payload = {
      name: newCustomer.name.trim(),
      phone: newCustomer.phone.trim(),
      email: newCustomer.email.trim(),
      document: newCustomer.document.trim(),
      is_active: true,
    };
    const hasAddress = Object.entries(newCustomer.address).some(([key, value]) => !["label", "is_default"].includes(key) && String(value || "").trim());
    if (hasAddress) payload.address = { ...newCustomer.address, state: newCustomer.address.state.trim().toUpperCase() };
    if (resolvedRestaurantId.value) payload.restaurant = resolvedRestaurantId.value;
    const { data } = await api.post("/customers/", payload);
    selectedCustomer.value = data;
    customers.value = [data, ...customers.value.filter((c) => c.id !== data.id)];
    showCustomerModal.value = false;
  } catch (e) {
    pdvError(e, "Erro ao cadastrar cliente");
  } finally {
    creatingCustomer.value = false;
  }
}

async function addItem(product) {
  if (!currentOrder.value) return;
  configuringProduct.value = product;
  selectedVariationId.value = null;
  selectedAddonIds.value = [];
  configuredQuantity.value = 1;
  configuredNote.value = "";
}

function closeProductOptions() {
  configuringProduct.value = null;
  selectedVariationId.value = null;
  selectedAddonIds.value = [];
  configuredQuantity.value = 1;
  configuredNote.value = "";
}

async function confirmProductOptions() {
  const product = configuringProduct.value;
  if (!product) return;
  const configuration = {
    variations: selectedVariationId.value ? [selectedVariationId.value] : [],
    addons: [...selectedAddonIds.value],
    quantity: configuredQuantity.value,
    customer_note: configuredNote.value.trim(),
  };
  closeProductOptions();
  await addConfiguredItem(product, configuration);
}

async function addConfiguredItem(product, configuration) {
  pendingConfiguration.value = configuration;
  if (product.pricing_unit === "kg") {
    await openWeighModal(product);
    return;
  }
  try {
    await api.post(`/orders/${currentOrder.value.id}/items/`, { product: product.id, ...configuration });
    await refreshCart();
  } catch (e) {
    pdvError(e, "Erro ao adicionar item");
  }
}

// ── Pesagem (produtos por kg) ────────────────────────────────────
async function openWeighModal(product) {
  weighingProduct.value = product;
  scaleReading.value = null;
  manualWeight.value = "";
  weighError.value = "";
  const restaurantId = resolvedRestaurantId.value || currentOrder.value?.restaurant;
  try {
    if (loadedScaleBranchId.value !== restaurantId) {
      loadingScales.value = true;
      const res = await api.get("/scales/", { params: { restaurant: restaurantId, is_active: true, page_size: 100 } });
      scales.value = res.data.results || res.data;
      loadedScaleBranchId.value = restaurantId;
    }
    selectedScale.value = scales.value.length === 1 ? scales.value[0] : null;
    if (selectedScale.value) await readScale();
  } catch {
    scales.value = [];
    selectedScale.value = null;
    weighError.value = "Não foi possível buscar as balanças deste restaurante.";
  } finally {
    loadingScales.value = false;
  }
}

async function resumeTableOrder(order) {
  currentOrder.value = order;
  discount.value = Number(order.discount || 0);
  discountInput.value = discount.value.toFixed(2);
  serviceFeeEnabled.value = order.service_fee_enabled !== false;
  await refreshCart();
  // Editar sempre abre a tela do PEDIDO (montar/editar itens) — inclusive quando
  // já está "aguardando pagamento". O caminho para o pagamento é o botão
  // "Fechar conta" (goToClose), que recarrega as formas e os pagamentos.
  navigateStep("order", { query: { order: order.id } });
}

function scaleLabel(scale) {
  return [scale.name, scale.sector_name, scale.port].filter(Boolean).join(" · ");
}

async function selectScale() {
  scaleReading.value = null;
  manualWeight.value = "";
  weighError.value = "";
  if (selectedScale.value) await readScale();
}

async function readScale() {
  if (!selectedScale.value) return;
  readingScale.value = true;
  weighError.value = "";
  try {
    const res = await api.get(`/scales/${selectedScale.value.id}/latest-reading/`);
    scaleReading.value = res.data;
    manualWeight.value = "";
  } catch (e) {
    scaleReading.value = null;
    weighError.value = e.response?.data?.detail || "Falha ao ler a balanca.";
  } finally {
    readingScale.value = false;
  }
}

const weighKg = computed(() => {
  if (scaleReading.value) return Number(scaleReading.value.net_weight_kg ?? scaleReading.value.weight_kg);
  const manual = parseFloat(String(manualWeight.value).replace(",", "."));
  return Number.isFinite(manual) && manual > 0 ? manual : 0;
});

const weighTotal = computed(() => {
  if (!weighingProduct.value) return 0;
  return weighKg.value * Number(weighingProduct.value.current_price);
});

async function confirmWeigh() {
  if (!weighingProduct.value || !weighKg.value) return;
  confirmingWeigh.value = true;
  weighError.value = "";
  const payload = { product: weighingProduct.value.id, ...pendingConfiguration.value };
  if (scaleReading.value) payload.scale_reading = scaleReading.value.id;
  else payload.weight_kg = weighKg.value.toFixed(3);
  try {
    await api.post(`/orders/${currentOrder.value.id}/items/`, payload);
    weighingProduct.value = null;
    await refreshCart();
  } catch (e) {
    const data = e.response?.data;
    weighError.value = data?.detail || (Array.isArray(data) ? data.join(" ") : "Erro ao lancar item pesado.");
  } finally {
    confirmingWeigh.value = false;
  }
}

function qtyLabel(item) {
  if (item.pricing_unit === "kg") return `${Number(item.quantity).toFixed(3)} kg`;
  return `${Number(item.quantity)}x`;
}

function itemExtras(item) {
  const variations = (item.variations || []).map((v) => typeof v === "string" ? v : v.name).filter(Boolean);
  const addons = (item.addons || []).map((a) => a.addon_name || a.name).filter(Boolean);
  return [...variations, ...addons].join(" · ");
}


async function voidItem(item) {
  itemToVoid.value = item;
  itemVoidReason.value = "";
}

function closeVoidItemDialog() {
  if (voidingItem.value) return;
  itemToVoid.value = null;
  itemVoidReason.value = "";
}

async function confirmVoidItem() {
  if (!itemToVoid.value || !itemVoidReason.value.trim()) return;
  voidingItem.value = true;
  try {
    await api.delete(`/orders/${currentOrder.value.id}/items/${itemToVoid.value.id}/void/`, {
      data: { reason: itemVoidReason.value.trim() },
    });
    voidingItem.value = false;
    closeVoidItemDialog();
    await refreshCart();
  } catch (e) {
    pdvError(e, "Erro ao cancelar item");
  } finally {
    voidingItem.value = false;
  }
}

useRealtimeResource(
  ["orders.order", "orders.orderitem", "restaurants.table", "restaurants.command"],
  async (payload) => {
    if (payload.resource === "restaurants.table") return loadTables();
    if (payload.resource === "restaurants.command") return loadCommands();
    if (currentOrder.value?.id) await refreshCart();
  },
  { debounce: 160 },
);

async function refreshCart() {
  const [itemsRes, orderRes] = await Promise.all([
    api.get(`/orders/${currentOrder.value.id}/items/`),
    api.get(`/orders/${currentOrder.value.id}/`),
  ]);
  cartItems.value = Array.isArray(itemsRes.data) ? itemsRes.data : (itemsRes.data.results || []);
  currentOrder.value = orderRes.data;
}

async function goToClose() {
  await loadPaymentMethods();
  try {
    if (pendingItems.value.length) {
      sendingKitchen.value = true;
      await api.post(`/orders/${currentOrder.value.id}/send-to-kitchen/`);
    }
    const res = await api.post(`/orders/${currentOrder.value.id}/close/`, {
      discount: discount.value || 0,
      service_fee_enabled: serviceFeeEnabled.value,
      expected_total: orderPreviewTotal.value.toFixed(2),
    });
    currentOrder.value = res.data;
  } catch (e) {
    pdvError(e, "Erro ao fechar pedido");
    return;
  } finally {
    sendingKitchen.value = false;
  }
  // Load existing payments
  await refreshPayments();
  amountReceived.value = remainingAmount.value;
  navigateStep("close");
  mobileCartOpen.value = false;
  mobilePaymentSummaryOpen.value = false;
  initKeypad();
}

async function refreshPayments() {
  try {
    const res = await api.get(`/orders/${currentOrder.value.id}/payments/`);
    registeredPayments.value = Array.isArray(res.data) ? res.data : (res.data.results || []);
  } catch {
    registeredPayments.value = [];
  }
}

async function addPayment() {
  if (!canAddPayment.value) return;
  paying.value = true;
  payError.value = "";
  try {
    await api.post(`/orders/${currentOrder.value.id}/pay/`, {
      payment_method: selectedPaymentMethod.value.id,
      amount: amountReceived.value,
    });
    await Promise.all([refreshPayments(), refreshCart()]);
    selectedPaymentMethod.value = null;
    amountReceived.value = remainingAmount.value;
  } catch (e) {
    payError.value = e.response?.data?.detail?.[0] || e.response?.data?.detail || "Erro ao registrar pagamento.";
  } finally {
    paying.value = false;
  }
}

async function confirmPaid() {
  lastPaidSequence.value = currentOrder.value.sequence;
  navigateStep("success");
}

/* ── Teclado de pagamento ────────────────────────────────────────── */
function pressKey(key) {
  payError.value = "";
  let s = padStr.value;
  if (key === ".") {
    if (!s.includes(".")) s = s === "" ? "0." : s + ".";
  } else if (s.includes(".")) {
    // Limita a 2 casas decimais.
    const dec = s.split(".")[1] || "";
    if (dec.length < 2) s += key.slice(0, 2 - dec.length);
  } else {
    s = s === "0" ? key : s + key;
  }
  padStr.value = s;
}
function backspaceKey() {
  padStr.value = padStr.value.slice(0, -1);
}
/** Prepara o teclado ao entrar na tela de pagamento. */
function initKeypad() {
  padStr.value = "";
  payError.value = "";
  // Forma padrão: dinheiro, senão a primeira cadastrada.
  selectedPaymentMethod.value = paymentMethods.value.find((m) => m.method_type === "cash") || paymentMethods.value[0] || null;
}
async function confirmKeypadPayment() {
  if (!canConfirmKeypad.value) return;
  const method = selectedPaymentMethod.value; // addPayment zera; guardamos p/ pagamento dividido
  amountReceived.value = effectiveAmount.value;
  await addPayment();
  if (payError.value) return; // falhou: mantém o valor digitado
  padStr.value = "";
  if (remainingAmount.value <= 0) { confirmPaid(); return; }
  selectedPaymentMethod.value = method;
}
/** Finaliza deixando o pedido pendente (pode ser pago após a refeição). */
function payLater() {
  toast.add({ severity: "info", summary: "Pedido pendente de pagamento", detail: "Pode ser pago depois, ao reabrir o pedido.", life: 3500 });
  newOrder();
}

async function showReceipt() {
  if (!currentOrder.value) return;
  const receiptWindow = window.open("", "_blank", "width=420,height=720");
  if (!receiptWindow) {
    toast.add({ severity: "warn", summary: "Pop-up bloqueado", detail: "Libere pop-ups para exibir o recibo.", life: 4000 });
    return;
  }
  receiptWindow.document.write("<p style='font-family:sans-serif;padding:24px'>Carregando recibo...</p>");
  printingOrder.value = true;
  try {
    const { data } = await api.post(`/orders/${currentOrder.value.id}/print/`, { job_type: "receipt" });
    receiptWindow.document.open();
    receiptWindow.document.write(data.html || "<p>Recibo indisponível.</p>");
    receiptWindow.document.close();
    receiptWindow.focus();
  } catch (e) {
    receiptWindow.close();
    pdvError(e, "Erro ao exibir recibo");
  } finally {
    printingOrder.value = false;
  }
}

async function cancelOrder() {
  if (!cancelReason.value) return;
  cancelling.value = true;
  try {
    await api.post(`/orders/${currentOrder.value.id}/cancel/`, { reason: cancelReason.value });
    showCancelModal.value = false;
    newOrder();
  } catch (e) {
    pdvError(e, "Erro ao cancelar pedido");
  } finally {
    cancelling.value = false;
  }
}

function newOrder() {
  navigateStep("type", { query: { order: null } });
  orderType.value = null;
  selectedTable.value = null;
  selectedCommand.value = null;
  showCommandTableDialog.value = false;
  commandTableSelectionTouched.value = false;
  commandSearch.value = "";
  selectedCustomer.value = null;
  currentOrder.value = null;
  cartItems.value = [];
  discount.value = 0;
  discountInput.value = "0.00";
  serviceFeeEnabled.value = true;
  selectedPaymentMethod.value = null;
  amountReceived.value = 0;
  payError.value = "";
  cancelReason.value = "";
  productSearch.value = "";
  customerSearch.value = "";
  customers.value = [];
  registeredPayments.value = [];
  mobileCartOpen.value = false;
  mobilePaymentSummaryOpen.value = false;
  profileCache = null;
}

async function deletePayment(payment) {
  if (!currentOrder.value || deletingPaymentId.value) return;
  deletingPaymentId.value = payment.id;
  payError.value = "";
  try {
    await api.delete(`/orders/${currentOrder.value.id}/payments/${payment.id}/`);
    await Promise.all([refreshPayments(), refreshCart()]);
    padStr.value = "";
    amountReceived.value = remainingAmount.value;
    toast.add({ severity: "success", summary: "Pagamento excluído", detail: "O saldo do pedido e do caixa foi atualizado.", life: 3000 });
  } catch (e) {
    payError.value = e.response?.data?.detail?.[0] || e.response?.data?.detail || "Erro ao excluir pagamento.";
  } finally {
    deletingPaymentId.value = null;
  }
}

function confirmNote() {
  addingNoteFor.value = null;
  pendingNote.value = "";
}

function itemStatusLabel(s) {
  return { pending: "Pendente", sent: "Cozinha", preparing: "Preparo", ready: "Pronto", delivered: "Entregue", cancelled: "Cancelado", comped: "Cortesia" }[s] || s;
}

function prodStatusLabel(s) {
  return { idle: "Sem envio", sent_to_kitchen: "Na cozinha", preparing: "Em preparo", partially_ready: "Parcial", ready: "Pronto", delivered: "Entregue" }[s] || s;
}


function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Abre um pedido existente direto na tela de itens (ex.: "Editar no PDV"). */
async function openExistingOrder(orderId, { validateCash = false } = {}) {
  try {
    const res = await api.get(`/orders/${orderId}/`);
    const order = res.data;
    if (["paid", "cancelled", "refunded"].includes(order.status)) {
      toast.add({
        severity: "info",
        summary: "Pedido somente para consulta",
        detail: "Pedidos concluídos ou cancelados não podem ser alterados.",
        life: 3500,
      });
      await router.replace({ name: "pedidos--view", params: { id: order.id } });
      return;
    }
    currentOrder.value = order;
    orderType.value = order.order_type;
    resolvedRestaurantId.value = order.restaurant;
    resolvedBranchId.value = null;
    if (!restaurants.value.some((restaurant) => restaurant.id === order.restaurant)) {
      const restaurantResponse = await api.get(`/restaurants/${order.restaurant}/`);
      restaurants.value = [restaurantResponse.data, ...restaurants.value];
    }
    if (validateCash) {
      await validatePdvCashAccess();
      if (pdvBlocked.value) return;
    }
    await loadProducts();
    await refreshCart();
    navigateStep("order", { replace: true, query: { order: order.id } });
  } catch (e) {
    pdvGateLoading.value = false;
    pdvError(e, "Não foi possível abrir o pedido");
  }
}

watch(
  () => route.query.step,
  (urlStep) => {
    if (typeof urlStep !== "string" || !PDV_STEPS.has(urlStep) || urlStep === step.value) return;
    // Durante a mesma sessão o estado do pedido permanece em memória; o
    // histórico do navegador pode então alternar entre pedido e pagamento.
    if (["order", "close", "success"].includes(urlStep) && !currentOrder.value) return;
    step.value = urlStep;
    mobileCartOpen.value = false;
    mobilePaymentSummaryOpen.value = false;
  },
);

onMounted(async () => {
  window.addEventListener("online", updateBrowserConnection);
  window.addEventListener("offline", updateBrowserConnection);
  const requestedStep = typeof route.query.step === "string" ? route.query.step : null;

  // Em edição, o restaurante vem do pedido. O admin em escopo "Todos" não
  // precisa passar pela seleção de restaurante antes de abrir os itens.
  const requestedOrderId = props.orderId || route.query.order;
  if (requestedOrderId) {
    const profile = await loadProfile();
    isAdmin.value = Boolean(profile?.is_superuser || profile?.profile_type === "admin" || profile?.profile_type === "owner");
    if (isAdmin.value) await loadRestaurants();
    await openExistingOrder(requestedOrderId, { validateCash: true });
    if (pdvBlocked.value || !currentOrder.value) return;
    if (requestedStep === "close") {
      await Promise.all([loadPaymentMethods(), refreshPayments()]);
      amountReceived.value = remainingAmount.value;
      initKeypad();
      navigateStep("close", { replace: true });
    } else if (requestedStep === "success") {
      lastPaidSequence.value = currentOrder.value.sequence;
      navigateStep("success", { replace: true });
    }
    return;
  }

  await resolveContext();
  // applyRestaurant(), chamado por resolveContext(), já validou o caixa.
  if (!resolvedRestaurantId.value) pdvGateLoading.value = false;
  if (pdvBlocked.value) return;
  navigateStep(step.value, { replace: true });
});

onBeforeUnmount(() => {
  window.removeEventListener("online", updateBrowserConnection);
  window.removeEventListener("offline", updateBrowserConnection);
});
</script>

<style scoped>
.pdv {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}
.pdv__gate { position: absolute; inset: 0; z-index: 100; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 32px; text-align: center; background: var(--surface-card); }
.pdv__gate>i { font-size: 2rem; color: var(--primary-color); }
.pdv__gate>span { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 50%; background: #fee2e2; color: #b91c1c; font-size: 1.5rem; }
.pdv__gate h2,.pdv__gate p { margin: 0; }
.pdv__gate p { max-width: 520px; color: var(--text-muted); line-height: 1.5; }

/* ── Steps ──────────────────────────────────────────────────── */
.pdv__step {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.pdv__step-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pdv__step-header h2 {
  font: var(--weight-extra) 22px/1.15 var(--font-sans);
  color: var(--text-strong);
  margin: 0;
}

.pdv__step-header p {
  font: var(--weight-medium) 14px/1.5 var(--font-sans);
  color: var(--text-muted);
  margin: 0;
}

.pdv__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 4px;
}
.pdv__back:hover { color: var(--text-body); }

/* ── Type selection ─────────────────────────────────────────── */
.pdv__type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: 14px;
}

.pdv__type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 16px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
  color: var(--text-body);
}
.pdv__type-card:hover {
  border-color: var(--brand-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.pdv__type-card--selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 18%, transparent), var(--shadow-sm);
}
.pdv__type-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--brand-subtle);
  color: var(--text-brand);
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.pdv__type-icon .pi { font-size: 24px; }
.pdv__type-card--selected .pdv__type-icon { background: var(--brand); color: #fff; }
.pdv__type-card strong { font: var(--weight-bold) 15px/1 var(--font-sans); color: var(--text-strong); }
.pdv__type-card small { font: var(--weight-medium) 11.5px/1.4 var(--font-sans); color: var(--text-muted); text-align: center; }

/* ── Tables ─────────────────────────────────────────────────── */
.pdv__tables { display: flex; flex-direction: column; gap: 14px; }

.pdv__tables-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.pdv__search-box--sm { height: 36px; width: 260px; max-width: 100%; }
.pdv__tables-count {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: var(--weight-bold) 12px/1 var(--font-sans);
  color: var(--text-muted);
}

.pdv__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pdv__dot--free { background: var(--success); box-shadow: 0 0 0 3px var(--success-subtle); }

.pdv__table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 12px;
}
.pdv__table-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  color: var(--text-body);
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.pdv__table-card:hover {
  border-color: var(--brand-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.pdv__table-card--selected {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 18%, transparent), var(--shadow-sm);
}
/* Enquanto o pedido está sendo aberto: cards desabilitados; o clicado "pulsa". */
.pdv__table-card:disabled { cursor: default; }
.pdv__table-card:disabled:not(.pdv__table-card--busy) { opacity: 0.55; }
.pdv__table-card:disabled:hover { transform: none; box-shadow: none; border-color: var(--border); }
.pdv__table-card--busy { animation: pdv-card-pulse 0.9s ease-in-out infinite; }
@keyframes pdv-card-pulse {
  0%, 100% { box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 30%, transparent); }
  50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--brand) 12%, transparent); }
}

.pdv__table-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.pdv__table-status {
  flex-shrink: 0;
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--success-text);
}
/* Cor do status por estado + faixa lateral (mesas ocupadas continuam clicáveis para editar) */
.pdv__table-card--occupied { border-left: 3px solid #b91c1c; }
.pdv__table-card--reserved { border-left: 3px solid #1d4ed8; }
.pdv__table-card--cleaning { border-left: 3px solid #b45309; }
.pdv__table-card--free { border-left: 3px solid #047857; }
.pdv__table-card--occupied .pdv__table-status { color: var(--danger-text); }
.pdv__table-card--reserved .pdv__table-status { color: var(--info-text); }
.pdv__table-card--cleaning .pdv__table-status { color: var(--warning-text); }

.pdv__table-number {
  font: var(--weight-extra) 26px/1 var(--font-sans);
  color: var(--text-strong);
  letter-spacing: var(--tracking-tight);
}

.pdv__table-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pdv__table-meta small {
  font: var(--weight-semibold) 11.5px/1.3 var(--font-sans);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Customer search ─────────────────────────────────────────── */
.pdv__search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 40px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-muted);
}
.pdv__search-box input {
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font: var(--weight-medium) 13.5px/1 var(--font-sans);
  color: var(--text-body);
}
.pdv__customer-search { display: flex; flex-direction: column; gap: 10px; }
.pdv__customer-searchbar { display: flex; align-items: stretch; gap: 10px; }
.pdv__customer-searchbar .pdv__search-box { flex: 1; }
.pdv__customer-searchbar .pdv__btn { flex-shrink: 0; height: 40px; }
.pdv__link-btn { align-self: center; background: none; border: none; padding: 0; color: var(--text-brand); font: var(--weight-bold) 13px/1.4 var(--font-sans); cursor: pointer; text-decoration: underline; }
.pdv__field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.pdv__field-row--address { grid-template-columns: minmax(0, 1fr) 92px; }
.pdv__field-row--city { grid-template-columns: minmax(0, 1fr) 72px; }
.pdv__modal-section-title { padding-top: 6px; color: var(--text-strong); font: var(--weight-extra) 13px/1 var(--font-sans); border-top: 1px solid var(--border-subtle); }
.pdv__field-label { display: flex; align-items: center; justify-content: space-between; color: var(--text-strong); font: var(--weight-bold) 12px/1 var(--font-sans); }
.pdv__field-label small { color: var(--brand); font-size: 10px; text-transform: uppercase; }
.pdv__modal-input { width: 100%; height: 42px; padding: 0 12px; box-sizing: border-box; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body); font: var(--weight-medium) 13.5px/1 var(--font-sans); }
.pdv__modal-input:focus { outline: none; border-color: var(--ring); box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 20%, transparent); }
.pdv__customer-list { display: flex; flex-direction: column; gap: 4px; max-height: 240px; overflow-y: auto; }
.pdv__customer-option {
  display: flex; flex-direction: column; gap: 2px; padding: 10px 14px;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer; text-align: left; color: var(--text-body);
}
.pdv__customer-option:hover,
.pdv__customer-option--selected { background: var(--brand-subtle); border-color: var(--brand); }
.pdv__customer-option strong { font: var(--weight-bold) 13px/1 var(--font-sans); }
.pdv__customer-option small { font: var(--weight-medium) 11.5px/1 var(--font-sans); color: var(--text-muted); }

/* ── Order step ─────────────────────────────────────────────── */
.pdv__order {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 340px;
  min-height: 0;
  overflow: hidden;
}

.pdv__order--editing { grid-template-rows: auto 1fr; }
.pdv__edit-banner {
  grid-column: 1 / -1; display: flex; align-items: center; gap: 10px;
  margin: 12px 14px 6px; padding: 14px 16px;
  color: var(--text-brand); background: var(--brand-subtle); border-radius: var(--radius-lg);
}
.pdv__edit-banner span { display: flex; flex-direction: column; gap: 2px; }
.pdv__edit-banner small { color: var(--text-muted); font-size: 11px; }

.pdv__menu-col { display: flex; flex-direction: column; overflow: hidden; }
.pdv__menu-top {
  padding: 14px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.pdv__category-select {
  width: 100%; height: 38px; padding: 0 10px; color: var(--text-body);
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-md);
  font: var(--weight-semibold) 12.5px/1 var(--font-sans);
}

.pdv__products { flex: 1; overflow-y: auto; padding: 14px 16px; }

/* Grade de produtos (sem imagem): nome no topo · preço + adicionar no rodapé */
.pdv__product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
  align-content: start;
}
.pdv__product-card {
  display: flex; flex-direction: column; justify-content: space-between; gap: 12px;
  min-height: 96px; padding: 12px 14px;
  background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg);
  cursor: pointer; text-align: left; color: var(--text-body);
  box-shadow: var(--shadow-xs);
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.pdv__product-card:hover:not(:disabled) { border-color: var(--brand-border); box-shadow: var(--shadow-md); transform: translateY(-2px); }
.pdv__product-card:active:not(:disabled) { transform: translateY(0); }
.pdv__product-card:disabled { opacity: 0.5; cursor: not-allowed; }
.pdv__product-card-head { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.pdv__product-card-name {
  font: var(--weight-bold) 13.5px/1.3 var(--font-sans); color: var(--text-strong);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pdv__product-card-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pdv__product-card-price { font: var(--weight-extra) 14px/1 var(--font-sans); color: var(--text-brand); white-space: nowrap; }
.pdv__product-add {
  flex-shrink: 0;
  display: grid; place-items: center; width: 26px; height: 26px;
  border-radius: 50%; background: var(--brand); color: #fff;
}
.pdv__inactive { align-self: flex-start; font: var(--weight-medium) 10.5px/1 var(--font-sans); color: var(--text-muted); background: var(--surface-sunken); border-radius: 4px; padding: 2px 5px; }

/* ── Cart ───────────────────────────────────────────────────── */
.pdv__cart-col { display: flex; flex-direction: column; overflow: hidden; background: var(--surface-card); border-radius: var(--radius-lg); }

.pdv__cart-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pdv__order-info { display: flex; flex-direction: column; gap: 2px; }
.pdv__order-info strong { font: var(--weight-extra) 15px/1 var(--font-sans); color: var(--text-strong); }
.pdv__order-info span { font: var(--weight-medium) 12px/1 var(--font-sans); color: var(--text-muted); }

.pdv__order-badges { display: flex; gap: 6px; flex-wrap: wrap; }
.pdv__badge {
  padding: 3px 8px; border-radius: var(--radius-pill);
  font: var(--weight-bold) 10px/1 var(--font-sans);
}
.pdv__prod--idle { background: var(--surface-active); color: var(--text-muted); }
.pdv__prod--sent_to_kitchen { background: #fef3c7; color: #92400e; }
.pdv__prod--preparing { background: #dbeafe; color: #1d4ed8; }
.pdv__prod--partially_ready { background: #fce7f3; color: #9d174d; }
.pdv__prod--ready { background: #d1fae5; color: #065f46; }
.pdv__prod--delivered { background: #e0e7ff; color: #3730a3; }

.pdv__cart-items { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }

.pdv__cart-section-label {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 6px;
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-top: 4px;
}
.pdv__cart-section-label--pending { color: var(--brand); }

.pdv__cart-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
  color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans);
}

.pdv__cart-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: var(--surface-sunken);
  border-radius: var(--radius-sm);
}
.pdv__cart-item--sent { opacity: 0.85; }

.pdv__cart-item-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.pdv__cart-item-info strong { font: var(--weight-bold) 12.5px/1.3 var(--font-sans); color: var(--text-strong); }
.pdv__cart-item-info small { font: var(--weight-medium) 11px/1.3 var(--font-sans); color: var(--text-muted); }

.pdv__cart-item-meta { display: flex; align-items: center; gap: 5px; margin-top: 2px; }
.pdv__batch-tag {
  padding: 1px 6px; border-radius: 3px;
  background: var(--brand-subtle); color: var(--text-brand);
  font: var(--weight-bold) 10px/1.4 var(--font-sans);
}

.pdv__cart-item-status {
  font: var(--weight-bold) 10px/1 var(--font-sans); text-transform: uppercase;
  padding: 2px 5px; border-radius: 4px; width: fit-content;
}
.pdv__status--pending { background: var(--surface-active); color: var(--text-muted); }
.pdv__status--sent { background: #fef3c7; color: #92400e; }
.pdv__status--preparing { background: #dbeafe; color: #1d4ed8; }
.pdv__status--ready { background: #d1fae5; color: #065f46; }
.pdv__status--delivered { background: #e0e7ff; color: #3730a3; }
.pdv__status--cancelled { background: #fee2e2; color: #991b1b; }
.pdv__status--comped { background: #fce7f3; color: #9d174d; }

.pdv__cart-item-right { display: flex; align-items: flex-end; gap: 6px; flex-shrink: 0; }

.pdv__cart-item-price { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.pdv__cart-item-price span { font: var(--weight-medium) 11px/1 var(--font-sans); color: var(--text-muted); }
.pdv__cart-item-price strong { font: var(--weight-bold) 13px/1 var(--font-sans); color: var(--text-strong); }
.pdv__price--comped { text-decoration: line-through; color: var(--text-muted); }

.pdv__void-btn {
  width: 26px; height: 26px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: var(--surface-card); color: var(--text-muted); cursor: pointer;
  flex-shrink: 0;
}
.pdv__void-btn:hover { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }

.pdv__cart-totals {
  padding: 10px 12px;
  border-top: 1px solid var(--border-subtle);
  display: flex; flex-direction: column; gap: 5px; flex-shrink: 0;
}

.pdv__total-row {
  display: flex; justify-content: space-between;
  font: var(--weight-medium) 13px/1 var(--font-sans); color: var(--text-body);
}
.pdv__total-row--discount { color: var(--success-text, #065f46); }
.pdv__service-fee-toggle { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 13px; font-weight: 700; cursor: pointer; }
.pdv__service-fee-toggle input { width: 17px; height: 17px; accent-color: var(--primary-color); }
.pdv__total-row--total {
  font: var(--weight-extra) 16px/1 var(--font-sans); color: var(--text-strong);
  padding-top: 5px; border-top: 1px solid var(--border-subtle);
}

.pdv__cart-actions {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px; border-top: 1px solid var(--border); flex-shrink: 0;
}
.pdv__mobile-panel-trigger,
.pdv__mobile-panel-close,
.pdv__mobile-payment-actions { display: none; }

/* ── Close step ─────────────────────────────────────────────── */
.pdv__step--close { max-width: 960px; gap: 28px; padding: 32px 28px; }
.pdv__close-body { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr); gap: 28px; align-items: start; }
.pdv__close-left, .pdv__close-right { display: flex; flex-direction: column; gap: 18px; }

.pdv__close-section {
  display: flex; flex-direction: column; gap: 14px; padding: 18px;
  background: var(--surface-card); border: 1px solid var(--border-subtle); border-radius: var(--radius-lg);
}
.pdv__close-section h4 {
  font: var(--weight-bold) 12px/1 var(--font-sans); text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-subtle); margin: 0;
}

.pdv__close-items { display: flex; flex-direction: column; gap: 8px; }
.pdv__close-item {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--surface-sunken); border-radius: var(--radius-md);
  font: var(--weight-medium) 13px/1.4 var(--font-sans); color: var(--text-body);
}
.pdv__close-item-qty {
  min-width: 38px; padding: 5px 7px; text-align: center; color: var(--text-brand);
  background: var(--brand-subtle); border-radius: var(--radius-sm); font-weight: var(--weight-bold);
}
.pdv__close-item-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pdv__close-item-info strong { color: var(--text-strong); }
.pdv__close-item-info small { color: var(--text-muted); font-size: 11px; }
.pdv__close-item-price { color: var(--text-strong); white-space: nowrap; }
.pdv__close-item--comped { color: var(--text-muted); font-style: italic; }

.pdv__close-totals {
  display: flex; flex-direction: column; gap: 6px;
  padding: 12px; background: var(--surface-sunken); border-radius: var(--radius-md);
}

.pdv__discount-row { position: relative; display: flex; align-items: center; width: 100%; }
.pdv__currency-prefix {
  position: absolute; left: 16px; z-index: 1; pointer-events: none;
  color: var(--text-muted); font: var(--weight-bold) 14px/1 var(--font-sans);
}
.pdv__discount-input {
  width: 100%; height: 52px; padding: 0 16px 0 48px; box-sizing: border-box;
  font-size: 18px; line-height: 1.2;
}
.pdv__close-input {
  height: 42px; padding: 0 12px; border: 1px solid var(--border);
  border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 14px/1 var(--font-sans); flex: 1;
}
.pdv__close-input.pdv__discount-input,
.pdv__close-input.pdv__close-input--large {
  width: 100%; height: 52px; padding: 0 16px 0 52px; box-sizing: border-box;
  font-size: 18px; line-height: 1.2;
}
.pdv__close-input--large {
  flex: none;
}

.pdv__change { font: var(--weight-semibold) 14px/1 var(--font-sans); color: var(--text-muted); margin-top: 4px; }
.pdv__change strong { color: var(--brand); }
.pdv__amount-field { display: flex; flex-direction: column; gap: 10px; }
.pdv__amount-field h4 { margin: 0; }
.pdv__currency-field { position: relative; display: flex; align-items: center; width: 100%; }

.pdv__payment-methods { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; }
.pdv__payment-btn {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 12px 8px; border: 2px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 12px/1 var(--font-sans); cursor: pointer; transition: all 0.12s;
}
.pdv__payment-btn:hover { border-color: var(--brand); }
.pdv__payment-btn--selected { border-color: var(--brand); background: var(--brand-subtle); color: var(--brand); }

/* Payments history in close step */
.pdv__payment-history { display: flex; flex-direction: column; gap: 4px; }
.pdv__payment-record {
  display: flex; justify-content: space-between; align-items: center;
  padding: 7px 10px; background: var(--surface-sunken); border-radius: var(--radius-sm);
  font: var(--weight-medium) 13px/1 var(--font-sans); color: var(--text-body);
}
.pdv__payment-record strong { font-weight: var(--weight-bold); color: var(--text-strong); }

.pdv__remaining-row {
  display: flex; justify-content: space-between;
  font: var(--weight-bold) 14px/1 var(--font-sans); color: var(--text-body);
  padding: 8px 2px 0;
}
.pdv__remaining--paid { color: #065f46; }
.pdv__remaining--due { color: #92400e; }

.pdv__paid-confirm {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  padding: 24px; background: #d1fae5; border-radius: var(--radius-lg);
  color: #065f46; text-align: center;
}
.pdv__paid-confirm p { font: var(--weight-bold) 14px/1 var(--font-sans); margin: 0; }

/* ── Pagamento (teclado PDV) ────────────────────────────────── */
.pdv__pay { flex: 1; display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: 0; overflow: hidden; }
.pdv__pay-summary { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; overflow-y: auto; border-right: 1px solid var(--border-subtle); }
.pdv__pay-order { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.pdv__pay-order strong { display: block; font: var(--weight-extra) 16px/1.2 var(--font-sans); color: var(--text-strong); }
.pdv__pay-order small { color: var(--text-muted); font: var(--weight-medium) 12px/1 var(--font-sans); }
.pdv__pay-order > span { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.pdv__pay-items { display: flex; flex-direction: column; }
.pdv__pay-item { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); }
.pdv__pay-item-qty { min-width: 30px; text-align: center; color: var(--text-brand); font: var(--weight-bold) 13px/1 var(--font-sans); }
.pdv__pay-item-info { display: flex; flex-direction: column; min-width: 0; }
.pdv__pay-item-info strong { font: var(--weight-semibold) 13px/1.3 var(--font-sans); color: var(--text-strong); }
.pdv__pay-item-info small { color: var(--text-muted); font-size: 11px; }
.pdv__pay-item-price { color: var(--text-strong); white-space: nowrap; font-size: 13px; }
.pdv__pay-item--comped { opacity: 0.7; font-style: italic; }
.pdv__pay-totals { display: flex; flex-direction: column; gap: 6px; padding-top: 4px; }
.pdv__pay-row { display: flex; align-items: center; justify-content: space-between; font: var(--weight-medium) 13px/1.4 var(--font-sans); color: var(--text-body); }
.pdv__pay-row--grand { padding-top: 8px; border-top: 1px solid var(--border-subtle); color: var(--text-strong); }
.pdv__pay-row--grand span { font: var(--weight-extra) 16px/1 var(--font-sans); }
.pdv__pay-row--grand strong { font: var(--weight-extra) 20px/1 var(--font-sans); }
.pdv__pay-row--discount .pdv__discount-mini { position: relative; display: flex; align-items: center; width: 130px; }
.pdv__discount-mini .pdv__currency-prefix { left: 10px; font-size: 12px; }
.pdv__discount-mini .pdv__discount-input { width: 100%; height: 34px; font-size: 14px; padding: 0 10px 0 30px; text-align: right; }
.pdv__pay-registered { display: flex; flex-direction: column; gap: 5px; padding: 8px 0; border-top: 1px solid var(--border-subtle); }
.pdv__pay-registered-title { color: var(--text-subtle); font: var(--weight-bold) 10.5px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.pdv__pay-registered-row { display: flex; justify-content: space-between; font: var(--weight-semibold) 12.5px/1 var(--font-sans); color: var(--text-body); }
.pdv__pay-registered-row strong { color: var(--text-strong); }
.pdv__pay-registered-row > span { display: flex; flex: 1; flex-direction: column; gap: 3px; }
.pdv__pay-registered-row > span small { color: var(--success-text); font-size: 11px; }
.pdv__pay-registered-entry {
  min-height: 36px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 36px;
  align-items: center;
  column-gap: 8px;
}
.pdv__pay-registered-entry > span { justify-content: center; }
.pdv__pay-registered-entry > strong { display: flex; align-items: center; justify-content: flex-end; height: 100%; }
.pdv__payment-delete {
  display: grid; place-items: center; width: 32px; height: 32px; margin: 0 auto;
  border: 0; border-radius: var(--radius-sm); background: transparent;
  color: var(--danger); cursor: pointer;
}
.pdv__payment-delete:hover { background: var(--danger-subtle); }
.pdv__payment-delete:disabled { cursor: not-allowed; opacity: .45; }
.pdv__pay-registered-remaining { padding-top: 5px; border-top: 1px dashed var(--border-subtle); }
.pdv__pay-balance { display: flex; flex-direction: column; gap: 4px; padding: 10px 0 0; border-top: 1px solid var(--border-subtle); }
.pdv__pay-balance strong { font-weight: var(--weight-extra); }
.pdv__balance--change { color: var(--success-text); }
.pdv__balance--due { color: var(--text-strong); }
.pdv__pay-summary-actions { margin-top: auto; display: grid; grid-template-columns: auto 1fr; gap: 10px; padding-top: 8px; }
.pdv__pay-summary-actions .pdv__btn { height: 48px; }
.pdv__pay-print { width: 100%; min-height: 44px; flex-shrink: 0; }

.pdv__pay-keypad-col { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; background: var(--surface-card); min-height: 0; }
.pdv__payable { display: flex; align-items: center; justify-content: space-between; }
.pdv__payable-value small { display: block; color: var(--text-muted); font: var(--weight-medium) 12px/1 var(--font-sans); }
.pdv__payable-value strong { font: var(--weight-extra) 26px/1.1 var(--font-sans); color: var(--success-text); }
.pdv__pay-method-field { display: flex; flex-direction: column; gap: 5px; }
.pdv__pay-method-field label { color: var(--text-strong); font: var(--weight-bold) 12px/1 var(--font-sans); }
.pdv__pay-select { width: 100%; height: 42px; padding: 0 12px; color: var(--text-body); background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-md); font: var(--weight-semibold) 13.5px/1 var(--font-sans); cursor: pointer; }
.pdv__pay-display { height: 62px; display: flex; align-items: center; justify-content: flex-end; padding: 0 18px; background: var(--surface-sunken); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); font: var(--weight-extra) 30px/1 var(--font-sans); color: var(--text-strong); overflow: hidden; }
.pdv__pay-display--empty { color: var(--text-subtle); }
.pdv__keypad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.pdv__keypad button { width: 100%; height: 52px; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-strong); font: var(--weight-bold) 20px/1 var(--font-sans); cursor: pointer; transition: background var(--dur-fast) var(--ease-out); }
.pdv__keypad button:hover { background: var(--surface-hover); }
.pdv__keypad button:active { background: var(--surface-active); }
.pdv__key-back { color: var(--text-muted); }
.pdv__key-back .pi { font-size: 20px; }

/* ── Success ────────────────────────────────────────────────── */
.pdv__step--success { align-items: center; justify-content: center; text-align: center; padding: 32px; }
.pdv__success-card {
  width: min(100%, 500px); display: flex; flex-direction: column; align-items: center; gap: 22px;
  padding: 40px; background: var(--surface-card); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl, 20px); box-shadow: var(--shadow-md);
}
.pdv__success-icon { display: grid; place-items: center; width: 88px; height: 88px; color: #047857; background: #d1fae5; border-radius: 50%; }
.pdv__success-icon .pi { font-size: 48px; }
.pdv__success-copy { display: flex; flex-direction: column; gap: 8px; }
.pdv__step--success h2 { font: var(--weight-extra) 28px/1.1 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__step--success p { font: var(--weight-medium) 15px/1.5 var(--font-sans); color: var(--text-muted); margin: 0; }
.pdv__success-summary {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px; background: var(--surface-sunken); border-radius: var(--radius-lg);
  color: var(--text-muted); font: var(--weight-semibold) 13px/1 var(--font-sans);
}
.pdv__success-summary strong { color: var(--text-strong); font-size: 20px; }
.pdv__success-summary--change { border-color: var(--success); background: var(--success-subtle); }
.pdv__success-summary--change strong { color: var(--success-text); }
.pdv__fiscal-key { font-size: 13px !important; font-family: var(--font-mono, monospace); letter-spacing: 0.5px; }
.pdv__success-fiscal { width: 100%; }
.pdv__success-actions { width: 100%; display: grid; grid-template-columns: 1fr; gap: 10px; }

/* ── Buttons ────────────────────────────────────────────────── */
.pdv__btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 0 18px; height: 42px; border: none; border-radius: var(--radius-md);
  font: var(--weight-bold) 13.5px/1 var(--font-sans); cursor: pointer; transition: all 0.12s;
}
.pdv__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pdv__btn--primary { background: var(--brand); color: #fff; }
.pdv__btn--primary:hover:not(:disabled) { filter: brightness(1.1); }
.pdv__btn--secondary { background: var(--surface-active); color: var(--text-body); border: 1px solid var(--border); }
.pdv__btn--secondary:hover:not(:disabled) { background: var(--border); }
.pdv__btn--danger { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.pdv__btn--danger:hover:not(:disabled) { background: #fca5a5; }
.pdv__btn--ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
.pdv__btn--full { width: 100%; }

/* ── Modals / Overlays ──────────────────────────────────────── */
.pdv__overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.pdv__modal {
  background: var(--surface-card); border-radius: var(--radius-lg);
  padding: 28px; max-width: 420px; width: calc(100% - 40px);
  display: flex; flex-direction: column; gap: 14px; box-shadow: var(--shadow-lg);
}
.pdv__modal--command-table { max-width: 620px; border-radius: 4px; }
.pdv__command-dialog-title { display: flex; align-items: center; gap: 10px; }
.pdv__command-dialog-title > span:last-child { display: flex; flex-direction: column; gap: 2px; }
.pdv__command-dialog-title small {
  color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps); text-transform: uppercase;
}
.pdv__command-dialog-icon {
  width: 34px; height: 34px; display: inline-grid; place-items: center; flex: 0 0 34px;
  border: 1px solid var(--brand-border); border-radius: 4px;
  background: var(--brand-subtle); color: var(--text-brand);
}
.pdv__command-table-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px;
  max-height: min(340px, 45vh); overflow-y: auto; padding: 1px;
}
.pdv__command-table-option {
  min-height: 54px; display: flex; align-items: center; gap: 10px; padding: 9px 11px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--surface-sunken); color: var(--text-body); cursor: pointer; text-align: left;
}
.pdv__command-table-option:hover:not(:disabled) { border-color: var(--brand-border); background: var(--surface-hover); }
.pdv__command-table-option--selected {
  border-color: var(--brand); background: var(--brand-subtle); color: var(--text-brand);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--brand) 18%, transparent);
}
.pdv__command-table-option:disabled { opacity: .55; cursor: not-allowed; }
.pdv__command-table-option > span { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.pdv__command-table-option strong { color: var(--text-strong); font: var(--weight-bold) 13px/1.2 var(--font-sans); }
.pdv__command-table-option small { color: var(--text-muted); font: var(--weight-medium) 11.5px/1.2 var(--font-sans); }
.pdv__modal h3 { font: var(--weight-extra) 18px/1.2 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__modal h4 { font: var(--weight-bold) 14px/1.2 var(--font-sans); color: var(--text-strong); margin: 0; }
.pdv__modal p { font: var(--weight-medium) 13.5px/1.5 var(--font-sans); color: var(--text-muted); margin: 0; }
.pdv__reason-options { display: flex; flex-wrap: wrap; gap: 8px; }
.pdv__reason-option {
  min-height: 34px; padding: 7px 10px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--surface-sunken); color: var(--text-body); cursor: pointer;
  font: var(--weight-semibold) 12px/1.2 var(--font-sans);
}
.pdv__reason-option:hover { border-color: var(--brand); color: var(--text-brand); }
.pdv__reason-option--selected { border-color: var(--brand); background: var(--brand-subtle); color: var(--text-brand); }
.pdv__reason-label { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.pdv__modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
.pdv__modal--options { max-width: 480px; max-height: calc(100vh - 48px); overflow-y: auto; }
.pdv__option-group { display: flex; flex-direction: column; gap: 7px; }
.pdv__option-group h4 { display: flex; justify-content: space-between; }
.pdv__option-group h4 small { color: var(--brand); font-size: 10px; text-transform: uppercase; }
.pdv__option-row {
  min-height: 46px; box-sizing: border-box;
  display: flex; align-items: center; gap: 10px; padding: 0 12px;
  border: 1px solid var(--border); border-radius: var(--radius-md); cursor: pointer;
}
.pdv__option-row input[type="radio"],
.pdv__option-row input[type="checkbox"] {
  width: 18px; height: 18px; flex-shrink: 0; margin: 0; accent-color: var(--brand);
}
.pdv__option-row span { flex: 1; color: var(--text-body); font: var(--weight-semibold) 13px/1.2 var(--font-sans); }
.pdv__option-row strong { color: var(--text-brand); font-size: 12px; }
.pdv__option-warning { padding: 10px 12px; color: var(--warning-text) !important; background: #fef3c7; border-radius: var(--radius-md); }
.pdv__quantity-control {
  display: grid; grid-template-columns: 44px minmax(64px, 1fr) 44px; align-items: center;
  width: 100%; height: 46px; box-sizing: border-box;
  border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden;
}
.pdv__quantity-control button {
  display: grid; place-items: center; height: 44px; border: 0; color: var(--text-brand);
  background: var(--brand-subtle); cursor: pointer;
}
.pdv__quantity-control button:hover:not(:disabled) { background: var(--surface-active); }
.pdv__quantity-control button:disabled { color: var(--text-subtle); cursor: not-allowed; opacity: .55; }
.pdv__quantity-control strong { text-align: center; color: var(--text-strong); font-size: 17px; }

.pdv__note-input {
  resize: vertical; padding: 10px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-medium) 13.5px/1.5 var(--font-sans); width: 100%; box-sizing: border-box;
}

/* ── Pesagem ────────────────────────────────────────────────── */
.pdv__modal--weigh { max-width: 380px; }
.pdv__modal--weigh h4 { display: flex; align-items: center; gap: 8px; }
.pdv__weigh-scale-row { display: flex; flex-direction: column; gap: 6px; }
.pdv__weigh-scale-row label { color: var(--text-strong); font: var(--weight-bold) 12px/1 var(--font-sans); }
.pdv__weigh-scale-row small { color: var(--warning-text); font: var(--weight-medium) 11.5px/1.4 var(--font-sans); }
.pdv__weigh-scale-row select { width: 100%; flex: none; padding: 0 38px 0 14px; cursor: pointer; }
.pdv__weigh-display {
  display: flex; align-items: baseline; justify-content: center; gap: 8px;
  padding: 18px 0; border-radius: var(--radius-md);
  background: var(--surface-ground, #f4f4f5); border: 1px dashed var(--border);
}
.pdv__weigh-display strong {
  font: var(--weight-extra) 40px/1 var(--font-mono, monospace);
  color: var(--text-muted); letter-spacing: 1px;
}
.pdv__weigh-display span { font: var(--weight-bold) 16px/1 var(--font-sans); color: var(--text-muted); }
.pdv__weigh-display--ok strong { color: var(--text-strong); }
.pdv__weigh-meta { text-align: center; font: var(--weight-medium) 12px/1.4 var(--font-sans); color: var(--text-muted); }
.pdv__weigh-actions { display: flex; gap: 10px; align-items: center; }
.pdv__weigh-manual { flex: 1; }
.pdv__weigh-total {
  display: flex; justify-content: space-between; align-items: center;
  padding-top: 10px; border-top: 1px solid var(--border);
  font: var(--weight-bold) 15px/1 var(--font-sans); color: var(--text-strong);
}
.pdv__weigh-error {
  padding: 8px 12px; background: #fee2e2; color: #991b1b;
  border-radius: var(--radius-sm); font: var(--weight-semibold) 12.5px/1.4 var(--font-sans);
}

/* ── Misc ───────────────────────────────────────────────────── */
.pdv__loading { padding: 20px; text-align: center; color: var(--text-muted); font: var(--weight-medium) 13px/1 var(--font-sans); }
.pdv__empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 20px; text-align: center; color: var(--text-muted); font: var(--weight-medium) 13px/1.4 var(--font-sans); grid-column: 1/-1; }
.pdv__error { padding: 10px 14px; background: #fee2e2; color: #991b1b; border-radius: var(--radius-sm); font: var(--weight-semibold) 13px/1.4 var(--font-sans); }
.pdv__step-footer { display: flex; justify-content: flex-end; }

@media (max-width: 860px) {
  .pdv { min-height: 0; }
  .pdv__step-header > .pdv__back { display: none; }
  .pdv__order { position: relative; grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr); padding-bottom: 68px; }
  .pdv__order--editing { grid-template-rows: auto minmax(0, 1fr); }
  .pdv__menu-top { padding: 10px 12px 8px; }
  .pdv__products { padding: 8px 12px 12px; }
  .pdv__product-grid { display: flex; flex-direction: column; gap: 7px; }
  .pdv__product-card {
    min-height: 0; padding: 12px 14px; flex-direction: row; align-items: center;
    gap: 12px; border-radius: var(--radius-md);
  }
  .pdv__product-card:hover:not(:disabled) { transform: none; }
  .pdv__product-card-head { flex: 1; }
  .pdv__product-card-name { -webkit-line-clamp: 1; font-size: 14px; }
  .pdv__product-card-foot { flex-shrink: 0; gap: 12px; }

  .pdv__mobile-panel-trigger {
    position: absolute; left: 10px; right: 10px; bottom: 8px; z-index: 30;
    height: 52px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between;
    border: 0; border-radius: var(--radius-lg); background: var(--brand); color: #fff;
    box-shadow: var(--shadow-lg); font: var(--weight-bold) 13.5px/1 var(--font-sans);
  }
  .pdv__mobile-panel-trigger span { display: inline-flex; align-items: center; gap: 8px; }
  .pdv__mobile-panel-trigger small { opacity: .8; font-size: 11px; }
  .pdv__mobile-panel-trigger strong { font-size: 15px; }
  .pdv__mobile-panel-close {
    display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
    width: 38px; height: 38px; border: 0; border-radius: 50%;
    background: var(--surface-active); color: var(--text-body);
  }
  .pdv__cart-col {
    position: fixed; inset: 0; z-index: 120; border-radius: 0;
    visibility: hidden; opacity: 0; transform: translateY(100%);
    transition: transform .22s var(--ease-out), opacity .18s ease, visibility 0s linear .22s;
  }
  .pdv__cart-col--mobile-open {
    visibility: visible; opacity: 1; transform: translateY(0);
    transition-delay: 0s;
  }
  .pdv__cart-header { min-height: 64px; padding: max(12px, env(safe-area-inset-top)) 14px 12px; }
  .pdv__cart-actions { padding-bottom: max(10px, env(safe-area-inset-bottom)); }

  .pdv__close-body { grid-template-columns: 1fr; }
  .pdv__step--close { padding: 22px 16px; }
  .pdv__pay { position: relative; display: block; overflow-y: auto; padding-bottom: 198px; }
  .pdv__pay-keypad-col { min-height: 100%; padding: 14px 14px 18px; }
  .pdv__pay-summary {
    position: fixed; inset: 0; z-index: 120; padding: max(14px, env(safe-area-inset-top)) 16px max(14px, env(safe-area-inset-bottom));
    background: var(--surface-card); border: 0; visibility: hidden; opacity: 0; transform: translateY(100%);
    transition: transform .22s var(--ease-out), opacity .18s ease, visibility 0s linear .22s;
  }
  .pdv__pay-summary--mobile-open {
    visibility: visible; opacity: 1; transform: translateY(0);
    transition-delay: 0s;
  }
  .pdv__mobile-panel-close--summary {
    width: auto; height: 38px; padding: 0 12px; gap: 7px; border-radius: var(--radius-md);
    align-self: flex-end; font: var(--weight-bold) 12px/1 var(--font-sans);
  }
  .pdv__mobile-payment-actions {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 110;
    display: flex; flex-direction: column; gap: 8px;
    padding: 8px 10px max(8px, env(safe-area-inset-bottom));
    background: var(--surface-card); border-top: 1px solid var(--border);
    box-shadow: 0 -8px 24px rgba(0, 0, 0, .08);
  }
  .pdv__mobile-payment-btn {
    width: 100%; min-height: 48px; padding: 0 14px;
    display: inline-flex; flex-direction: row; align-items: center; justify-content: center; gap: 8px;
    border: 1px solid var(--border); border-radius: var(--radius-md);
    background: var(--surface-card); color: var(--text-body);
    font: var(--weight-bold) 13px/1 var(--font-sans); text-align: center;
  }
  .pdv__mobile-payment-btn--primary { border-color: var(--brand); background: var(--brand); color: #fff; }
  .pdv__mobile-payment-btn:disabled {
    opacity: .35;
    cursor: not-allowed;
    filter: grayscale(.35);
    box-shadow: none;
  }
  .pdv__pay-summary-actions { display: none; }

  .pdv__overlay { align-items: stretch; }
  .pdv__modal,
  .pdv__modal--options,
  .pdv__modal--weigh {
    width: 100%; max-width: none; height: 100%; max-height: none;
    box-sizing: border-box; border-radius: 0; padding: max(20px, env(safe-area-inset-top)) 18px max(18px, env(safe-area-inset-bottom));
    overflow-y: auto;
  }
  .pdv__modal-actions { margin-top: auto; position: sticky; bottom: 0; padding-top: 12px; background: var(--surface-card); }
  .pdv__modal-actions .pdv__btn { min-height: 46px; flex: 1; }
  .pdv__command-table-grid { grid-template-columns: 1fr; max-height: none; overflow: visible; }

  .pdv__success-card { padding: 30px 22px; }
  .pdv__success-actions { grid-template-columns: 1fr; }
}
</style>
