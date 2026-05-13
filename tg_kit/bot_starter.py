"""
Telegram Bot 起始範本
======================
複製此檔案到你的系統，加上自己的指令即可。

使用步驟：
  1. 把 config_templates/bots_config.json.example 複製到 data/bots_config.json，填入 Token 和 chat_id
  2. 把這個檔案複製到你的系統
  3. 在「加入你的指令」區塊加上 CommandHandler / MessageHandler
  4. 執行：python bot_starter.py
"""

import asyncio
import json
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from tg_kit.conflict_handler import make_conflict_handler

# ── 設定 ──────────────────────────────────────────────────────────────
_CFG_FILE = Path(__file__).parent.parent / "data" / "bots_config.json"

def _load_cfg(bot_name: str) -> tuple[str, int]:
    """回傳 (token, chat_id)"""
    cfg = json.loads(_CFG_FILE.read_text(encoding="utf-8"))
    bot = cfg[bot_name]
    return bot["token"], int(bot["chat_id"])


# ── 安全守門（只回應授權 chat_id）────────────────────────────────────
def _make_auth_filter(chat_id: int):
    async def _auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat and update.effective_chat.id != chat_id:
            await update.message.reply_text("未授權")
            return
    return _auth


# ── 內建指令 ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot 上線")


# ── 主函式 ────────────────────────────────────────────────────────────
async def main():
    BOT_NAME  = "trade_bot"          # ← 改成 bots_config.json 裡的 key
    DISP_NAME = "交易Bot"            # ← 用於 log 顯示

    token, chat_id = _load_cfg(BOT_NAME)

    app = (
        ApplicationBuilder()
        .token(token)
        .build()
    )

    # Conflict 錯誤處理（容器重啟必備，不可拿掉）
    app.add_error_handler(make_conflict_handler(DISP_NAME))

    # ── 加入你的指令 ──────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    # app.add_handler(CommandHandler("status",  cmd_status))
    # app.add_handler(CommandHandler("buy",     cmd_buy))
    # app.add_handler(CallbackQueryHandler(handle_button))
    # ─────────────────────────────────────────────────────────────────

    print(f"[{DISP_NAME}] 啟動")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
