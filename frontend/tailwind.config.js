/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // Athena Trader 专业配色方案
      colors: {
        // 深色主题
        athena: {
          dark: {
            background: '#121212',
            card_background: '#1E1E1E',
            border: '#2D2D2D',
            text_primary: '#FFFFFF',
            text_secondary: '#B3B3B3',
            text_disabled: '#666666',
            accent_green: '#4CAF50',
            accent_red: '#E53935',
            accent_yellow: '#FFC107',
            accent_blue: '#2196F3',
            accent_purple: '#9C27B0',
            success: '#4CAF50',
            warning: '#FF9800',
            error: '#F44336',
            info: '#2196F3',
            progress_bar_background: '#333333',
            button_primary: '#2D2D2D',
            button_primary_hover: '#3A3A3A',
            button_primary_active: '#4A4A4A',
            button_secondary: '#1E1E1E',
            button_secondary_hover: '#2A2A2A',
            button_accent: '#4CAF50',
            button_accent_hover: '#66BB6A',
            button_danger: '#E53935',
            button_danger_hover: '#EF5350'
          },
          // 浅色主题
          light: {
            background: '#FFFFFF',
            card_background: '#F5F5F5',
            border: '#E0E0E0',
            text_primary: '#000000',
            text_secondary: '#555555',
            text_disabled: '#999999',
            accent_green: '#388E3C',
            accent_red: '#D32F2F',
            accent_yellow: '#FFA000',
            accent_blue: '#1976D2',
            accent_purple: '#7B1FA2',
            success: '#388E3C',
            warning: '#FFA000',
            error: '#D32F2F',
            info: '#1976D2',
            progress_bar_background: '#EEEEEE',
            button_primary: '#EEEEEE',
            button_primary_hover: '#DDDDDD',
            button_primary_active: '#CCCCCC',
            button_secondary: '#FFFFFF',
            button_secondary_hover: '#F0F0F0',
            button_accent: '#388E3C',
            button_accent_hover: '#4CAF50',
            button_danger: '#D32F2F',
            button_danger_hover: '#E53935'
          }
        },
        // 进度条颜色
        progress: {
          buy: '#4CAF50',
          sell: '#E53935',
          hold: '#FFC107'
        },
        // 保持原有颜色作为备用
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
          950: '#172554',
        },
        secondary: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      fontSize: {
        // Athena Trader 字体尺寸规范
        title: ['20px', { lineHeight: '1.5' }],
        label: ['14px', { lineHeight: '1.5' }],
        value: ['16px', { lineHeight: '1.5' }],
        detail: ['12px', { lineHeight: '1.5' }],
        subheading: ['16px', { lineHeight: '1.5' }],
        heading: ['20px', { lineHeight: '1.5' }],
        body: ['14px', { lineHeight: '1.5' }],
        caption: ['12px', { lineHeight: '1.5' }],
        // 保持原有字体尺寸
        'xs': ['0.75rem', { lineHeight: '1rem' }],
        'sm': ['0.875rem', { lineHeight: '1.25rem' }],
        'base': ['1rem', { lineHeight: '1.5rem' }],
        'lg': ['1.125rem', { lineHeight: '1.75rem' }],
        'xl': ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
        '5xl': ['3rem', { lineHeight: '1' }],
        '6xl': ['3.75rem', { lineHeight: '1' }],
        '7xl': ['4.5rem', { lineHeight: '1' }],
        '8xl': ['6rem', { lineHeight: '1' }],
        '9xl': ['8rem', { lineHeight: '1' }],
      },
      spacing: {
        // Athena Trader 间距规范
        'module-gap': '24px',
        'inner-padding': '16px',
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem',
      },
      borderRadius: {
        // Athena Trader 圆角规范
        'module': '8px',
        'button': '20px',
        '4xl': '2rem',
      },
      animation: {
        // Athena Trader 动画规范
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'fade-out': 'fadeOut 0.5s ease-in-out',
        'slide-in-from-left': 'slideInFromLeft 0.4s ease-out',
        'slide-out-to-left': 'slideOutToLeft 0.3s ease-in',
        'bounce-in': 'bounceIn 0.6s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fill-gradient': 'fillGradient 1.2s ease-out',
        'card-lift': 'cardLift 0.2s ease-out',
        'theme-transition': 'themeTransition 0.4s ease-in-out',
        'confetti-burst': 'confettiBurst 1s ease-out',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite'
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeOut: {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        slideInFromLeft: {
          '0%': { transform: 'translateX(-100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        slideOutToLeft: {
          '0%': { transform: 'translateX(0)', opacity: '1' },
          '100%': { transform: 'translateX(-100%)', opacity: '0' },
        },
        bounceIn: {
          '0%': { transform: 'scale(0.3)', opacity: '0' },
          '50%': { transform: 'scale(1.05)' },
          '70%': { transform: 'scale(0.9)' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        fillGradient: {
          '0%': { width: '0%' },
          '100%': { width: 'var(--progress-width)' },
        },
        cardLift: {
          '0%': { transform: 'translateY(0)', boxShadow: '0 4px 12px rgba(0,0,0,0.15)' },
          '100%': { transform: 'translateY(-4px)', boxShadow: '0 8px 24px rgba(0,0,0,0.25)' },
        },
        themeTransition: {
          '0%': { opacity: '1' },
          '50%': { opacity: '0.8' },
          '100%': { opacity: '1' },
        },
        confettiBurst: {
          '0%': { transform: 'scale(0) rotate(0deg)', opacity: '1' },
          '50%': { transform: 'scale(1.2) rotate(180deg)', opacity: '0.8' },
          '100%': { transform: 'scale(0) rotate(360deg)', opacity: '0' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 5px rgba(76, 175, 80, 0.5)' },
          '50%': { boxShadow: '0 0 20px rgba(76, 175, 80, 0.8)' },
        },
      },
      boxShadow: {
        // Athena Trader 阴影规范
        'module': '0 4px 12px rgba(0,0,0,0.15)',
        'module-hover': '0 8px 24px rgba(0,0,0,0.25)',
        'soft': '0 2px 15px -3px rgba(0,0,0,0.07), 0 10px 20px -2px rgba(0,0,0,0.04)',
        'medium': '0 4px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
        'hard': '0 10px 40px -10px rgba(0,0,0,0.15), 0 4px 25px -5px rgba(0,0,0,0.1)',
        'glow': '0 0 20px rgba(59, 130, 246, 0.5)',
        'glow-success': '0 0 20px rgba(76, 175, 80, 0.5)',
        'glow-warning': '0 0 20px rgba(255, 193, 7, 0.5)',
        'glow-danger': '0 0 20px rgba(229, 57, 53, 0.5)',
        'glow-ai': '0 0 20px rgba(33, 150, 243, 0.5)'
      },
      backdropBlur: {
        xs: '2px',
      },
      borderWidth: {
        '3': '3px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
    require('@headlessui/tailwindcss')({
      prefix: 'ui',
    })
  ],
  // 添加 safelist 配置，让 Tailwind 识别我们的自定义类名
  safelist: [
    'athena-btn',
    'athena-card',
    'athena-progress',
    'athena-thinking-item',
    'athena-trade-card',
    'athena-theme-toggle',
    'athena-mode-toggle',
    'athena-confidence-item',
    'athena-confidence-label',
    'athena-confidence-value',
    'athena-confidence-buy',
    'athena-confidence-sell',
    'athena-confidence-hold',
    'athena-thinking-badge',
    'athena-trade-profit',
    'athena-trade-loss',
    'athena-trade-badge-buy',
    'athena-trade-badge-sell'
  ]
}
