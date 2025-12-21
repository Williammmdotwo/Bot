import React from 'react'

interface AIConfidenceProps {
  long: number
  short: number
  hold: number
}

export default function AIConfidence({ long, short, hold }: AIConfidenceProps) {
  return (
    <div className="athena-card">
      <h2 className="athena-card-header">
        AI 信心指数
      </h2>
      
      <div className="space-y-4">
        {/* 做多信心 */}
        <div className="athena-confidence-item">
          <div className="athena-confidence-label">
            <span className="athena-card-label">做多</span>
            <span className="athena-confidence-value athena-confidence-buy">
              {long}%
            </span>
          </div>
          <div className="athena-progress">
            <div 
              className="athena-progress-fill athena-progress-buy"
              style={{ 
                width: `${long}%`,
                '--progress-width': `${long}%`
              } as React.CSSProperties}
            />
          </div>
        </div>
        
        {/* 做空信心 */}
        <div className="athena-confidence-item">
          <div className="athena-confidence-label">
            <span className="athena-card-label">做空</span>
            <span className="athena-confidence-value athena-confidence-sell">
              {short}%
            </span>
          </div>
          <div className="athena-progress">
            <div 
              className="athena-progress-fill athena-progress-sell"
              style={{ 
                width: `${short}%`,
                '--progress-width': `${short}%`
              } as React.CSSProperties}
            />
          </div>
        </div>
        
        {/* 持有信心 */}
        <div className="athena-confidence-item">
          <div className="athena-confidence-label">
            <span className="athena-card-label">持有</span>
            <span className="athena-confidence-value athena-confidence-hold">
              {hold}%
            </span>
          </div>
          <div className="athena-progress">
            <div 
              className="athena-progress-fill athena-progress-hold"
              style={{ 
                width: `${hold}%`,
                '--progress-width': `${hold}%`
              } as React.CSSProperties}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
