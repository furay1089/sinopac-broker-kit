# sinopac-broker-kit — 開發準則

## 這個套件是什麼

從主操盤術 AI 交易系統（`ai_trading_system`）萃取的共用基礎層，供 daywin、新系統等復用。
本套件只負責：永豐金 Shioaji 下單、Telegram Bot 工具、設定檔範本、設置秘笈。

GitHub：https://github.com/furay1089/sinopac-broker-kit

---

## 核心設計原則

1. **主系統唯讀**：透過 `state.json` 單向讀取主系統狀態，絕對不寫入主系統任何檔案
2. **Singleton API**：`get_api()` 保持單一連線自動重連，不可長期快取 `api` 物件
3. **模擬優先**：開發期全程 `simulation: true`，確認邏輯正確後再切換上線
4. **永不拋例外**：API 層失敗回傳 `None`，由呼叫端決定 fallback
5. **同帳號單一連線**：Shioaji 硬限制，同一帳號不可多程序同時連線

---

## 目錄結構

```
broker/               ← 永豐金下單核心
  base.py               OrderResult / PositionInfo
  broker_sinopac.py     Singleton API + 快照 + K線
  contract.py           合約代碼對應
  sinopac.py            SinopacBroker（下單/平倉/查倉）
  simulator.py          SimulatorBroker（模擬模式）
tg_kit/               ← TG Bot 工具
  shared.py             send_message / send_photo
  conflict_handler.py   make_conflict_handler(bot_name)
  bot_starter.py        新 Bot 起始範本（建新 Bot 從這裡複製）
config_templates/     ← 設定檔範本（複製後填入真實值）
docs/                 ← 設置秘笈
  00_quickstart.md      快速上手（新開發者從這裡開始）
  01_shioaji_setup.md   永豐 API 申請 + CA 憑證
  02_telegram_setup.md  TG Bot 建立 + chat_id + Conflict
  03_integration.md     完整整合指南（含 Docker 多容器）
PROTECTION.md         ← 主系統保護聲明
```

---

## 建新系統 TG Bot 的方式

用戶說「參考 sinopac-broker-kit 幫我建 xxx 系統的 Bot」時：
→ 直接以 `tg_kit/bot_starter.py` 為底，加上指定的 CommandHandler / CallbackQueryHandler，不需從頭解釋架構。

---

## 安全守則

以下檔案絕對不可 commit：

```
data/sinopac_config.json    ← API Key + 身分證號 + CA 密碼
data/bots_config.json       ← Telegram Bot Token
data/Sinopac.pfx            ← CA 憑證
```

`.gitignore` 已設定排除 `data/` 目錄，修改前確認仍有效。

---

## Conflict 錯誤唯一正確修法

```python
from tg_kit.conflict_handler import make_conflict_handler
app.add_error_handler(make_conflict_handler("Bot名稱"))
```

原理：`updater.stop() → asyncio.sleep(70) → updater.start_polling()`
禁止用：`delete_webhook()` 或在 error handler 裡單純 `sleep()`（對 PTB v20 無效）

---

## 與主系統的邊界

- 本套件不包含、不參照、不修改主系統的 `engine/`、`scheduler/`、`tg_bot/`
- 如需讀取主系統信號，只能讀 `state.json`（掛載時加 `:ro`）
- 衝突判斷邏輯寫在各自的新系統內，不回頭改本套件或主系統
