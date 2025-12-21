# Athena Trader Frontend

Professional cryptocurrency trading platform built with Next.js, TypeScript, and modern web technologies.

## 🚀 Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS + Headless UI
- **State Management**: Zustand
- **Data Fetching**: TanStack Query
- **Web3**: RainbowKit + Wagmi
- **Charts**: TradingView Lightweight Charts
- **Real-time**: Socket.IO Client
- **Icons**: Lucide React
- **Fonts**: Inter + JetBrains Mono

## 📦 Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd athena-trader/frontend
```

2. Install dependencies:
```bash
npm install
# or
yarn install
# or
pnpm install
```

3. Set up environment variables:
```bash
cp .env.local.example .env.local
```

4. Start the development server:
```bash
npm run dev
# or
yarn dev
# or
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

## 🌟 Features

### Core Trading Features
- **Real-time Market Data**: Live price feeds and order book updates
- **Advanced Charting**: Professional-grade TradingView charts
- **Order Management**: Place, modify, and cancel orders
- **Portfolio Tracking**: Real-time portfolio valuation and P&L
- **Risk Management**: Advanced risk controls and position sizing

### Web3 Integration
- **Multi-Wallet Support**: Connect with MetaMask, WalletConnect, and more
- **Chain Support**: Ethereum, Polygon, Arbitrum, Optimism, Base
- **Transaction History**: Track all on-chain transactions
- **Gas Optimization**: Smart gas fee estimation

### User Experience
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- **Dark Mode**: Easy on the eyes for extended trading sessions
- **Real-time Notifications**: Instant alerts for price movements and order updates
- **Accessibility**: WCAG 2.1 compliant interface

## 🏗️ Project Structure

```
frontend/
├── components/          # Reusable React components
│   ├── ui/             # Base UI components (buttons, inputs, etc.)
│   ├── charts/          # Chart components
│   ├── forms/           # Form components
│   └── layout/          # Layout components
├── pages/               # Next.js pages
│   ├── api/             # API routes
│   ├── dashboard/        # Dashboard pages
│   ├── trading/          # Trading interface
│   └── settings/         # Settings pages
├── hooks/               # Custom React hooks
├── stores/              # Zustand stores
├── lib/                 # Utility libraries
│   ├── api/             # API clients
│   ├── web3/            # Web3 utilities
│   └── utils/           # Helper functions
├── styles/              # Global styles and CSS
├── types/               # TypeScript type definitions
└── public/              # Static assets
```

## 🎨 Design System

### Color Palette
- **Primary**: Blue (#3b82f6)
- **Secondary**: Gray (#64748b)
- **Success**: Green (#22c55e)
- **Warning**: Orange (#f59e0b)
- **Danger**: Red (#ef4444)

### Typography
- **Sans-serif**: Inter (UI elements)
- **Monospace**: JetBrains Mono (code, data)

### Components
- **Buttons**: Multiple variants (primary, secondary, ghost, etc.)
- **Cards**: Consistent shadow and border styles
- **Forms**: Accessible form inputs with validation
- **Charts**: TradingView integration for professional charts

## 🔧 Development

### Available Scripts

```bash
# Development
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server

# Code Quality
npm run lint         # Run ESLint
npm run type-check   # Run TypeScript type checking
```

### Environment Variables

```bash
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_WS_URL=ws://localhost:8001

# WalletConnect
NEXT_PUBLIC_WALLET_CONNECT_PROJECT_ID=your_project_id

# Feature Flags
NEXT_PUBLIC_ENABLE_ANALYTICS=false
NEXT_PUBLIC_ENABLE_DARK_MODE=true
```

### Code Style

- **TypeScript**: Strict mode enabled
- **ESLint**: Recommended rules with custom configurations
- **Prettier**: Consistent code formatting
- **Husky**: Pre-commit hooks for code quality

## 🚀 Deployment

### Build for Production

```bash
npm run build
```

### Environment Setup

1. **Production Variables**: Set all required environment variables
2. **Build**: Run `npm run build`
3. **Deploy**: Upload the `.next` folder to your hosting provider

### Supported Platforms

- **Vercel**: Recommended for Next.js applications
- **Netlify**: Static site hosting
- **AWS**: Custom deployment with S3 + CloudFront
- **Docker**: Containerized deployment

## 🔌 API Integration

### Backend Services

The frontend connects to the following backend services:

- **Risk Manager** (Port 8001): Risk management and position monitoring
- **Executor** (Port 8002): Order execution and trade management
- **Strategy Engine** (Port 8003): Strategy execution and automation
- **Data Manager** (Port 8004): Market data and historical data

### WebSocket Events

Real-time updates for:
- Price changes
- Order status updates
- Position changes
- Risk alerts
- Strategy performance

## 🧪 Testing

```bash
# Run tests
npm run test

# Run tests with coverage
npm run test:coverage

# Run E2E tests
npm run test:e2e
```

## 📊 Performance

### Optimization Techniques

- **Code Splitting**: Automatic route-based splitting
- **Image Optimization**: Next.js Image component
- **Font Optimization**: Google Fonts with display: swap
- **Caching**: Aggressive caching strategies
- **Bundle Analysis**: Regular bundle size monitoring

### Performance Metrics

- **Lighthouse Score**: 95+ across all categories
- **Core Web Vitals**: Optimized for user experience
- **Bundle Size**: < 500KB (gzipped) initial load

## 🔒 Security

### Best Practices

- **Content Security Policy**: Strict CSP headers
- **HTTPS Only**: Production deployments only
- **Input Validation**: All user inputs validated
- **XSS Protection**: Built-in React protections
- **Dependency Scanning**: Regular security audits

## 📱 Mobile Support

### Responsive Breakpoints

- **Mobile**: < 768px
- **Tablet**: 768px - 1024px
- **Desktop**: > 1024px

### Touch Optimizations

- **Touch-friendly**: Minimum 44px touch targets
- **Gesture Support**: Swipe and pinch gestures
- **Viewport**: Proper mobile viewport configuration

## 🌍 Internationalization

### Supported Languages

- **English** (en): Default language
- **Chinese** (zh): Simplified Chinese
- **Japanese** (ja): Japanese support
- **Korean** (ko): Korean support

### Adding New Languages

1. Add translation files to `locales/`
2. Update language selector
3. Test RTL/LTR text direction

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Development Guidelines

- Follow the existing code style
- Write meaningful commit messages
- Update documentation for new features
- Ensure all tests pass

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: [docs.athena-trader.com](https://docs.athena-trader.com)
- **Issues**: [GitHub Issues](https://github.com/athena-trader/issues)
- **Discord**: [Community Discord](https://discord.gg/athena-trader)
- **Email**: support@athena-trader.com

## 🗺 Roadmap

### Upcoming Features

- **Advanced Charting**: More indicators and drawing tools
- **Strategy Builder**: Visual strategy creation
- **Social Trading**: Copy trading from successful traders
- **Mobile App**: Native iOS and Android apps
- **Advanced Analytics**: Machine learning insights

### Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.
