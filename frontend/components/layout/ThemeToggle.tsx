import React from 'react'

interface ThemeToggleProps {
  isDarkMode: boolean
  onToggle: () => void
}

export default function ThemeToggle({ isDarkMode, onToggle }: ThemeToggleProps) {
  return (
    <button
      onClick={onToggle}
      className="athena-theme-toggle"
      aria-label={`切换到${isDarkMode ? '浅色' : '深色'}主题`}
      title={`切换到${isDarkMode ? '浅色' : '深色'}主题`}
    >
      {isDarkMode ? '🌙' : '☀️'}
    </button>
  )
}
