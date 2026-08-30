import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
// Fontes empacotadas com o bundle: o painel é servido pelo próprio nginx e
// não deve depender de CDN externa para renderizar com a tipografia certa.
// Só o subset latino: os demais (cirílico, grego, vietnamita) triplicariam os
// arquivos de fonte no dist sem uso nenhum num painel em português.
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => {
        // 401/403 não se resolvem repetindo a requisição.
        const status = (error as { status?: number })?.status
        if (status === 401 || status === 403) return false
        return count < 2
      },
      staleTime: 20_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
