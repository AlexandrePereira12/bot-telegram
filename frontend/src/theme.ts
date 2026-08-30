/**
 * Tema claro/escuro.
 *
 * A escolha vive no <html data-theme>, não no React: o script inline do
 * index.html já carimba o atributo antes do bundle carregar, então este
 * módulo apenas assume o valor que o documento já tem e o mantém em sincronia
 * com o localStorage. Isso evita o flash de tema errado a cada carga.
 */
import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const CHAVE = 'theme'
const ouvintes = new Set<() => void>()

function atual(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(CHAVE, theme)
  } catch {
    /* modo privativo/storage bloqueado: o tema vale só para esta aba */
  }
  ouvintes.forEach((fn) => fn())
}

export function toggleTheme(): void {
  setTheme(atual() === 'dark' ? 'light' : 'dark')
}

function subscribe(fn: () => void): () => void {
  ouvintes.add(fn)
  return () => {
    ouvintes.delete(fn)
  }
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, atual, () => 'light' as Theme)
}

/** Tokens que o Recharts precisa receber como valor: `stroke`/`fill` são
 *  atributos de apresentação do SVG e não aceitam `var(--x)`. Ler o
 *  computed style mantém a fonte da verdade no CSS, e depender do tema atual
 *  faz o gráfico recolorir junto do resto da interface. */
export function useChartTokens() {
  const theme = useTheme()

  // theme entra na dependência de propósito: sem isso o valor seria lido uma
  // única vez e o gráfico ficaria com as cores do tema anterior.
  void theme
  const css = getComputedStyle(document.documentElement)
  const token = (nome: string) => css.getPropertyValue(nome).trim()

  return {
    grid: token('--chart-grid'),
    axis: token('--chart-axis'),
    serie1: token('--chart-1'),
    serie2: token('--chart-2'),
    tooltip: {
      background: token('--surface'),
      border: `1px solid ${token('--border')}`,
      borderRadius: 6,
      color: token('--text'),
      fontSize: 12,
      boxShadow: token('--shadow'),
    } as const,
  }
}
