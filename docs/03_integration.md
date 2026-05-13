# 如何在新系統中接入 sinopac-broker-kit

## 一、目錄結構

```
your_trading_system/
├── broker/                    ← 從本套件複製過來（或 git submodule）
│   ├── __init__.py
│   ├── base.py
│   ├── broker_sinopac.py      ← Shioaji Singleton + 快照 + K線
│   ├── contract.py            ← 合約代碼對應
│   ├── sinopac.py             ← SinopacBroker（進場/平倉/查倉）
│   └── simulator.py           ← 模擬下單（不需真實 API）
├── tg_kit/                    ← 從本套件複製過來
│   ├── shared.py              ← send_message / send_photo 等共用函式
│   └── conflict_handler.py    ← Conflict 錯誤處理器
├── data/
│   ├── sinopac_config.json    ← 永豐 API 設定（不可 commit）
│   ├── bots_config.json       ← TG Bot Token（不可 commit）
│   └── trade_config.json      ← 下單設定
└── main.py                    ← 你的主程式
```

---

## 二、快速接入下單

### 基本下單流程

```python
from broker.sinopac import SinopacBroker
from broker.base import OrderResult

# 初始化（每次操作前取得最新 API，不需長期保存）
broker = SinopacBroker()

# 做多 1 口
result: OrderResult = broker.place_order(
    action = "BUY",
    lots   = 1,
)
print(result.success, result.order_id, result.message)

# 平倉
result = broker.close_position()
print(result.success, result.message)
```

### 查詢持倉

```python
from broker.sinopac import SinopacBroker

broker = SinopacBroker()
positions = broker.get_all_positions()
for p in positions:
    print(f"{p.code} {p.direction} {p.lots}口 均價{p.avg_price}")
```

---

## 三、使用模擬模式開發

在 `trade_config.json` 設定 `"simulation_mode": true`，或直接用 `SimulatorBroker`：

```python
from broker.simulator import SimulatorBroker

broker = SimulatorBroker()
result = broker.place_order("BUY", lots=1)
print(result)   # 不會真的送出訂單
```

開發時**強烈建議全程使用模擬模式**，確認邏輯正確後再切換 `simulation_mode: false`。

---

## 四、取得即時報價

```python
from broker.broker_sinopac import get_snapshot, get_tx_snapshot

# 加權指數
snap = get_snapshot()
print(snap["close"])   # 即時收盤價

# 台指期近月合約
tx_snap = get_tx_snapshot(contract_code="XMTX", month_setting=0)
print(tx_snap["price"])  # 微台指近月即時價
```

---

## 五、接入 Telegram Bot

### 啟動通知

```python
import asyncio
from tg_kit.shared import send_message

async def on_start():
    await send_message("系統啟動完成")

asyncio.run(on_start())
```

### Conflict 錯誤處理（容器重啟必備）

```python
from telegram.ext import ApplicationBuilder
from tg_kit.conflict_handler import make_conflict_handler

app = ApplicationBuilder().token(TOKEN).build()
app.add_error_handler(make_conflict_handler("我的交易Bot"))
```

---

## 六、與主系統 state.json 整合（只讀）

如果你的系統需要讀取主操盤術系統的狀態（例如：確認當前波段方向），
採用**單向讀取**原則：

```python
import json

def read_main_state(state_path: str) -> dict:
    """只讀主系統狀態，絕對不寫入"""
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)

state = read_main_state("/path/to/ai_trading/data/state.json")
trend = state.get("trend")  # "online" / "offline"
lots  = state.get("lots", 0)
```

> ⚠️ **主系統 state.json 只能讀取，不可寫入**
> 你的系統應維護自己獨立的狀態檔

---

## 七、Docker 多容器部署

```yaml
# docker-compose.yml 多系統範例
services:
  ai_trading:
    image: ai_trading_img
    volumes:
      - ./ai_trading/data:/app/data
    restart: unless-stopped

  daywin:
    image: daywin_img
    volumes:
      - ./daywin/data:/app/data
      - ./ai_trading/data/state.json:/app/shared/state.json:ro   # 只讀掛載
    restart: unless-stopped
```

---

## 八、重要原則

### 永遠不要修改主系統
- `broker/` 和 `tg_kit/` 是共用層，可以自由修改和擴充
- 主系統的 `engine/`、`tg_bot/`、`scheduler/` **不可因整合需求而修改**
- 衝突邏輯寫在你自己的系統裡，不在主系統

### API 連線隔離
- 每個容器有自己的 Shioaji 連線
- 同一個帳號不能多個程序同時連線（Shioaji 限制）
- 如果需要共享資料，透過檔案（state.json 只讀）或 API 傳遞

### 安全防護
- `broker/sinopac.py` 的 `place_order()` 有前置檢查：`enabled=false` → 拒絕下單
- 開發期間保持 `"simulation_mode": true`
- 上線前手動將 `simulation_mode` 切換為 `false`，並確認 `enabled: true`
