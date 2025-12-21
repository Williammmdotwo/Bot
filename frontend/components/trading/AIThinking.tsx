import React from 'react'

interface AIThinkingItem {
  id: number
  text: string
  timestamp: string
}

interface AIThinkingProps {
  thoughts: AIThinkingItem[]
}

export default function AIThinking({ thoughts }: AIThinkingProps) {
  return (
    <div className="athena-card">
      <h2 className="athena-card-header">
        AI 实时思考
      </h2>
      
      <div className="space-y-3 max-h-96 overflow-y-auto scrollbar-hide">
        {thoughts.map((thought, index) => (
          <div 
            key={thought.id}
            className="athena-thinking-item"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            <div className="flex items-start space-x-2">
              <span className="athena-thinking-badge">
                AI
              </span>
              <p className="flex-1 athena-card-detail leading-relaxed">
                {thought.text}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
