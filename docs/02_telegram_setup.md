# Telegram Bot 設置秘笈

## 一、建立 Bot（BotFather）

### 步驟
1. 在 Telegram 搜尋 `@BotFather`
2. 發送 `/newbot`
3. 輸入 Bot 的**顯示名稱**（例如：`我的交易機器人`）
4. 輸入 Bot 的**用戶名**（必須以 `bot` 結尾，例如：`my_trading_bot`）
5. BotFather 回傳你的 **Bot Token**，格式如：
   ```
   1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
   ```

> ⚠️ Token 等同於 Bot 的完整控制權，絕對不可放入 Git

### 建議每個系統獨立一個 Bot
| Bot 名稱 | 用途 |
|---------|------|
| `交易Bot` | 接收下單指令、顯示持倉 |
| `分析Bot` | 盤前/盤後分析報告 |
| `系統管理Bot` | 部署、重啟、備份控制 |

---

## 二、取得你的 chat_id

### 方法一（最簡單）：用 @userinfobot
1. 搜尋 `@userinfobot`
2. 發送 `/start`
3. 它會回傳你的 `Id`（就是 `chat_id`）

### 方法二：程式取得
```python
import asyncio
from telegram import Bot

async def main():
    bot = Bot(token="你的Bot Token")
    # 先對 Bot 發送任意訊息，再執行以下
    updates = await bot.get_updates()
    for u in updates:
        print(u.message.chat_id)

asyncio.run(main())
```

> ⚠️ 必須先對 Bot 發送過訊息，`get_updates()` 才有資料

---

## 三、設定 `bots_config.json`

```json
{
    "trade_bot": {
        "token":   "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
        "chat_id": "987654321"
    }
}
```

---

## 四、安裝 python-telegram-bot

```bash
pip install python-telegram-bot==22.0
```

> ⚠️ 版本非常重要！v13 與 v20+ 的 API 完全不同
> 本套件基於 **v20+（async 架構）**

---

## 五、最小可用 Bot 範例

```python
import asyncio
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

cfg = json.load(open("data/bots_config.json"))
TOKEN   = cfg["trade_bot"]["token"]
CHAT_ID = int(cfg["trade_bot"]["chat_id"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot 上線！")

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # 加入 Conflict 錯誤處理（容器重啟必備）
    from tg_kit.conflict_handler import make_conflict_handler
    app.add_error_handler(make_conflict_handler("交易Bot"))
    
    await app.run_polling(drop_pending_updates=True)

asyncio.run(main())
```

---

## 六、處理容器重啟的 Conflict 錯誤（必讀）

### 問題說明
容器/程序重啟後，Telegram 伺服器仍保有舊的 long-polling 連線（最長 60 秒）。
新程序啟動後立刻收到 `Conflict (409)` 錯誤。

### 錯誤的處理方式（無效）
```python
# ❌ 這些完全無效
await bot.delete_webhook()        # 只清 webhook，對 long-polling 無用
await asyncio.sleep(5)            # 太短，PTB 內部 retry 不受控
await asyncio.sleep(65)           # 雖夠長，但 error handler 的 sleep 不阻止 PTB 的 retry loop
```

### 正確的處理方式
```python
# ✅ 正確做法：停止 polling → 等待 → 重啟
if isinstance(err, Conflict):
    updater = context.application.updater
    if updater.running:
        await updater.stop()        # 真正停止 PTB 的 polling loop
    await asyncio.sleep(70)         # 等 Telegram 那端 60 秒 session 過期
    await updater.start_polling(drop_pending_updates=True)
```

### 使用本套件的現成處理器
```python
from tg_kit.conflict_handler import make_conflict_handler
app.add_error_handler(make_conflict_handler("我的Bot"))
```

### 根本原因
PTB v20+ 的 `network_retry_loop` 在內部線程獨立運行，error handler 的 `sleep` 不會阻止它繼續 retry。
唯一方法是呼叫 `updater.stop()` 真正中止 loop，等待 Telegram 那端 session 過期後再重啟。

---

## 七、安全設定：限制 Bot 只回應你

```python
async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """在所有 handler 前執行，過濾非授權使用者"""
    if update.effective_chat.id != CHAT_ID:
        await update.message.reply_text("未授權")
        return  # 不呼叫 context.application.process_update()

# 加入最前面的 handler
from telegram.ext import TypeHandler
app.add_handler(TypeHandler(Update, auth_check), group=-1)
```

---

## 八、傳送主動通知（非指令觸發）

```python
import asyncio
from telegram import Bot

async def notify(token: str, chat_id: int, message: str):
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")

# 同步環境呼叫
asyncio.run(notify(TOKEN, CHAT_ID, "<b>警報：</b>指數跌破生命線"))
```

---

## 九、常見錯誤排除

| 錯誤訊息 | 原因 | 解法 |
|---------|------|------|
| `Unauthorized` | Token 錯誤 | 重新從 BotFather 取得 Token |
| `Chat not found` | chat_id 錯誤 | 先對 Bot 發訊息，再重新取得 |
| `Conflict (409)` | 雙重連線 | 使用 `conflict_handler.py` 正確處理 |
| `Flood control (429)` | 訊息發太快 | 加 `await asyncio.sleep(1)` 間隔 |
| `Message is not modified` | 嘗試編輯相同內容 | 加 try/except 忽略此錯誤 |

---

## 十、Docker 容器設定

```yaml
# docker-compose.yml 範例
environment:
  - TG_TOKEN=你的Token（或用 .env 檔）
volumes:
  - ./data/bots_config.json:/app/data/bots_config.json:ro
```

> 建議將 Token 放在 `.env` 而非直接寫進 docker-compose，並將 `.env` 加入 `.gitignore`
