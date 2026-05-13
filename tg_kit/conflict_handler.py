"""
Telegram Bot Conflict 錯誤正確處理範本
python-telegram-bot v20+

問題：容器/程序重啟後，Telegram 伺服器仍保有舊的 long-polling 連線（最長 60 秒）。
      新程序啟動後立即收到 Conflict 錯誤，若處理不當會無限循環。

錯誤做法（無效）：
  - delete_webhook()           → 只清 webhook 設定，對 long-polling 完全無效
  - asyncio.sleep(5)           → error handler 的 sleep 不阻止 PTB 內部 retry
  - asyncio.sleep(65)          → 同上，PTB 的 network_retry_loop 獨立運行

正確做法：
  - updater.stop()             → 真正停止 PTB 的 polling loop
  - asyncio.sleep(70)          → 等 Telegram 那端 60 秒 session 過期
  - updater.start_polling()    → 重新建立連線

使用方法：
  將下方 _on_error 函式貼入你的 run_bot() 函式內，
  在 app.add_error_handler(_on_error) 前定義。
"""

import asyncio
import traceback


def make_conflict_handler(bot_name: str = "Bot"):
    """
    建立 Conflict 錯誤處理器。

    bot_name: 用於 log 辨識，例如 "交易Bot"、"分析Bot"

    回傳一個 async def _on_error(update, context) 函式，
    直接傳給 app.add_error_handler() 即可。

    範例：
        app.add_error_handler(make_conflict_handler("交易Bot"))
    """
    async def _on_error(update, context):
        from telegram.error import Conflict, NetworkError, TimedOut
        err = context.error

        if isinstance(err, Conflict):
            print(f"⚠️ {bot_name}：偵測到舊連線（Conflict），停止 polling → 等待 70 秒 → 重啟...")
            try:
                updater = context.application.updater
                if updater.running:
                    await updater.stop()
                await asyncio.sleep(70)
                await updater.start_polling(drop_pending_updates=True)
                print(f"  ✅ {bot_name} 重啟完成")
            except Exception as e:
                print(f"  重啟失敗：{e}")
            return

        if isinstance(err, (NetworkError, TimedOut)):
            print(f"[{bot_name}] 網路短暫中斷：{err}")
            return

        tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
        print(f"[{bot_name} Error] {tb}")

    return _on_error
