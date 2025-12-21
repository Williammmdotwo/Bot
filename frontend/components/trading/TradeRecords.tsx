import React from 'react'

interface TradeRecord {
  id: number
  time: string
  pair: string
  action: 'BUY' | 'SELL'
  amount: number
  price: number
  pnl: number
  status: 'profit' | 'loss'
}

interface TradeRecordsProps {
  trades: TradeRecord[]
}

export default function TradeRecords({ trades }: TradeRecordsProps) {
  return (
    <div className="athena-card">
      <h2 className="athena-card-header">
        交易记录
      </h2>
      
      <div className="space-y-3 max-h-96 overflow-y-auto scrollbar-hide">
        {trades.map((trade) => (
          <div 
            key={trade.id}
            className="athena-trade-card"
          >
            <div className="flex justify-between items-start mb-2">
              <div className="flex items-center space-x-2">
                <span className={`athena-trade-badge-${trade.action.toLowerCase()}`}>
                  {trade.action}
                </span>
                <span className="athena-card-value font-medium">
                  {trade.pair}
                </span>
              </div>
              <span className={`athena-card-value font-bold ${
                trade.pnl > 0 ? 'athena-trade-profit' : 'athena-trade-loss'
              }`}>
                {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
              </span>
            </div>
            
            <div className="space-y-1">
              <div className="athena-card-detail">
                时间: {trade.time}
              </div>
              <div className="athena-card-detail">
                数量: {trade.amount} @ {trade.price}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
