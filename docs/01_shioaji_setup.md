# 永豐金 Shioaji API 申請與設置秘笈

## 一、申請永豐金帳戶與 API 權限

### 1. 開立永豐證券/期貨帳戶
- 前往永豐金證券官網 或 永豐期貨官網
- 完成線上開戶（需上傳身分證正反面 + 銀行帳戶資料）
- 等待審核（通常 1~3 個工作天）

### 2. 申請 API 交易權限
- 登入永豐金證券網站 → 會員服務 → API 申請
- 填寫開發用途（建議填：自動化交易程式）
- 申請後取得：
  - **API Key**（`api_key`）
  - **Secret Key**（`secret_key`）

> ⚠️ **安全警告**：API Key + Secret Key = 你的帳號完全存取權，絕對不可放入 Git 或傳給他人

---

## 二、取得 CA 憑證（期貨下單必備）

CA 憑證是期貨下單的數位簽章，**不申請就只能看盤，無法下單**。

### 申請步驟
1. 登入永豐期貨網站
2. 進入「電子憑證申請」
3. 下載後得到一個 `.pfx` 檔案（例如 `Sinopac.pfx`）
4. 記下你設定的 **CA 憑證密碼**

### 設定路徑
```json
{
    "ca_path":   "/app/data/Sinopac.pfx",
    "ca_passwd": "你的憑證密碼"
}
```

> ⚠️ `.pfx` 憑證檔也屬敏感資料，不可 commit 到 Git

---

## 三、安裝 shioaji

```bash
pip install shioaji
```

目前穩定版為 `shioaji>=1.2`，建議 pin 住版本避免 API 變動：

```
shioaji==1.2.0
```

---

## 四、設定 `sinopac_config.json`

```json
{
    "api_key":    "你的永豐API金鑰",
    "secret_key": "你的永豐API密鑰",
    "person_id":  "你的身分證號（登入用）",
    "ca_path":    "/app/data/Sinopac.pfx",
    "ca_passwd":  "你的CA憑證密碼",
    "simulation": false
}
```

| 欄位 | 說明 |
|------|------|
| `api_key` | 永豐後台取得的 API Key |
| `secret_key` | 永豐後台取得的 Secret Key |
| `person_id` | 身分證號（登入驗證） |
| `ca_path` | `.pfx` 憑證檔的**容器內絕對路徑** |
| `ca_passwd` | 申請憑證時設定的密碼 |
| `simulation` | `false` = 真實下單；`true` = 模擬模式 |

---

## 五、登入測試

```python
import shioaji as sj
import json

cfg = json.load(open("data/sinopac_config.json"))
api = sj.Shioaji(simulation=cfg["simulation"])
api.login(
    api_key    = cfg["api_key"],
    secret_key = cfg["secret_key"],
    fetch_contract = True,
)
print("登入成功")
print(api.Contracts.Futures.TXF)   # 印出台指期合約列表
```

---

## 六、啟用期貨下單（activate_ca）

登入後第一次需要啟用 CA：

```python
api.activate_ca(
    ca_path   = cfg["ca_path"],
    ca_passwd = cfg["ca_passwd"],
    person_id = cfg["person_id"],
)
print("CA 啟用成功")
```

> 重要：`activate_ca` 在容器重啟後必須重新執行。
> `broker/sinopac.py` 的 `SinopacBroker` 已在 `_ensure_ready()` 中自動處理。

---

## 七、常見錯誤排除

| 錯誤訊息 | 原因 | 解法 |
|---------|------|------|
| `LoginError: api_key invalid` | Key 輸入錯誤或已過期 | 重新到永豐後台取得 |
| `CA Error: wrong password` | 憑證密碼錯誤 | 確認 `ca_passwd` 欄位 |
| `Not ready` | CA 尚未啟用 | 呼叫 `activate_ca()` |
| `FileNotFoundError: .pfx` | 憑證路徑錯誤 | 確認容器內路徑正確 |
| `Shioaji not installed` | 套件未安裝 | `pip install shioaji` |
| 登入後 30 分鐘斷線 | Shioaji 有心跳機制 | 使用 `get_api()` Singleton（已處理自動重連） |

---

## 八、Docker 容器掛載設定

```yaml
# docker-compose.yml 範例
volumes:
  - ./data/sinopac_config.json:/app/data/sinopac_config.json:ro
  - ./data/Sinopac.pfx:/app/data/Sinopac.pfx:ro
```

> `:ro` = read-only，防止容器意外修改敏感檔案

---

## 九、注意事項

1. **永豐 API 正式環境只在台灣盤中時段可用**（09:00~13:45 期貨，加上夜盤）
2. `simulation=True` 可在非盤中使用，用於開發測試
3. CA 憑證有效期限通常為 1 年，過期需重新申請
4. 同一帳號不可同時建立多個 API 連線（會被踢掉）
