# sinopac-broker-kit

永豐金 Shioaji 期貨下單 + Telegram Bot 設置共用套件。

從主操盤術 AI 交易系統萃取的基礎層，供多個交易系統復用。

---

## 套件內容

```
sinopac-broker-kit/
├── broker/                    ← 永豐金下單核心
│   ├── base.py                  OrderResult / PositionInfo 資料結構
│   ├── broker_sinopac.py        Shioaji Singleton API（登入/報價/K線）
│   ├── contract.py              合約代碼 / 點值對應
│   ├── sinopac.py               SinopacBroker（下單/平倉/查倉）
│   └── simulator.py             SimulatorBroker（模擬模式，不真實下單）
├── tg_kit/                    ← Telegram Bot 工具
│   ├── shared.py                send_message / send_photo 等共用函式
│   └── conflict_handler.py      容器重啟 Conflict 錯誤正確處理器
├── config_templates/          ← 設定檔範本（複製後填入真實值）
│   ├── sinopac_config.json.example
│   ├── bots_config.json.example
│   └── trade_config.json.example
├── docs/                      ← 設置秘笈
│   ├── 01_shioaji_setup.md      永豐 API 申請 + CA 憑證 + 常見錯誤
│   ├── 02_telegram_setup.md     TG Bot 建立 + chat_id + Conflict 處理
│   └── 03_integration.md        如何在新系統接入本套件
├── PROTECTION.md              ← 主系統保護聲明（必讀）
└── README.md
```

---

## 快速開始

### 1. 複製設定檔範本

```bash
cp config_templates/sinopac_config.json.example  data/sinopac_config.json
cp config_templates/bots_config.json.example     data/bots_config.json
cp config_templates/trade_config.json.example    data/trade_config.json
```

填入你的 API Key、TG Token、CA 憑證路徑。

### 2. 安裝依賴

```bash
pip install shioaji python-telegram-bot==22.0
```

### 3. 測試下單連線

```python
from broker.broker_sinopac import get_api

api = get_api()
if api:
    print("永豐 API 連線成功")
else:
    print("連線失敗，請確認 sinopac_config.json")
```

### 4. 加入你的 Bot

```python
from telegram.ext import ApplicationBuilder
from tg_kit.conflict_handler import make_conflict_handler

app = ApplicationBuilder().token(TOKEN).build()
app.add_error_handler(make_conflict_handler("我的Bot"))
```

---

## 設置文件

| 文件 | 說明 |
|------|------|
| [永豐 API 設置秘笈](docs/01_shioaji_setup.md) | 申請帳號、CA憑證、常見錯誤 |
| [Telegram Bot 設置秘笈](docs/02_telegram_setup.md) | BotFather、chat_id、Conflict 處理 |
| [系統整合指南](docs/03_integration.md) | 如何接入你的交易系統 |
| [主系統保護聲明](PROTECTION.md) | 主系統不可修改原則 |

---

## 重要安全提醒

以下檔案包含敏感資訊，**絕對不可 commit 到 Git**：

```
data/sinopac_config.json    ← API Key + 身分證號 + CA 密碼
data/bots_config.json       ← Telegram Bot Token
data/Sinopac.pfx            ← CA 憑證（數位簽章）
```

建議在 `.gitignore` 加入：
```
data/*.json
data/*.pfx
data/*.key
.env
```

---

## 架構原則

- **主系統唯讀**：本套件透過 `state.json` 單向讀取主系統狀態，不修改主系統任何檔案
- **Singleton API**：`broker_sinopac.py` 的 `get_api()` 保持單一連線，自動重連
- **模擬優先**：開發時使用 `SimulatorBroker` 或 `simulation_mode: true`，確認正確後才上線
- **永不拋例外**：API 層失敗時回傳 `None`，讓呼叫端決定 fallback 策略

---

## 相容性

| 套件 | 版本 |
|------|------|
| Python | 3.11+ |
| shioaji | 1.2+ |
| python-telegram-bot | 22.0 |
| pandas | 2.0+ |
