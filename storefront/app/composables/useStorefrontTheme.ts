/**
 * Tema do restaurante → variáveis CSS.
 *
 * O tema chega do backend como um punhado de tokens (`primaryColor`,
 * `borderRadius`, …) e vira `--sf-*` no elemento raiz do site. É por isso que
 * as páginas guardam `var(--sf-primary)` em vez de `#E53935`: trocar o tema
 * repinta o site inteiro sem editar um bloco sequer.
 *
 * O fallback importa tanto quanto o tema. Um site cujo tema veio vazio (payload
 * antigo em cache, campo limpo à mão) ainda tem de aparecer legível — nunca
 * texto preto sobre fundo preto.
 */
import type { StorefrontTheme } from '~~/types/storefront'

/** Mesmos valores do preset PADRÃO do backend (`apps/storefront/themes.py`). */
export const FALLBACK_THEME: Required<Pick<StorefrontTheme,
  'primaryColor' | 'secondaryColor' | 'accentColor' | 'backgroundColor' | 'surfaceColor' |
  'textColor' | 'mutedTextColor' | 'borderColor' | 'saleColor' | 'onPrimaryColor' |
  'onAccentColor' | 'whatsappColor' | 'headerBackgroundColor' |
  'announcementBackgroundColor' | 'announcementTextColor' | 'fontFamily' |
  'headingFontFamily' | 'borderRadius' | 'containerWidth' | 'spacing'>> = {
  primaryColor: '#0B5B34',
  secondaryColor: '#0F1A14',
  accentColor: '#F7CE46',
  backgroundColor: '#FFFFFF',
  surfaceColor: '#F5F7F4',
  textColor: '#14211A',
  mutedTextColor: '#6B7B72',
  borderColor: '#E4E9E5',
  saleColor: '#D92D20',
  onPrimaryColor: '#FFFFFF',
  onAccentColor: '#0F1A14',
  whatsappColor: '#25D366',
  headerBackgroundColor: '#FFFFFF',
  announcementBackgroundColor: '#0F1A14',
  announcementTextColor: '#FFFFFF',
  fontFamily: 'Inter, system-ui, sans-serif',
  headingFontFamily: 'Inter, system-ui, sans-serif',
  borderRadius: '14px',
  containerWidth: '1240px',
  spacing: '24px',
}

const TOKEN_TO_VARIABLE: Record<string, string> = {
  primaryColor: '--sf-primary',
  secondaryColor: '--sf-secondary',
  accentColor: '--sf-accent',
  backgroundColor: '--sf-background',
  surfaceColor: '--sf-surface',
  textColor: '--sf-text',
  mutedTextColor: '--sf-muted-text',
  borderColor: '--sf-border',
  // Cores que antes estavam fixas no CSS dos blocos. Sem elas no mapa, trocar
  // de tema repintava o site e deixava ilhas para trás — o selo de promoção
  // vermelho num tema azul, o texto branco sobre um destaque claro.
  saleColor: '--sf-sale',
  onPrimaryColor: '--sf-on-primary',
  onAccentColor: '--sf-on-accent',
  whatsappColor: '--sf-whatsapp',
  headerBackgroundColor: '--sf-header-bg',
  announcementBackgroundColor: '--sf-announce-bg',
  announcementTextColor: '--sf-announce-text',
  fontFamily: '--sf-font',
  headingFontFamily: '--sf-heading-font',
  borderRadius: '--sf-radius',
  containerWidth: '--sf-container-width',
  spacing: '--sf-spacing',
}

/** Só valores simples viram variável — nada de `url(javascript:...)` no CSS. */
const SAFE_TOKEN_VALUE = /^[A-Za-z0-9\s#(),.%'"/_-]{1,200}$/

export function themeToCssVariables(theme?: StorefrontTheme | null): Record<string, string> {
  const merged = { ...FALLBACK_THEME, ...(theme ?? {}) } as Record<string, unknown>
  const variables: Record<string, string> = {}

  for (const [token, variable] of Object.entries(TOKEN_TO_VARIABLE)) {
    const value = merged[token]
    if (typeof value !== 'string' || !value.trim()) continue
    if (!SAFE_TOKEN_VALUE.test(value)) continue
    variables[variable] = value.trim()
  }
  return variables
}

export function useStorefrontTheme(theme: Ref<StorefrontTheme | undefined | null>) {
  const cssVariables = computed(() => themeToCssVariables(theme.value))
  const isDark = computed(() => theme.value?.mode === 'dark')
  return { cssVariables, isDark }
}
