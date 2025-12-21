import type { AppProps } from 'next/app'
import Head from 'next/head'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
// import { wagmiConfig } from '../lib/wagmi' // 临时封存钱包功能
import '../styles/globals.css'

// Create a client
const queryClient = new QueryClient()

function MyApp({ Component, pageProps }: AppProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <>
        <Head>
          <title>Athena Trader - Professional Trading Platform</title>
          <meta name="description" content="Professional cryptocurrency trading platform with advanced risk management and strategy automation" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <meta name="theme-color" content="#3b82f6" />
          <link rel="icon" href="/favicon.ico" />
          <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
          <link rel="manifest" href="/manifest.json" />
          
          {/* Open Graph */}
          <meta property="og:title" content="Athena Trader - Professional Trading Platform" />
          <meta property="og:description" content="Professional cryptocurrency trading platform with advanced risk management and strategy automation" />
          <meta property="og:type" content="website" />
          <meta property="og:image" content="/og-image.png" />
          
          {/* Twitter */}
          <meta name="twitter:card" content="summary_large_image" />
          <meta name="twitter:title" content="Athena Trader - Professional Trading Platform" />
          <meta name="twitter:description" content="Professional cryptocurrency trading platform with advanced risk management and strategy automation" />
          <meta name="twitter:image" content="/twitter-image.png" />
          
          {/* Preconnect to external domains */}
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        </Head>

        <Component {...pageProps} />
      </>
    </QueryClientProvider>
  )
}

export default MyApp
