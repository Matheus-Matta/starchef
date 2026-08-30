<template>
  <div class="help-center">
    <header class="help-topbar">
      <RouterLink class="help-brand" to="/docs" aria-label="Central de Ajuda StarChef">
        <img src="/logoicon.png" width="38" height="38" alt="" />
        <span>StarChef <strong>Ajuda</strong></span>
      </RouterLink>
      <nav class="help-topbar__actions" aria-label="Acesso ao sistema">
        <a class="help-contact" :href="whatsappUrl" target="_blank" rel="noopener noreferrer">
          <AppIcon name="life-buoy" :size="16" />
          Falar com o suporte
        </a>
        <RouterLink class="help-login" to="/home">Acessar o StarChef</RouterLink>
      </nav>
    </header>

    <section class="help-hero" aria-labelledby="help-title">
      <div class="help-hero__content">
        <span class="help-eyebrow">CENTRAL DE AJUDA</span>
        <h1 id="help-title">Como podemos ajudar?</h1>
        <p>Encontre processos, configurações e a origem dos dados usados em cada área do StarChef.</p>
        <label class="help-search">
          <AppIcon name="search" :size="19" />
          <input
            ref="searchInput"
            v-model.trim="query"
            type="search"
            placeholder="Buscar por caixa, nota fiscal, produto, impressora..."
            autocomplete="off"
            aria-label="Buscar na Central de Ajuda"
            @keydown.esc="query = ''"
          />
          <kbd>/</kbd>
        </label>
        <div class="help-hero__meta">
          <span>{{ helpArticles.length }} guias</span>
          <span>Leitura pública</span>
          <span>Atualizado junto com o sistema</span>
        </div>
      </div>
    </section>

    <main class="help-layout">
      <aside class="help-nav" aria-label="Tópicos da Central de Ajuda">
        <div class="help-nav__title">Navegue por area</div>
        <section v-for="section in helpSections" :key="section.id" class="help-nav__section">
          <button
            type="button"
            class="help-nav__section-button"
            :class="{ 'help-nav__section-button--active': activeArticle?.sectionId === section.id }"
            @click="openArticle(section.articles[0].id)"
          >
            <span>{{ section.title }}</span>
            <small>{{ section.articles.length }}</small>
          </button>
          <div v-if="activeArticle?.sectionId === section.id && !query" class="help-nav__articles">
            <button
              v-for="article in section.articles"
              :key="article.id"
              type="button"
              :class="{ 'help-nav__article--active': activeArticle?.id === article.id }"
              @click="openArticle(article.id)"
            >
              {{ article.title }}
            </button>
          </div>
        </section>
      </aside>

      <section v-if="query" class="help-results" aria-live="polite">
        <div class="help-results__head">
          <div>
            <span class="help-eyebrow">RESULTADOS</span>
            <h2>{{ resultLabel }}</h2>
          </div>
          <button type="button" @click="query = ''">Limpar busca</button>
        </div>

        <div v-if="filteredArticles.length" class="help-results__grid">
          <button
            v-for="article in filteredArticles"
            :key="article.id"
            type="button"
            class="help-result-card"
            @click="openArticle(article.id)"
          >
            <span class="help-result-card__icon"><AppIcon :name="article.icon" :size="20" /></span>
            <span class="help-result-card__copy">
              <small>{{ article.sectionTitle }}</small>
              <strong>{{ article.title }}</strong>
              <span>{{ article.summary }}</span>
            </span>
            <AppIcon name="arrow-right" :size="16" />
          </button>
        </div>

        <div v-else class="help-empty">
          <span><AppIcon name="search" :size="24" /></span>
          <h2>Nenhum guia encontrado</h2>
          <p>Tente termos como “caixa”, “produto”, “Focus”, “comanda” ou “impressora”.</p>
          <button type="button" @click="query = ''">Ver todos os assuntos</button>
        </div>
      </section>

      <article v-else-if="activeArticle" :id="activeArticle.id" class="help-article">
        <nav class="help-breadcrumb" aria-label="Navegação estrutural">
          <button type="button" @click="openArticle('home')">Central de Ajuda</button>
          <AppIcon name="chevron-right" :size="12" />
          <span>{{ activeArticle.sectionTitle }}</span>
        </nav>

        <header class="help-article__header">
          <span class="help-article__icon"><AppIcon :name="activeArticle.icon" :size="24" /></span>
          <div>
            <span class="help-eyebrow">{{ activeArticle.sectionTitle.toUpperCase() }}</span>
            <h1>{{ activeArticle.title }}</h1>
            <p>{{ activeArticle.summary }}</p>
          </div>
        </header>

        <div v-if="activeArticle.warning" class="help-warning" role="note">
          <AppIcon name="warning" :size="18" />
          <p>{{ activeArticle.warning }}</p>
        </div>

        <section class="help-article__block">
          <h2>Para que serve</h2>
          <p>{{ activeArticle.purpose }}</p>
        </section>

        <section class="help-article__block">
          <h2>Como usar</h2>
          <ol class="help-steps">
            <li v-for="(step, index) in activeArticle.steps" :key="step">
              <span>{{ index + 1 }}</span>
              <p>{{ step }}</p>
            </li>
          </ol>
        </section>

        <section class="help-article__block">
          <h2>Onde obter os dados</h2>
          <ul class="help-data-list">
            <li v-for="item in activeArticle.data" :key="item">
              <AppIcon name="check-circle" :size="16" />
              <span>{{ item }}</span>
            </li>
          </ul>
        </section>

        <section v-if="activeArticle.tips?.length" class="help-tip" aria-label="Dicas importantes">
          <span class="help-tip__icon"><AppIcon name="life-buoy" :size="18" /></span>
          <div>
            <strong>Antes de continuar</strong>
            <p v-for="tip in activeArticle.tips" :key="tip">{{ tip }}</p>
          </div>
        </section>

        <footer class="help-article__footer">
          <div>
            <strong>Ainda precisa de ajuda?</strong>
            <span>Fale com o suporte e informe a tela, a ação realizada e a mensagem apresentada.</span>
          </div>
          <a :href="whatsappUrl" target="_blank" rel="noopener noreferrer">Abrir atendimento</a>
        </footer>

        <nav class="help-article__pagination" aria-label="Artigos anterior e seguinte">
          <button type="button" :disabled="!previousArticle" @click="previousArticle && openArticle(previousArticle.id)">
            <AppIcon name="arrow-left" :size="15" />
            <span><small>Anterior</small>{{ previousArticle?.title || "Início" }}</span>
          </button>
          <button type="button" :disabled="!nextArticle" @click="nextArticle && openArticle(nextArticle.id)">
            <span><small>Próximo</small>{{ nextArticle?.title || "Fim" }}</span>
            <AppIcon name="arrow-right" :size="15" />
          </button>
        </nav>
      </article>
    </main>

    <footer class="help-footer">
      <img src="/logoicon.png" width="28" height="28" alt="" />
      <span>StarChef · Operação, gestão e atendimento em um só lugar.</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import AppIcon from "../components/AppIcon.vue";
import { helpArticles, helpSections } from "../content/helpCenter";

const route = useRoute();
const router = useRouter();
const searchInput = ref(null);
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
const whatsappUrl = "https://wa.me/5521966621486?text=Ol%C3%A1%2C%20preciso%20de%20ajuda%20com%20o%20StarChef.";
const previousTitle = document.title;

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const requestedArticleId = computed(() => route.hash.replace(/^#/, "") || "home");
const activeArticle = computed(() =>
  helpArticles.find((article) => article.id === requestedArticleId.value) || helpArticles[0],
);
const activeIndex = computed(() => helpArticles.findIndex((article) => article.id === activeArticle.value?.id));
const previousArticle = computed(() => activeIndex.value > 0 ? helpArticles[activeIndex.value - 1] : null);
const nextArticle = computed(() => activeIndex.value >= 0 && activeIndex.value < helpArticles.length - 1 ? helpArticles[activeIndex.value + 1] : null);
const filteredArticles = computed(() => {
  const term = normalize(query.value);
  if (!term) return helpArticles;
  return helpArticles.filter((article) => normalize([
    article.title,
    article.sectionTitle,
    article.summary,
    article.purpose,
    ...article.steps,
    ...article.data,
    ...(article.tips || []),
  ].join(" ")).includes(term));
});
const resultLabel = computed(() => {
  const count = filteredArticles.value.length;
  return `${count} ${count === 1 ? "guia encontrado" : "guias encontrados"} para “${query.value}”`;
});

async function openArticle(id) {
  query.value = "";
  await router.push({ name: "docs", hash: `#${id}` });
  await nextTick();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function handleGlobalKeydown(event) {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable) return;
  event.preventDefault();
  searchInput.value?.focus();
}

watch(query, (value) => {
  const current = typeof route.query.q === "string" ? route.query.q : "";
  if (value === current) return;
  router.replace({ name: "docs", query: value ? { q: value } : {}, hash: route.hash }).catch(() => {});
});

onMounted(() => {
  document.title = "Central de Ajuda | StarChef";
  window.addEventListener("keydown", handleGlobalKeydown);
});

onBeforeUnmount(() => {
  document.title = previousTitle;
  window.removeEventListener("keydown", handleGlobalKeydown);
});
</script>

<style scoped>
.help-center {
  min-height: 100vh;
  min-height: 100dvh;
  background: #f7f8f6;
  color: #18201d;
  font-family: var(--font-sans);
}

.help-topbar {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 0 max(24px, calc((100vw - 1180px) / 2));
  background: #fff;
  border-bottom: 1px solid #e5e9e6;
}

.help-brand,
.help-topbar__actions,
.help-contact {
  display: flex;
  align-items: center;
}

.help-brand {
  gap: 10px;
  color: #15221d;
  text-decoration: none;
  font-size: 19px;
  font-weight: 850;
  letter-spacing: -.02em;
}

.help-brand strong { color: #0e8f63; }
.help-topbar__actions { gap: 10px; }

.help-contact,
.help-login {
  min-height: 40px;
  padding: 0 15px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 750;
  text-decoration: none;
}

.help-contact { gap: 8px; color: #44524c; }
.help-contact:hover { background: #f1f4f2; }
.help-login { display: inline-flex; align-items: center; color: #fff; background: #087a55; }
.help-login:hover { background: #066a49; }

.help-hero {
  padding: 62px 24px 72px;
  background:
    radial-gradient(circle at 20% 0%, rgba(67, 190, 139, .2), transparent 35%),
    radial-gradient(circle at 82% 15%, rgba(255, 255, 255, .09), transparent 24%),
    linear-gradient(135deg, #073f31 0%, #075b42 55%, #087a55 100%);
  color: #fff;
}

.help-hero__content { width: min(760px, 100%); margin: 0 auto; text-align: center; }
.help-eyebrow { display: block; color: #0e8f63; font-size: 11px; font-weight: 850; letter-spacing: .14em; }
.help-hero .help-eyebrow { color: #9ce8c6; }
.help-hero h1 { margin: 9px 0 12px; font-size: clamp(32px, 5vw, 48px); line-height: 1.05; letter-spacing: -.04em; }
.help-hero p { margin: 0 auto; max-width: 650px; color: #d7eee5; font-size: 16px; line-height: 1.6; }

.help-search {
  min-height: 60px;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 30px;
  padding: 0 18px;
  background: #fff;
  border: 1px solid rgba(255, 255, 255, .34);
  border-radius: 15px;
  box-shadow: 0 18px 45px rgba(1, 33, 24, .25);
  color: #718079;
  text-align: left;
}

.help-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: #17211d;
  font: 650 15px/1.2 var(--font-sans);
}

.help-search input::placeholder { color: #87938e; }
.help-search kbd { padding: 4px 8px; border: 1px solid #dce3df; border-radius: 6px; background: #f5f7f6; color: #6e7b75; font: 700 12px/1 var(--font-sans); }
.help-hero__meta { display: flex; justify-content: center; gap: 22px; margin-top: 18px; color: #bde4d4; font-size: 12px; font-weight: 650; }
.help-hero__meta span + span::before { content: "·"; margin-right: 22px; }

.help-layout {
  width: min(1180px, calc(100% - 48px));
  display: grid;
  grid-template-columns: 245px minmax(0, 1fr);
  gap: 48px;
  align-items: start;
  margin: 0 auto;
  padding: 48px 0 72px;
}

.help-nav {
  position: sticky;
  top: 24px;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  padding-right: 10px;
}

.help-nav__title { margin-bottom: 14px; color: #7a8882; font-size: 11px; font-weight: 850; letter-spacing: .12em; text-transform: uppercase; }
.help-nav__section { margin-bottom: 4px; }
.help-nav button { font-family: inherit; }

.help-nav__section-button {
  width: 100%;
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 11px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #45534d;
  cursor: pointer;
  font-size: 13px;
  font-weight: 750;
  text-align: left;
}

.help-nav__section-button small { min-width: 22px; padding: 3px 6px; border-radius: 999px; background: #e9eeeb; color: #6f7d77; text-align: center; }
.help-nav__section-button:hover { background: #edf2ef; color: #17211d; }
.help-nav__section-button--active { background: #dff3e9; color: #087a55; }
.help-nav__section-button--active small { background: #fff; color: #087a55; }
.help-nav__articles { margin: 4px 0 10px 15px; padding-left: 11px; border-left: 1px solid #dce4df; }
.help-nav__articles button { width: 100%; display: block; padding: 7px 5px; border: 0; background: none; color: #6b7872; cursor: pointer; font-size: 12px; line-height: 1.3; text-align: left; }
.help-nav__articles button:hover,
.help-nav__articles .help-nav__article--active { color: #087a55; font-weight: 800; }

.help-article,
.help-results { min-width: 0; }
.help-breadcrumb { display: flex; align-items: center; gap: 7px; margin-bottom: 24px; color: #78857f; font-size: 12px; }
.help-breadcrumb button { padding: 0; border: 0; background: none; color: #087a55; cursor: pointer; font: inherit; font-weight: 750; }

.help-article__header {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  padding-bottom: 32px;
  border-bottom: 1px solid #dfe5e1;
}

.help-article__icon,
.help-result-card__icon,
.help-empty > span,
.help-tip__icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #dff3e9;
  color: #087a55;
}

.help-article__icon { width: 54px; height: 54px; border-radius: 15px; }
.help-article__header h1 { margin: 7px 0 8px; color: #16201c; font-size: clamp(29px, 4vw, 40px); line-height: 1.08; letter-spacing: -.035em; }
.help-article__header p { max-width: 720px; margin: 0; color: #65736d; font-size: 15px; line-height: 1.6; }
.help-article__block { padding-top: 32px; }
.help-article__block h2 { margin: 0 0 13px; color: #1d2924; font-size: 19px; letter-spacing: -.01em; }
.help-article__block > p { margin: 0; color: #53615b; font-size: 14px; line-height: 1.75; }

.help-steps { display: grid; gap: 11px; margin: 0; padding: 0; list-style: none; }
.help-steps li { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 12px; align-items: start; padding: 15px 16px; background: #fff; border: 1px solid #e0e6e2; border-radius: 12px; }
.help-steps li > span { width: 27px; height: 27px; display: inline-flex; align-items: center; justify-content: center; border-radius: 8px; background: #e3f4eb; color: #087a55; font-size: 12px; font-weight: 850; }
.help-steps p { margin: 3px 0 0; color: #46544e; font-size: 13px; line-height: 1.55; }
.help-data-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.help-data-list li { display: flex; align-items: flex-start; gap: 10px; color: #4d5b55; font-size: 13px; line-height: 1.55; }
.help-data-list :deep(i) { margin-top: 3px; color: #0e8f63; }

.help-warning { display: flex; align-items: flex-start; gap: 11px; margin-top: 26px; padding: 15px 16px; border: 1px solid #f2d38d; border-radius: 12px; background: #fff8e7; color: #7c5917; }
.help-warning p { margin: 0; font-size: 13px; line-height: 1.55; }
.help-warning :deep(i) { margin-top: 2px; }
.help-tip { display: flex; gap: 12px; margin-top: 34px; padding: 18px; border-radius: 13px; background: #e8f5ef; color: #244b3b; }
.help-tip__icon { width: 34px; height: 34px; border-radius: 10px; background: #fff; }
.help-tip strong { display: block; margin: 1px 0 5px; font-size: 13px; }
.help-tip p { margin: 3px 0 0; font-size: 13px; line-height: 1.55; }

.help-article__footer { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 38px; padding: 22px; border: 1px solid #dfe5e1; border-radius: 14px; background: #fff; }
.help-article__footer div { display: flex; flex-direction: column; gap: 5px; }
.help-article__footer strong { font-size: 14px; }
.help-article__footer span { color: #6a7771; font-size: 12px; line-height: 1.5; }
.help-article__footer a { flex-shrink: 0; padding: 11px 15px; border-radius: 9px; background: #087a55; color: #fff; font-size: 12px; font-weight: 800; text-decoration: none; }
.help-article__pagination { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px; }
.help-article__pagination button { min-height: 58px; display: flex; align-items: center; gap: 12px; padding: 10px 14px; border: 1px solid #dfe5e1; border-radius: 11px; background: #fff; color: #35433d; cursor: pointer; font-family: inherit; text-align: left; }
.help-article__pagination button:last-child { justify-content: flex-end; text-align: right; }
.help-article__pagination button:hover:not(:disabled) { border-color: #70bc9d; color: #087a55; }
.help-article__pagination button:disabled { opacity: .45; cursor: default; }
.help-article__pagination span { min-width: 0; display: flex; flex-direction: column; gap: 3px; font-size: 12px; font-weight: 800; }
.help-article__pagination small { color: #89958f; font-size: 10px; font-weight: 700; text-transform: uppercase; }

.help-results__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.help-results__head h2 { margin: 7px 0 0; font-size: 25px; letter-spacing: -.025em; }
.help-results__head button,
.help-empty button { border: 0; background: transparent; color: #087a55; cursor: pointer; font: 800 12px/1 var(--font-sans); }
.help-results__grid { display: grid; gap: 10px; }
.help-result-card { width: 100%; display: grid; grid-template-columns: 42px minmax(0, 1fr) 18px; gap: 13px; align-items: center; padding: 15px; border: 1px solid #dfe5e1; border-radius: 12px; background: #fff; color: #26332d; cursor: pointer; font-family: inherit; text-align: left; transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease; }
.help-result-card:hover { transform: translateY(-1px); border-color: #72bda0; box-shadow: 0 8px 24px rgba(19, 65, 47, .08); }
.help-result-card__icon { width: 42px; height: 42px; border-radius: 11px; }
.help-result-card__copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.help-result-card__copy small { color: #0e8f63; font-size: 10px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }
.help-result-card__copy strong { font-size: 14px; }
.help-result-card__copy > span { overflow: hidden; color: #6a7771; font-size: 12px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.help-empty { padding: 70px 20px; border: 1px dashed #cfd8d3; border-radius: 15px; text-align: center; }
.help-empty > span { width: 52px; height: 52px; margin: 0 auto 15px; border-radius: 15px; }
.help-empty h2 { margin: 0 0 7px; font-size: 20px; }
.help-empty p { margin: 0 0 18px; color: #74817b; font-size: 13px; }

.help-footer { min-height: 88px; display: flex; align-items: center; justify-content: center; gap: 10px; padding: 20px; border-top: 1px solid #e0e6e2; background: #fff; color: #76837d; font-size: 12px; }

@media (max-width: 850px) {
  .help-layout { grid-template-columns: 1fr; gap: 24px; }
  .help-nav { position: static; max-height: none; display: flex; gap: 7px; overflow-x: auto; padding: 0 0 8px; }
  .help-nav__title,
  .help-nav__articles { display: none; }
  .help-nav__section { flex: 0 0 auto; margin: 0; }
  .help-nav__section-button { gap: 8px; border: 1px solid #dfe5e1; background: #fff; }
}

@media (max-width: 640px) {
  .help-topbar { min-height: 62px; padding: 0 16px; }
  .help-brand { font-size: 16px; }
  .help-brand img { width: 32px; height: 32px; }
  .help-contact { display: none; }
  .help-login { min-height: 36px; padding: 0 12px; font-size: 11px; }
  .help-hero { padding: 46px 16px 54px; }
  .help-hero p { font-size: 14px; }
  .help-search { min-height: 54px; padding: 0 14px; }
  .help-search input { font-size: 13px; }
  .help-search kbd { display: none; }
  .help-hero__meta { gap: 10px; font-size: 10px; }
  .help-hero__meta span + span::before { margin-right: 10px; }
  .help-layout { width: calc(100% - 28px); padding: 28px 0 48px; }
  .help-article__header { gap: 13px; }
  .help-article__icon { width: 44px; height: 44px; border-radius: 12px; }
  .help-article__header h1 { font-size: 29px; }
  .help-article__footer { align-items: stretch; flex-direction: column; }
  .help-article__footer a { text-align: center; }
  .help-article__pagination { grid-template-columns: 1fr; }
  .help-results__head { align-items: flex-start; flex-direction: column; }
  .help-result-card__copy > span { white-space: normal; }
}
</style>
