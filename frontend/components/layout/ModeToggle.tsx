import React from 'react'

interface ModeToggleProps {
  tradingMode: 'demo' | 'live'
  onToggle: () => void
}

export default function ModeToggle({ tradingMode, onToggle }: ModeToggleProps) {
  const handleClick = () => {
    if (tradingMode === 'demo') {
      if (confirm('切换到真实交易模式？请注意真实交易涉及资金风险。')) {
        onToggle()
      }
    } else {
      onToggle()
    }
  }

  return (
    <button
      onClick={handleClick}
      className={`athena-mode-toggle ${
        tradingMode === 'live' 
          ? 'bg-red-600 hover:bg-red-700' 
          : 'bg-blue-600 hover:bg-blue-700'
      }`}
      aria-label={`切换到${tradingMode === 'live' ? '模拟' : '真实'}交易模式`}
      title={`切换到${tradingMode === 'live' ? '模拟' : '真实'}交易模式`}
    >
      {tradingMode === 'live' ? '切换到模拟' : '切换到真实'}
    </button>
  )
}
