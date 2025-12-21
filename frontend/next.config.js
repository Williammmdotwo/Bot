/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  output: 'standalone',
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001',
    NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001',
    NEXT_PUBLIC_WALLET_CONNECT_PROJECT_ID: process.env.NEXT_PUBLIC_WALLET_CONNECT_PROJECT_ID || '',
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/api/:path*`,
      },
    {
        source: '/ws/:path*',
        destination: `${process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001'}/ws/:path*`,
      },
    {
        source: '/socket.io/:path*',
        destination: `${process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001'}/socket.io/:path*`,
      },
    {
        source: '/health',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/health`,
      },
    {
        source: '/config',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/config`,
      },
    {
        source: '/trades',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/trades`,
      },
    {
        source: '/positions',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/positions`,
      },
    {
        source: '/risk',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/risk`,
      },
    {
        source: '/strategy',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/strategy`,
      },
    {
        source: '/analytics',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/analytics`,
      },
    {
        source: '/portfolio',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/portfolio`,
      },
    {
        source: '/orders',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/orders`,
      },
    {
        source: '/account',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/account`,
      },
    {
        source: '/notifications',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/notifications`,
      },
    {
        source: '/settings',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/settings`,
      },
    {
        source: '/logs',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/logs`,
      },
    {
        source: '/system',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/system`,
      },
    {
        source: '/market-data',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/market-data`,
      },
    {
        source: '/backtest',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/backtest`,
      },
    {
        source: '/reports',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/reports`,
      },
    {
        source: '/monitoring',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/monitoring`,
      },
    {
        source: '/alerts',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/alerts`,
      },
    {
        source: '/integrations',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/integrations`,
      },
    {
        source: '/help',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/help`,
      },
    {
        source: '/docs',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/docs`,
      },
    {
        source: '/status',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/status`,
      },
    {
        source: '/metrics',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/metrics`,
      },
    {
        source: '/audit',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/audit`,
      },
    {
        source: '/security',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/security`,
      },
    {
        source: '/performance',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/performance`,
      },
    {
        source: '/debug',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/debug`,
      },
    {
        source: '/test',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/test`,
      },
    {
        source: '/demo',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/demo`,
      },
    {
        source: '/tutorial',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/tutorial`,
      },
    {
        source: '/faq',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/faq`,
      },
    {
        source: '/contact',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/contact`,
      },
    {
        source: '/about',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/about`,
      },
    {
        source: '/privacy',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/privacy`,
      },
    {
        source: '/terms',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/terms`,
      },
    {
        source: '/legal',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/legal`,
      },
    {
        source: '/investors',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/investors`,
      },
    {
        source: '/team',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/team`,
      },
    {
        source: '/careers',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/careers`,
      },
    {
        source: '/press',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/press`,
      },
    {
        source: '/blog',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/blog`,
      },
    {
        source: '/newsletter',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/newsletter`,
      },
    {
        source: '/community',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/community`,
      },
    {
        source: '/roadmap',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/roadmap`,
      },
    {
        source: '/changelog',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/changelog`,
      },
    {
        source: '/download',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/download`,
      },
    {
        source: '/mobile',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/mobile`,
      },
    {
        source: '/desktop',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/desktop`,
      },
    {
        source: '/extensions',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/extensions`,
      },
    {
        source: '/plugins',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/plugins`,
      },
    {
        source: '/themes',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/themes`,
      },
    {
        source: '/languages',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/languages`,
      },
    {
        source: '/currency',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/currency`,
      },
    {
        source: '/exchange',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/exchange`,
      },
    {
        source: '/network',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/network`,
      },
    {
        source: '/gas',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/gas`,
      },
    {
        source: '/fees',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/fees`,
      },
    {
        source: '/slippage',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/slippage`,
      },
    {
        source: '/liquidity',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/liquidity`,
      },
    {
        source: '/volume',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/volume`,
      },
    {
        source: '/price',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/price`,
      },
    {
        source: '/orderbook',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/orderbook`,
      },
    {
        source: '/trades-history',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/trades-history`,
      },
    {
        source: '/open-interest',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/open-interest`,
      },
    {
        source: '/funding-rate',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/funding-rate`,
      },
    {
        source: '/leverage',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/leverage`,
      },
    {
        source: '/margin',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/margin`,
      },
    {
        source: '/collateral',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/collateral`,
      },
    {
        source: '/borrow',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/borrow`,
      },
    {
        source: '/lend',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/lend`,
      },
    {
        source: '/stake',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'}/stake`,
      }
    ]
  },
  // 安全头部配置
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=()',
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=31536000; includeSubDomains; preload',
          },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline' https://www.googletagmanager.com",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: https: blob:",
              "font-src 'self' data:",
              "connect-src 'self' ws: wss: https:",
              "frame-src 'none'",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; '),
          },
        ],
      },
    ];
  },
}
