import Head from 'next/head'
import { useState, useEffect } from 'react'
import AIConfidence from '../components/trading/AIConfidence'
import AIThinking from '../components/trading/AIThinking'
import TradeRecords from '../components/trading/TradeRecords'
import ThemeToggle from '../components/layout/ThemeToggle'
import ModeToggle from '../components/layout/ModeToggle'

export default function Home() {
  const [isDarkMode, setIsDarkMode] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [tradingMode, setTradingMode] = useState<'demo' | 'live'>('demo')

  // AI信心数据
  const [aiConfidence, setAiConfidence] = useState({
    long: 65,
    short: 25,
    hold: 10
  })

  // 实时思考内容
  const [aiThinking, setAiThinking] = useState([
    {
      id: 1,
      text: "正在分析BTC-USDT当前市场状况...",
      timestamp: "2024-01-15 14:32:15"
    },
    {
      id: 2,
      text: "检测到RSI指标显示超买信号",
      timestamp: "2024-01-15 14:32:20"
    },
    {
      id: 3,
      text: "MACD金叉形成，建议谨慎做多",
      timestamp: "2024-01-15 14:32:25"
    },
    {
      id: 4,
      text: "成交量分析显示买盘力量较强",
      timestamp: "2024-01-15 14:32:30"
    }
  ])

  // 交易记录
  const [trades, setTrades] = useState([
    {
      id: 1,
      time: "2024-01-15 14:32:15",
      pair: "BTC-USDT",
      action: "BUY" as const,
      amount: 0.025,
      price: 42500,
      pnl: +125.50,
      status: "profit" as const
    },
    {
      id: 2,
      time: "2024-01-15 13:15:22",
      pair: "ETH-USDT", 
      action: "SELL" as const,
      amount: 0.5,
      price: 2650,
      pnl: -32.80,
      status: "loss" as const
    }
  ])

  useEffect(() => {
    // 检查系统时间自动切换主题
    const hour = new Date().getHours()
    setIsDarkMode(hour < 6 || hour >= 18)
  }, [])

  useEffect(() => {
    // 应用主题类到body
    if (isDarkMode) {
      document.body.classList.remove('light')
      document.documentElement.classList.remove('light')
    } else {
      document.body.classList.add('light')
      document.documentElement.classList.add('light')
    }
  }, [isDarkMode])

  const toggleTheme = () => {
    setIsDarkMode(!isDarkMode)
  }

  const toggleTradingMode = () => {
    const newMode = tradingMode === 'demo' ? 'live' : 'demo'
    if (newMode === 'live') {
      if (confirm('切换到真实交易模式？请注意真实交易涉及资金风险。')) {
        setTradingMode(newMode)
      }
    } else {
      setTradingMode(newMode)
    }
  }

  return (
    <>
      <Head>
        <title>Athena Trader - 个人交易界面</title>
        <meta name="description" content="个人加密货币交易界面" />
      </Head>

      <div className="min-h-screen transition-all duration-300 animate-theme-transition" 
           style={{ backgroundColor: 'var(--athena-bg-primary)', color: 'var(--athena-text-primary)' }}>
        
        {/* 顶部导航栏 */}
        <header className="border-b transition-all duration-300" 
                style={{ backgroundColor: 'var(--athena-card-bg)', borderColor: 'var(--athena-border)' }}>
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <div className="flex items-center space-x-4">
                <h1 className="text-xl font-bold" style={{ color: 'var(--athena-accent-blue)' }}>
                  Athena Trader
                </h1>
                <span className={`px-2 py-1 rounded text-xs font-medium ${
                  tradingMode === 'live' 
                    ? 'bg-red-100 text-red-800' 
                    : 'bg-blue-100 text-blue-800'
                }`}>
                  {tradingMode === 'live' ? '真实交易' : '模拟交易'}
                </span>
              </div>
              
              <div className="flex items-center space-x-4">
                {/* 交易模式切换 */}
                <ModeToggle tradingMode={tradingMode} onToggle={toggleTradingMode} />
                
                {/* 主题切换 */}
                <ThemeToggle isDarkMode={isDarkMode} onToggle={toggleTheme} />
              </div>
            </div>
          </div>
        </header>

        {/* 主要内容区域 */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-module">
            
            {/* AI信心面板 */}
            <div className="lg:col-span-4">
              <AIConfidence 
                long={aiConfidence.long}
                short={aiConfidence.short}
                hold={aiConfidence.hold}
              />
            </div>

            {/* 实时思考栏 */}
            <div className="lg:col-span-4">
              <AIThinking thoughts={aiThinking} />
            </div>

            {/* 交易记录栏 */}
            <div className="lg:col-span-4">
              <TradeRecords trades={trades} />
            </div>
          </div>

          {/* 主交易区域占位 */}
          <div className="mt-6">
            <div className="athena-card text-center">
              <h3 className="athena-card-header" style={{ color: 'var(--athena-accent-blue)' }}>
                主交易区域
              </h3>
              <p className="athena-card-detail">
                图表、订单簿、技术指标等功能将在后续版本中实现
              </p>
            </div>
          </div>
        </main>
      </div>
    </>
  )
}
