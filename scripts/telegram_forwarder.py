#!/usr/bin/env python3
"""
Telegram 转发服务

将 NotificationManager 的 Webhook 消息转发到 Telegram Bot

使用方法：
1. 创建 Telegram Bot 并获取 Token
2. 获取你的 Chat ID
3. 修改下面的配置
4. 运行：python scripts/telegram_forwarder.py

然后修改 config/base.json 中的 webhook_url 为：http://your-server:5000/telegram
"""

from flask import Flask, request, jsonify
import requests
import os
from typing import Dict, Any

# ========== 配置 ==========

# 从环境变量读取，如果没有则使用默认值
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')
PORT = int(os.getenv('PORT', '5000'))
HOST = os.getenv('HOST', '0.0.0.0')

# ========== Flask 应用 ==========

app = Flask(__name__)


def format_alert_message(data: Dict[str, Any]) -> str:
    """
    格式化告警消息为 Telegram 可读格式

    Args:
        data (Dict): 告警数据

    Returns:
        str: 格式化后的消息
    """
    # 根据级别选择 emoji
    level_emoji = {
        'INFO': '📢',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }

    emoji = level_emoji.get(data.get('level', 'INFO'), '📢')

    # 根据类型选择格式
    alert_type = data.get('alert_type', '')

    if alert_type == 'order_filled':
        # 订单成交战报格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
📊 详情：
• 策略: {metadata.get('strategy_id', 'N/A')}
• 交易对: {metadata.get('symbol', 'N/A')}
• 方向: {metadata.get('side', 'N/A')}
• 价格: {metadata.get('price', 0):.6f}
• 数量: {metadata.get('size', 0):.4f}
• 盈亏: {metadata.get('pnl', 'N/A')}
• 收益率: {metadata.get('win_rate', 'N/A')}
• 总权益: {metadata.get('total_equity', 'N/A')}
"""
    elif alert_type == 'heartbeat':
        # 心跳格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
💓 系统状态：健康
运行时间: {metadata.get('uptime_hours', 0):.1f} 小时
"""
    elif alert_type == 'engine_crash':
        # Engine 崩溃格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
📋 详情：
• 策略: {metadata.get('strategy_id', 'N/A')}
• 堆栈: 见日志

⚡ 建议：
{metadata.get('action', '立即检查日志并重启策略')}
"""
    elif alert_type == 'position_mismatch':
        # 持仓不一致格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
📋 详情：
• 策略: {metadata.get('strategy_id', 'N/A')}
• 本地持仓: {metadata.get('local_position', 0)}
• 远程持仓: {metadata.get('remote_position', 0)}
• 差异: {metadata.get('diff_pct', 0):.2%}

⚡ 建议：
{metadata.get('action', '检查持仓同步逻辑')}
"""
    elif alert_type == 'ws_disconnect':
        # WebSocket 断线格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
📋 详情：
• 交易对: {metadata.get('symbol', 'N/A')}
• 重连次数: {metadata.get('retry_count', 0)}

⚡ 建议：
{metadata.get('action', '检查网络连接和 API Key 有效性')}
"""
    else:
        # 通用格式
        title = data.get('title', '')
        message = data.get('message', '')
        metadata = data.get('metadata', {})

        formatted = f"""
{emoji} {title}

{message}

━━━━━━━━━━━━━━━
• 类型: {data.get('alert_type', 'N/A')}
• 级别: {data.get('level', 'N/A')}
• 时间: {data.get('timestamp', 'N/A')}
"""

    # 添加来源
    formatted += f"\n\n🤖 来源: {data.get('source', 'athena-trader')}"

    return formatted.strip()


def send_telegram_message(message: str) -> bool:
    """
    发送消息到 Telegram

    Args:
        message (str): 消息内容

    Returns:
        bool: 是否发送成功
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        response = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"  # 支持 HTML 格式化
        }, timeout=10)

        if response.status_code == 200:
            return True
        else:
            print(f"❌ Telegram API 错误: {response.status_code}, {response.text}")
            return False

    except Exception as e:
        print(f"❌ 发送失败: {e}")
        return False


@app.route('/telegram', methods=['POST'])
def forward_to_telegram():
    """
    Webhook 端点，接收 NotificationManager 的消息并转发到 Telegram
    """
    try:
        # 获取数据
        data = request.json

        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        # 格式化消息
        message = format_alert_message(data)

        # 发送到 Telegram
        success = send_telegram_message(message)

        if success:
            return jsonify({"status": "ok", "message": "Message sent"})
        else:
            return jsonify({"status": "error", "message": "Failed to send message"}), 500

    except Exception as e:
        print(f"❌ 处理异常: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    健康检查端点
    """
    return jsonify({
        "status": "healthy",
        "service": "telegram_forwarder",
        "telegram_configured": TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN' and TELEGRAM_CHAT_ID != 'YOUR_CHAT_ID'
    })


@app.route('/', methods=['GET'])
def index():
    """
    首页
    """
    return jsonify({
        "service": "Athena Trader Telegram Forwarder",
        "version": "1.0.0",
        "endpoints": {
            "/telegram": "POST - Webhook endpoint for NotificationManager",
            "/health": "GET - Health check"
        }
    })


# ========== 主程序 ==========

if __name__ == '__main__':
    print("=" * 50)
    print("🤖 Athena Trader Telegram Forwarder")
    print("=" * 50)
    print()
    print(f"📡 监听地址: {HOST}:{PORT}")
    print(f"🔌 Webhook URL: http://{HOST}:{PORT}/telegram")
    print()

    # 检查配置
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN':
        print("⚠️  警告: TELEGRAM_BOT_TOKEN 未配置！")
        print("   请设置环境变量或修改脚本中的配置")
        print()

    if TELEGRAM_CHAT_ID == 'YOUR_CHAT_ID':
        print("⚠️  警告: TELEGRAM_CHAT_ID 未配置！")
        print("   请设置环境变量或修改脚本中的配置")
        print()

    if TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN' and TELEGRAM_CHAT_ID != 'YOUR_CHAT_ID':
        print("✅ Telegram Bot 配置完成")
    else:
        print("⚠️  请先配置 Telegram Bot，否则无法发送消息")
        print()
        print("📝 配置步骤：")
        print("   1. 在 Telegram 中找到 @BotFather")
        print("   2. 发送 /newbot 创建机器人")
        print("   3. 获取 Bot Token")
        print("   4. 给机器人发送消息")
        print("   5. 访问 https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates 获取 Chat ID")
        print()

    print("=" * 50)
    print("🚀 启动服务...")
    print("=" * 50)
    print()

    # 启动 Flask 应用
    app.run(host=HOST, port=PORT, debug=False)
