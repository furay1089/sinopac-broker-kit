"""
永豐金 Shioaji API 整合層

功能：
  - get_api()          : 取得已登入的 Singleton API（自動重連）
  - get_snapshot()     : 即時加權指數報價（open/high/low/close/total_amount）
  - get_today_kbars1m(): 今日 1 分K → 讓 data_loader resample 成 5 分K

設計原則：
  - 永遠不 raise，失敗時回傳 None，讓 data_loader fallback 到 yfinance
  - Singleton 保持連線，每次呼叫 get_api() 若斷線自動重連一次
"""

import json
import threading
from pathlib import Path
from datetime import date, timedelta

import pandas as pd

_CONFIG_FILE    = Path(__file__).parent.parent / "data" / "sinopac_config.json"
_api            = None
_lock           = threading.Lock()
_last_login_ts  = 0.0
_RECONNECT_SEC  = 8 * 3600


# ── 設定 ──────────────────────────────────────────────

def _load_cfg() -> dict:
    return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))


def _api_alive(api) -> bool:
    try:
        _ = api.Contracts.Futures
        return True
    except Exception:
        return False


# ── API Singleton（自動重連 + 定期刷新）──────────────

def get_api():
    global _api, _last_login_ts
    import time
    with _lock:
        now = time.time()

        if _api is not None:
            stale = (now - _last_login_ts) > _RECONNECT_SEC
            if stale or not _api_alive(_api):
                reason = "定期重連" if stale else "連線中斷"
                print(f"[Shioaji] {reason}，重新登入...")
                try:
                    _api.logout()
                except Exception:
                    pass
                _api = None
            else:
                return _api

        try:
            import shioaji as sj
            cfg  = _load_cfg()
            api  = sj.Shioaji(simulation=cfg.get("simulation", False))
            api.login(
                api_key        = cfg["api_key"],
                secret_key     = cfg["secret_key"],
                fetch_contract = True,
            )
            _api           = api
            _last_login_ts = now
            print("[Shioaji] 登入成功")
            return _api
        except FileNotFoundError:
            return None
        except Exception as e:
            print(f"[Shioaji] 登入失敗：{e}")
            return None


def reset_api():
    """強制重置連線（斷線時由外部呼叫）"""
    global _api
    with _lock:
        if _api:
            try:
                _api.logout()
            except Exception:
                pass
        _api = None


def _contract():
    """取得加權指數合約"""
    api = get_api()
    if api is None:
        return None, None
    return api, api.Contracts.Indexs.TSE.TSE001


# ── 即時報價 ──────────────────────────────────────────

def get_snapshot() -> dict | None:
    """
    即時加權指數報價。
    回傳 {"open", "high", "low", "close", "volume", "total_amount_yi"}
    或 None（API 不可用時）。
    """
    try:
        api, contract = _contract()
        if api is None:
            return None
        snaps = api.snapshots([contract])
        if not snaps:
            return None
        s = snaps[0]
        return {
            "open":             s.open,
            "high":             s.high,
            "low":              s.low,
            "close":            s.close,
            "volume":           s.volume,
            "total_amount_yi":  round(s.total_amount / 1e8, 0) if s.total_amount else None,
        }
    except Exception as e:
        print(f"[Shioaji] snapshot 失敗：{e}")
        reset_api()
        return None


# ── 台指期近月合約快照 ────────────────────────────────

def get_tx_snapshot(contract_code: str = "TX", month_setting=0) -> dict | None:
    """
    取得台指期合約即時報價。
    contract_code: "TX"（大台）/ "MTX"（小台）/ "XMTX"（微台）
    month_setting: 0=近月, 1=次月, 2=次次月, "YYYYMM"=指定月份
    回傳 {"price": float, "code": str} 或 None（API 不可用時）
    """
    _SJ = {"TX": "TXF", "MTX": "MXF", "XMTX": "TMF"}
    sj_code = _SJ.get(contract_code.upper())
    if not sj_code:
        return None
    try:
        api = get_api()
        if api is None:
            return None
        from engine.broker.sinopac import _get_contract_by_month
        contract = _get_contract_by_month(api, sj_code, month_setting)
        if contract is None:
            return None
        c_code = getattr(contract, "code", sj_code)
        c_name = getattr(contract, "name", "")
        c_cat  = getattr(contract, "category", "")
        print(f"[Shioaji] TX snapshot 合約：code={c_code} name={c_name} category={c_cat}")
        snaps = api.snapshots([contract])
        if not snaps:
            return None
        s = snaps[0]
        print(f"[Shioaji] TX snapshot 欄位：close={s.close} open={s.open} high={getattr(s,'high',None)} low={getattr(s,'low',None)} change_price={getattr(s,'change_price',None)}")
        raw = s.close or s.open or 0
        price = float(raw)
        # 台指期合理範圍：5000~100000，低於此視為欄位錯誤（如跳動點/漲跌）
        if price < 5000:
            print(f"[Shioaji] TX snapshot 異常價格 {price}（合約 {c_code}），忽略")
            return None
        return {"price": price, "code": c_code}
    except Exception as e:
        print(f"[Shioaji] TX snapshot 失敗（{contract_code} month={month_setting}）：{e}")
        return None


# ── 今日盤中 1 分K ────────────────────────────────────

def get_today_kbars1m() -> pd.DataFrame | None:
    """
    今日加權指數 1 分K 棒（盤中即時）。
    回傳 DataFrame，index=DatetimeIndex，columns=[Open,High,Low,Close,Volume,Amount]
    或 None（非交易日 / API 不可用 / 資料空白）。
    """
    try:
        api, contract = _contract()
        if api is None:
            return None

        today    = date.today().strftime("%Y-%m-%d")
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        kbars = api.kbars(contract, start=today, end=tomorrow)
        if not kbars or not kbars.ts:
            return None

        df = pd.DataFrame({**kbars})
        if df.empty:
            return None

        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df.dropna(subset=["Close"], inplace=True)

        return df if not df.empty else None

    except Exception as e:
        print(f"[Shioaji] 今日1分K 失敗：{e}")
        reset_api()
        return None


# ── 歷史日K（輔助）────────────────────────────────────

def get_daily_kbars(months: int = 7) -> pd.DataFrame | None:
    """
    抓加權指數歷史日K（由 1分K 聚合）。
    通常不需要直接呼叫；get_market_data() 用 snapshot 注入今日即可。
    回傳 DataFrame，columns=[Open,High,Low,Close,Volume,Amount_yi]，index=date。
    """
    try:
        api, contract = _contract()
        if api is None:
            return None

        end   = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = (date.today() - timedelta(days=months * 31)).strftime("%Y-%m-%d")

        kbars = api.kbars(contract, start=start, end=end)
        if not kbars or not kbars.ts:
            return None

        df = pd.DataFrame({**kbars})
        df["ts"] = pd.to_datetime(df["ts"])
        df.set_index("ts", inplace=True)
        df.dropna(subset=["Close"], inplace=True)

        # 聚合為日K
        day_df = pd.DataFrame({
            "Open":   df["Open"].resample("D").first(),
            "High":   df["High"].resample("D").max(),
            "Low":    df["Low"].resample("D").min(),
            "Close":  df["Close"].resample("D").last(),
            "Volume": df["Volume"].resample("D").sum(),
            "Amount": df["Amount"].resample("D").sum(),
        }).dropna(subset=["Close"])

        day_df["Amount_yi"] = (day_df["Amount"] / 1e8).round(0)
        return day_df

    except Exception as e:
        print(f"[Shioaji] 歷史日K 失敗：{e}")
        reset_api()
        return None
