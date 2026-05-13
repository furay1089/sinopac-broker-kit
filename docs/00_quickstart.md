# sinopac-broker-kit 快速上手指南

> 適合對象：要在新系統中接入永豐金下單 + Telegram Bot 的開發者

---

## 這個套件是什麼

從主操盤術 AI 交易系統萃取的共用下單基礎層，讓你不用從零建立：

- **永豐金 Shioaji 下單**（進場 / 平倉 / 查倉 / 即時報價）
- **Telegram Bot 工具**（傳送通知 / Conflict 錯誤處理）
- **設定檔範本**（直接複製填入）
- **設置秘笈**（API 申請 / TG Bot 建立 / 整合方式）

---

## 目錄結構

```
sinopac-broker-kit/
├── broker/                    ← 永豐金下單核心（複製到你的系統）
│   ├── base.py                  OrderResult / PositionInfo 資料結構
│   ├── broker_sinopac.py        Shioaji Singleton API（登入/報價/K線）
│   ├── contract.py              合約代碼 / 點值對應
│   ├── sinopac.py               SinopacBroker（下單/平倉/查倉）
│   └── simulator.py             SimulatorBroker（模擬模式，不真實下單）
├── tg_kit/                    ← Telegram Bot 工具（複製到你的系統）
│   ├── shared.py                send_message / send_photo 等共用函式
│   └── conflict_handler.py      容器重啟 Conflict 錯誤正確處理器
├── config_templates/          ← 設定檔範本（複製後填入真實值）
│   ├── sinopac_config.json.example
│   ├── bots_config.json.example
│   └── trade_config.json.example
├── docs/                      ← 設置秘笈
│   ├── 00_quickstart.md         本文件
│   ├── 01_shioaji_setup.md      永豐 API 申請 + CA 憑證 + 常見錯誤
│   ├── 02_telegram_setup.md     TG Bot 建立 + chat_id + Conflict 處理
│   └── 03_integration.md        完整整合指南（含 Docker 多容器）
└── PROTECTION.md              ← 主系統保護聲明（必讀）
```

---

## 五步驟快速開始

### 第一步：建立你的新系統目錄結構

把 `broker/` 和 `tg_kit/` 複製到你的新系統根目錄：

```
your_system/
├── broker/       ← 從本套件複製
├── tg_kit/       ← 從本套件複製
├── data/         ← 放設定檔（此目錄不可 commit）
└── main.py
```

---

### 第二步：複製設定檔範本

```bash
cp config_templates/sinopac_config.json.example  data/sinopac_config.json
cp config_templates/bots_config.json.example     data/bots_config.json
cp config_templates/trade_config.json.example    data/trade_config.json
```

**`sinopac_config.json`** — 填入永豐金帳戶資訊：

```json
{
    "api_key":    "你的永豐API金鑰",
    "secret_key": "你的永豐API密鑰",
    "person_id":  "你的身分證號",
    "ca_path":    "/app/data/Sinopac.pfx",
    "ca_passwd":  "你的CA憑證密碼",
    "simulation": true
}
```

**`bots_config.json`** — 填入 Telegram Bot Token：

```json
{
    "trade_bot": {
        "token":   "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ",
        "chat_id": "987654321"
    }
}
```

> 不知道怎麼取得這些值？請看 [01\_shioaji\_setup.md](01_shioaji_setup.md) 和 [02\_telegram\_setup.md](02_telegram_setup.md)

---

### 第三步：安裝依賴

```bash
pip install shioaji==1.2.0 python-telegram-bot==22.0 pandas
```

> ⚠️ `python-telegram-bot` 版本很重要，本套件基於 v20+（async 架構），v13 完全不相容

---

### 第四步：驗證連線

```python
from broker.broker_sinopac import get_api

api = get_api()
if api:
    print("永豐 API 連線成功")
else:
    print("連線失敗，請確認 sinopac_config.json")
```

---

### 第五步：開始開發（先用模擬模式）

把 `sinopac_config.json` 的 `"simulation": true` 保持開啟，先跑通邏輯：

```python
from broker.simulator import SimulatorBroker

broker = SimulatorBroker()
result = broker.place_order(action="BUY", lots=1)
print(result.success, result.message)   # 不會真的送出訂單
```

確認邏輯無誤後，再把 `simulation` 改為 `false` 上線。

---

## 常用操作範例

### 下單

```python
from broker.sinopac import SinopacBroker

broker = SinopacBroker()

# 做多 1 口
result = broker.place_order(action="BUY", lots=1)
print(result.success, result.order_id, result.message)

# 做空 1 口
result = broker.place_order(action="SELL", lots=1)
```

### 平倉

```python
result = broker.close_position()
print(result.success, result.message)
```

### 查詢持倉

```python
for p in broker.get_all_positions():
    print(f"{p.code}  {p.direction}  {p.lots}口  均價 {p.avg_price}")
```

### 即時報價

```python
from broker.broker_sinopac import get_snapshot, get_tx_snapshot

# 加權指數
snap = get_snapshot()
print(snap["close"])

# 台指期近月（微台指）
tx = get_tx_snapshot(contract_code="XMTX", month_setting=0)
print(tx["price"])
```

### 傳送 Telegram 通知

```python
import asyncio
from tg_kit.shared import send_message

asyncio.run(send_message("系統啟動完成"))
```

### Telegram Bot 啟動（含 Conflict 處理）

```python
from telegram.ext import ApplicationBuilder
from tg_kit.conflict_handler import make_conflict_handler

app = ApplicationBuilder().token(TOKEN).build()
app.add_error_handler(make_conflict_handler("我的交易Bot"))
await app.run_polling(drop_pending_updates=True)
```

---

## 讀取主系統狀態（只讀）

如果你的系統需要知道主操盤術系統的當前方向或持倉：

```python
import json

def read_main_state(state_path: str) -> dict:
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)

state = read_main_state("/path/to/ai_trading/data/state.json")
trend = state.get("trend")   # "online" / "offline"
lots  = state.get("lots", 0)
```

> ⚠️ **只讀，絕對不寫入**。你的系統要維護自己獨立的狀態檔。

Docker 掛載時加 `:ro`（唯讀）防止意外寫入：

```yaml
volumes:
  - ./ai_trading/data/state.json:/app/shared/state.json:ro
```

---

## 安全注意事項

### 這些檔案絕對不可 commit 到 Git

```
data/sinopac_config.json    ← API Key + 身分證號 + CA 密碼
data/bots_config.json       ← Telegram Bot Token
data/Sinopac.pfx            ← CA 憑證（數位簽章）
```

確認 `.gitignore` 已包含：

```
data/*.json
data/*.pfx
data/*.key
.env
```

---

## 核心設計原則

| 原則 | 說明 |
|------|------|
| **主系統唯讀** | 只透過 `state.json` 單向讀取，不修改主系統任何檔案 |
| **Singleton API** | `get_api()` 保持單一連線，自動重連，不要長期快取 `api` 物件 |
| **模擬優先** | 開發期全程 `simulation: true`，上線前再切換 |
| **永不拋例外** | API 層失敗回傳 `None`，呼叫端決定 fallback |
| **同帳號單一連線** | 同一帳號不能多個程序同時連線（Shioaji 硬限制） |

---

## 常見問題

| 問題 | 解法 |
|------|------|
| `LoginError: api_key invalid` | 重新到永豐後台取得 API Key |
| `CA Error: wrong password` | 確認 `ca_passwd` 欄位正確 |
| `FileNotFoundError: .pfx` | 確認容器內 `ca_path` 路徑正確 |
| `Conflict (409)` | 使用 `make_conflict_handler()` 正確處理，勿用 `delete_webhook` |
| `Unauthorized` (TG) | Bot Token 錯誤，重新從 BotFather 取得 |
| 盤中以外無法連線 | 正式環境只在盤中有效；開發用 `simulation: true` |

---

## 延伸閱讀

| 文件 | 說明 |
|------|------|
| [01\_shioaji\_setup.md](01_shioaji_setup.md) | 永豐 API 申請、CA 憑證申請、登入測試 |
| [02\_telegram\_setup.md](02_telegram_setup.md) | BotFather 建立 Bot、取得 chat\_id、Conflict 錯誤完整說明 |
| [03\_integration.md](03_integration.md) | 完整整合指南（含 Docker 多容器 compose 範例） |
| [PROTECTION.md](../PROTECTION.md) | 主系統保護聲明，開發前必讀 |
