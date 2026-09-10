/**
 * Os três dispositivos do editor — e nada além disso.
 *
 * Três breakpoints cobrem o que um cardápio precisa e mantêm a edição
 * gerenciável: cada breakpoint a mais é mais um estado que o restaurante tem de
 * conferir antes de publicar. `widthMedia` é a largura da media query gerada;
 * `width` é só o tamanho do canvas no editor.
 */
import type { Breakpoint } from '~~/types/builder'

export interface DeviceSpec {
  id: Breakpoint
  name: string
  width: string
  widthMedia?: number
}

export const DEVICES: DeviceSpec[] = [
  { id: 'desktop', name: 'Desktop', width: '' },
  { id: 'tablet', name: 'Tablet', width: '768px', widthMedia: 1024 },
  { id: 'mobile', name: 'Mobile', width: '375px', widthMedia: 767 },
]

export const TABLET_MAX_WIDTH = 1024
export const MOBILE_MAX_WIDTH = 767

/**
 * A qual breakpoint pertence uma regra, a partir do `mediaText` do GrapesJS.
 *
 * Sem media query é desktop (o estilo base). `max-width` até 767px é mobile;
 * até 1024px, tablet. Qualquer outra media query cai em desktop em vez de ser
 * descartada — perder o estilo silenciosamente seria pior do que aplicá-lo em
 * todas as larguras.
 */
export function breakpointFromMedia(mediaText?: string | null): Breakpoint {
  if (!mediaText) return 'desktop'
  const match = /max-width\s*:\s*(\d+)\s*px/i.exec(mediaText)
  if (!match) return 'desktop'

  const width = Number(match[1])
  if (width <= MOBILE_MAX_WIDTH) return 'mobile'
  if (width <= TABLET_MAX_WIDTH) return 'tablet'
  return 'desktop'
}
