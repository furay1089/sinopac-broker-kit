"""
共用工具 — 所有 Bot 共享
"""
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

BOTS_CONFIG_FILE = Path(__file__).parent.parent / "data" / "bots_config.json"


def load_bots_config() -> dict:
    return json.loads(BOTS_CONFIG_FILE.read_text(encoding="utf-8"))


def get_bot_token(bot_key: str) -> str:
    return load_bots_config()[bot_key]["token"]


def get_chat_id(bot_key: str) -> int:
    return load_bots_config()[bot_key]["chat_id"]


def make_send_fn(token: str, chat_id: int):
    """建立 send_telegram_message 函式"""
    import requests
    def send(msg: str, parse_mode: str = "HTML"):
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": parse_mode},
                timeout=10,
            )
        except Exception as e:
            print(f"[TG送訊失敗] {e}")
    return send


BACK_MAIN = "🔙 返回主選單"


def get_settlement_info() -> str:
    """
    計算台指期下一個結算日（每月第3個星期三）及倒數天數。
    回傳格式化字串，供各 Bot 插入報告。
    """
    from datetime import date, timedelta
    today = date.today()

    def _third_wed(year, month):
        d = date(year, month, 1)
        first_wed = d + timedelta(days=(2 - d.weekday()) % 7)
        return first_wed + timedelta(weeks=2)

    settle = _third_wed(today.year, today.month)
    if settle < today:                          # 本月結算日已過
        m, y = today.month + 1, today.year
        if m > 12:
            m, y = 1, y + 1
        settle = _third_wed(y, m)

    days   = (settle - today).days
    date_s = f"{settle.month}月{settle.day}日"

    if days == 0:
        return f"🔔 今日結算　{date_s}"
    elif days <= 5:
        return f"⚠️ 結算倒數 {days} 天　{date_s}"
    else:
        return f"📅 本月結算：{date_s}　倒數 {days} 天"
