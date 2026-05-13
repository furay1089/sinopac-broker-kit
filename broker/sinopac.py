"""
永豐金證券 Shioaji 期貨下單層

功能：
  - 台指期大台 TX  / 小台 MTX / 微台 XMTX
  - 市價單（ROD + MKT）自動新倉/平倉（OCType.Auto）
  - 倉位查詢、全撤委託
  - simulation=True 時使用永豐模擬帳戶（不影響真倉）

設計：
  - 重用 broker_sinopac.get_api()（Singleton，已登入）
  - 不重複登入；斷線時呼叫 reset_api() 重連
"""

from .base import BrokerBase, OrderResult, PositionInfo
from .contract import get_contract
from datetime import datetime
import uuid

# 永豐合約代碼對應（Shioaji 用不同代碼）
_SJ_CODE = {
    "TX":   "TXF",    # 大台指
    "MTX":  "MXF",    # 小台指
    "XMTX": "TMF",    # 微台指（微型臺指期貨，確認代碼）
}

# 微台指備用代碼（TMF 為正確代碼，舊版備用）
# IMF = 亞光期貨（股票期貨），絕對不可放入此清單
_XMTX_FALLBACK_CODES = ["TMF", "IMXF", "XMTXF"]


import re as _re

def _is_weekly_contract(code: str) -> bool:
    """
    週合約識別：代碼結尾為 R + 數字，例如 TXFR1, MXFR1, TXFR2。
    月合約結尾為 月份字母 + 年份數字，例如 TXFE6, MXFF6。
    """
    return bool(_re.search(r'R\d+$', code.upper()))


def _get_all_contracts(api, sj_code: str) -> list:
    """
    取得某商品所有「月合約」，依 delivery_month 排序（最近月在前）。
    自動過濾掉週合約（代碼含 R+數字 結尾，如 TXFR1/MXFR1）。

    查法：
      1. 直接 getattr / subscript 存取 sj_code
      2. 若 sj_code 是 IMXF（微台）則自動嘗試備用代碼清單
      3. 全掃描所有 group，比對 code 前綴或關鍵字
    """
    found = []

    def _collect(group):
        try:
            for c in group:
                code = getattr(c, "code", "") or ""
                if _is_weekly_contract(code):
                    continue   # 過濾週合約（TXFR1, MXFR1 等）
                dm = getattr(c, "delivery_month", None) or getattr(c, "delivery_date", None)
                if dm is not None:
                    found.append((str(dm), c))
        except TypeError:
            pass

    def _try_code(code):
        """嘗試用單一代碼取 group 並 collect"""
        g = getattr(api.Contracts.Futures, code, None)
        if g is not None:
            _collect(g)
        if not found:
            try:
                _collect(api.Contracts.Futures[code])
            except Exception:
                pass

    # 方法 1：嘗試主代碼
    _try_code(sj_code)

    # 方法 2：微台備用代碼（TMF 找不到時）
    if not found and sj_code in ("TMF", "IMXF"):
        for alt in _XMTX_FALLBACK_CODES:
            if alt == sj_code:
                continue
            _try_code(alt)
            if found:
                print(f"[Shioaji] 微台指改用代碼：{alt}")
                break

    # 方法 3：全掃描，比對 code 欄位前綴
    if not found:
        prefixes = [sj_code]
        if sj_code in ("TMF", "IMXF"):
            prefixes += _XMTX_FALLBACK_CODES
        try:
            for attr in dir(api.Contracts.Futures):
                if attr.startswith("_"):
                    continue
                grp = getattr(api.Contracts.Futures, attr, None)
                if grp is None:
                    continue
                try:
                    for c in grp:
                        code = getattr(c, "code", "") or ""
                        if _is_weekly_contract(code):
                            continue   # 過濾週合約
                        dm = (getattr(c, "delivery_month", None)
                              or getattr(c, "delivery_date", None))
                        if dm is not None and any(code.startswith(p) for p in prefixes):
                            found.append((str(dm), c))
                except TypeError:
                    pass
        except Exception:
            pass

    found.sort(key=lambda x: x[0])
    return [c for _, c in found]


def _get_contract_by_month(api, sj_code: str, month_setting=0):
    """
    依 month_setting 取合約：
      0        → 近月（最近到期）
      1        → 次月
      2        → 次次月
      "YYYYMM" → 指定月份字串，如 "202506"
    """
    try:
        contracts = _get_all_contracts(api, sj_code)
        if not contracts:
            return None

        if isinstance(month_setting, int):
            idx = max(0, month_setting)
            return contracts[idx] if idx < len(contracts) else contracts[-1]

        # 指定月份字串
        target = str(month_setting).strip()
        for c in contracts:
            dm = str(getattr(c, "delivery_month", "") or getattr(c, "delivery_date", "") or "")
            if dm.startswith(target):
                return c
        # 找不到指定月份 → fallback 近月
        print(f"[Shioaji] 找不到指定月份 {target}，改用近月")
        return contracts[0]

    except Exception as e:
        print(f"[Shioaji] 取合約失敗（{sj_code} month={month_setting}）：{e}")
        return None


# 保留舊名稱相容性
def _get_near_contract(api, sj_code: str):
    return _get_contract_by_month(api, sj_code, 0)


def list_futures_groups(api) -> str:
    """
    列出 api.Contracts.Futures 下所有 group 名稱及近月合約代碼。
    優先顯示台指期相關（TX/MTX/XMTX/IMX），其餘只列名稱。
    """
    _TX_KEYWORDS = ("TX", "MTX", "MX", "IMX", "XMTX", "TXF", "MXF", "IMXF")

    tx_lines    = ["📋 台指期相關 Group："]
    other_names = []

    try:
        for attr in sorted(dir(api.Contracts.Futures)):
            if attr.startswith("_"):
                continue
            grp = getattr(api.Contracts.Futures, attr, None)
            if grp is None:
                continue
            try:
                contracts = list(grp)
                if not contracts:
                    continue
                sample = contracts[0]
                code = getattr(sample, "code", "?")
                dm   = (getattr(sample, "delivery_month", "")
                        or getattr(sample, "delivery_date", ""))
                is_tx = any(attr.upper().startswith(k) or code.upper().startswith(k)
                            for k in _TX_KEYWORDS)
                if is_tx:
                    tx_lines.append(f"  {attr} → {code}（{dm}）共{len(contracts)}筆")
                else:
                    other_names.append(attr)
            except TypeError:
                pass
    except Exception as e:
        tx_lines.append(f"  ❌ 查詢失敗：{e}")

    result = "\n".join(tx_lines)
    if other_names:
        # 只列名稱，每行最多10個，不超字數
        chunks = [", ".join(other_names[i:i+10]) for i in range(0, len(other_names), 10)]
        result += "\n\n其他 Group（僅列名）：\n" + "\n".join(chunks[:5])  # 最多5行
    return result


class SinopacBroker(BrokerBase):
    """
    永豐 Shioaji 期貨真實/模擬下單
    simulation=True → 使用永豐模擬帳戶
    simulation=False → 真實下單（請確認帳戶資金）
    """

    def __init__(self, contract: str = "MTX", quantity: int = 1,
                 simulation: bool = True):
        super().__init__(contract, quantity)
        self.simulation = simulation
        self._api = None
        self._last_trades: list = []
        self._notify_fn = None   # 成交回報推播函式（由 order_manager 注入）

    def set_notify_fn(self, fn):
        """注入 TG 推播函式，connect() 之後呼叫才能生效"""
        self._notify_fn = fn
        if self._api and self._notify_fn:
            self._api.set_order_callback(self._make_fill_callback())

    def _make_fill_callback(self):
        """建立 Shioaji 成交回報 callback（在背景執行緒執行）"""
        notify_fn   = self._notify_fn
        simulation  = self.simulation
        mode_s      = "模擬" if simulation else "真實"

        def on_order_event(stat, msg):
            try:
                # msg 可能是 dict 或物件，統一用 .get / getattr 取值
                if isinstance(msg, dict):
                    status_d  = msg.get("status", {})
                    order_d   = msg.get("order",  {})
                    contract_d = msg.get("contract", {})
                    status    = status_d.get("status", "")
                    fill_price = status_d.get("price", 0)
                    deal_qty  = status_d.get("deal_quantity", 0)
                    action    = order_d.get("action", "")
                    code      = (contract_d.get("code", "") if isinstance(contract_d, dict)
                                 else getattr(contract_d, "code", ""))
                else:
                    status_obj = getattr(msg, "status", None)
                    status     = getattr(status_obj, "status", "")
                    fill_price = getattr(status_obj, "price", 0)
                    deal_qty   = getattr(status_obj, "deal_quantity", 0)
                    action     = getattr(getattr(msg, "order", None), "action", "")
                    code       = getattr(getattr(msg, "contract", None), "code", "")

                if str(status).lower() not in ("filled", "partfilled"):
                    return

                dir_s = "做多" if "Buy" in str(action) else "做空/平倉"
                label = "✅ 成交確認" if str(status).lower() == "filled" else "⚡ 部分成交"
                ts    = datetime.now().strftime("%H:%M:%S")

                text = (
                    f"{label}【{mode_s}】{dir_s}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"合約：{code}　口數：{deal_qty}口\n"
                    f"成交價：{fill_price}\n"
                    f"時間：{ts}"
                )
                if notify_fn:
                    notify_fn(text)

                # ── 設定對帳旗標（執行緒安全：只寫一個 key）───────────────
                # callback 在背景執行緒，不直接呼叫 API；
                # 下次 execute_action 或 bot 重啟時，_reconcile_position 會清除此旗標。
                try:
                    from engine.state_engine import load_state, save_state
                    _s = load_state()
                    _s["needs_reconcile"] = True
                    save_state(_s)
                except Exception:
                    pass   # 旗標設定失敗不中斷成交通知

            except Exception as e:
                print(f"[Shioaji fill callback 例外] {e}")

        return on_order_event

    # ══════════════════════════════════════════════════
    # 連線（重用 broker_sinopac Singleton）
    # ══════════════════════════════════════════════════

    def connect(self) -> bool:
        try:
            from engine.broker_sinopac import get_api, _load_cfg
            self._api = get_api()
            if self._api is None:
                print("❌ [Shioaji] 無法取得 API，請確認 sinopac_config.json")
                return False

            # ── CA 憑證啟用（下單必要，查帳不需要）────────────
            cfg = _load_cfg()
            ca_path   = cfg.get("ca_path", "")
            ca_passwd  = cfg.get("ca_passwd", "")
            person_id  = cfg.get("person_id", "")
            if ca_path and ca_passwd and person_id:
                try:
                    self._api.activate_ca(
                        ca_path   = ca_path,
                        ca_passwd = ca_passwd,
                        person_id = person_id,
                    )
                    print(f"\n✅ [Shioaji] CA 憑證啟用成功（{person_id}）")
                except Exception as e:
                    print(f"⚠️  [Shioaji] CA 啟用失敗（{e}）→ 只能查帳，無法下單")
            else:
                print("⚠️  [Shioaji] 未設定 CA 憑證（sinopac_config.json 填 ca_path/ca_passwd）→ 無法下單")

            self._connected = True
            # 成交回報 callback（若 notify_fn 已設定則一起掛）
            if self._notify_fn:
                self._api.set_order_callback(self._make_fill_callback())
            mode_s = "模擬" if self.simulation else "真實"
            print(f"✅ [Shioaji] 期貨下單連線成功（{mode_s}）")
            return True
        except Exception as e:
            print(f"❌ [Shioaji] 連線失敗：{e}")
            return False

    # ══════════════════════════════════════════════════
    # 取合約 / 帳戶
    # ══════════════════════════════════════════════════

    def _get_contract(self):
        """依 trade_config.contract_month 取得對應月份合約"""
        sj_code = _SJ_CODE.get(self.contract.upper())
        if not sj_code:
            raise ValueError(f"不支援的合約：{self.contract}")

        # 讀取月份設定（預設 0 = 近月）
        try:
            from engine.broker.order_manager import load_config as _lcfg
            month_setting = _lcfg().get("contract_month", 0)
        except Exception:
            month_setting = 0

        c = _get_contract_by_month(self._api, sj_code, month_setting)
        if c is None:
            # 針對微台給出明確提示
            if self.contract.upper() == "XMTX":
                raise RuntimeError(
                    "微台 XMTX 在此帳戶不支援（Shioaji 無 TMF 合約）\n"
                    "請改用小台：/setcontract MTX 或 ⚙️設定 → 小台 MTX"
                )
            raise RuntimeError(
                f"找不到合約：{sj_code}（月份設定：{month_setting}）\n"
                f"請用 /listcontracts 確認此帳戶支援的合約代碼"
            )

        month_label = {0: "近月", 1: "次月", 2: "次次月"}.get(
            month_setting, f"指定月份{month_setting}"
        )
        print(f"[Shioaji] 使用合約：{getattr(c, 'code', sj_code)}（{month_label}）")
        return c

    def _get_account(self):
        """取得期貨帳戶"""
        try:
            return self._api.futopt_account
        except Exception:
            raise RuntimeError("無法取得期貨帳戶，請確認永豐帳戶已開立期貨權限")

    # ══════════════════════════════════════════════════
    # 下單（市價 ROD + Auto 新倉/平倉）
    # ══════════════════════════════════════════════════

    def buy(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """做多開倉 或 空頭回補。order_type='limit' 時以 price 為限價，否則為市價。"""
        self._check_connected()
        try:
            import shioaji as sj
            contract  = self._get_contract()
            account   = self._get_account()
            is_limit  = (order_type == "limit" and price > 0)

            order = self._api.Order(
                action     = sj.constant.Action.Buy,
                price      = int(price) if is_limit else 0,
                quantity   = qty,
                price_type = (sj.constant.FuturesPriceType.LMT if is_limit
                              else sj.constant.FuturesPriceType.MKT),
                order_type = sj.constant.OrderType.ROD,
                octype     = sj.constant.FuturesOCType.Auto,
                account    = account,
            )
            trade = self._api.place_order(contract, order)
            self._last_trades.append(trade)

            oid    = getattr(trade.order, "id", str(uuid.uuid4())[:8])
            filled = price if is_limit else (getattr(trade.order, "price", None) or price)
            type_s = f"限價 {int(price)}" if is_limit else "市價"
            msg = (f"[永豐{'模擬' if self.simulation else '真實'}] "
                   f"買進（Buy）{qty}口 @ {type_s}　委託 #{oid}")
            print(f"📈 {datetime.now().strftime('%H:%M:%S')} {msg}")
            return OrderResult(success=True, order_id=str(oid),
                               message=msg, filled_price=filled, filled_qty=qty)

        except Exception as e:
            msg = f"Buy 失敗：{e}"
            print(f"❌ {msg}")
            return OrderResult(success=False, message=msg)

    def sell(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """做空開倉 或 多頭平倉。order_type='limit' 時以 price 為限價，否則為市價。"""
        self._check_connected()
        try:
            import shioaji as sj
            contract  = self._get_contract()
            account   = self._get_account()
            is_limit  = (order_type == "limit" and price > 0)

            order = self._api.Order(
                action     = sj.constant.Action.Sell,
                price      = int(price) if is_limit else 0,
                quantity   = qty,
                price_type = (sj.constant.FuturesPriceType.LMT if is_limit
                              else sj.constant.FuturesPriceType.MKT),
                order_type = sj.constant.OrderType.ROD,
                octype     = sj.constant.FuturesOCType.Auto,
                account    = account,
            )
            trade = self._api.place_order(contract, order)
            self._last_trades.append(trade)

            oid    = getattr(trade.order, "id", str(uuid.uuid4())[:8])
            filled = price if is_limit else (getattr(trade.order, "price", None) or price)
            type_s = f"限價 {int(price)}" if is_limit else "市價"
            msg = (f"[永豐{'模擬' if self.simulation else '真實'}] "
                   f"賣出（Sell）{qty}口 @ {type_s}　委託 #{oid}")
            print(f"📉 {datetime.now().strftime('%H:%M:%S')} {msg}")
            return OrderResult(success=True, order_id=str(oid),
                               message=msg, filled_price=filled, filled_qty=qty)

        except Exception as e:
            msg = f"Sell 失敗：{e}"
            print(f"❌ {msg}")
            return OrderResult(success=False, message=msg)

    def close_position(self, price: float, order_type: str = "market") -> OrderResult:
        """查倉位方向後送出反向平倉單（針對 self.contract）"""
        self._check_connected()
        pos = self.get_position()
        if pos.direction == "none" or pos.quantity == 0:
            return OrderResult(success=False, message="目前空手，無倉位可平")
        if pos.direction == "Long":
            return self.sell(price, pos.quantity, order_type)
        else:
            return self.buy(price, pos.quantity, order_type)

    def close_contract_position(self, target_contract: str, price: float) -> OrderResult:
        """
        平倉指定合約（不更改 self.contract 設定）。
        target_contract: "TX" / "MTX" / "XMTX"
        """
        self._check_connected()
        sj_code = _SJ_CODE.get(target_contract.upper())
        if not sj_code:
            return OrderResult(success=False, message=f"不支援的合約：{target_contract}")
        try:
            import shioaji as sj
            self._api.update_status()
            account   = self._get_account()
            positions = self._api.list_positions(account, unit=sj.constant.Unit.Common)

            # 找出屬於 target_contract 的倉位
            target_pos = None
            for pos in positions:
                code = getattr(pos, "code", "")
                if code.startswith(sj_code[:2]):
                    target_pos = pos
                    break

            if target_pos is None:
                return OrderResult(success=False, message=f"{target_contract} 無持倉可平")

            qty = target_pos.quantity
            direction = target_pos.direction  # "Buy" / "Sell"

            # 取該合約的近月合約物件
            c = _get_contract_by_month(self._api, sj_code, 0)
            if c is None:
                return OrderResult(success=False, message=f"找不到 {target_contract} 合約物件")

            # 反向平倉
            close_action = sj.constant.Action.Sell if direction == "Buy" else sj.constant.Action.Buy
            order = self._api.Order(
                action     = close_action,
                price      = 0,
                quantity   = qty,
                price_type = sj.constant.FuturesPriceType.MKT,
                order_type = sj.constant.OrderType.ROD,
                octype     = sj.constant.FuturesOCType.Auto,
                account    = account,
            )
            trade = self._api.place_order(c, order)
            self._last_trades.append(trade)
            oid = getattr(trade.order, "id", "?")
            dir_s = "多單" if direction == "Buy" else "空單"
            msg = (f"[永豐{'模擬' if self.simulation else '真實'}] "
                   f"平{dir_s} {target_contract} {qty}口 @ 市價　#{oid}")
            print(f"🚪 {msg}")
            return OrderResult(success=True, order_id=str(oid),
                               message=msg, filled_qty=qty)
        except Exception as e:
            return OrderResult(success=False, message=f"平倉失敗：{e}")

    # ══════════════════════════════════════════════════
    # 查詢持倉
    # ══════════════════════════════════════════════════

    def get_position(self) -> PositionInfo:
        """查詢永豐期貨倉位（僅目前設定合約）"""
        self._check_connected()
        try:
            import shioaji as sj
            self._api.update_status()
            account   = self._get_account()
            positions = self._api.list_positions(account,
                            unit=sj.constant.Unit.Common)
            sj_code   = _SJ_CODE.get(self.contract.upper(), "")

            for pos in positions:
                code = getattr(pos, "code", "")
                if not code.startswith(sj_code[:2]):   # TXF / MXF / IMXF 前綴
                    continue
                direction = pos.direction               # "Buy" / "Sell"
                qty       = pos.quantity
                avg_price = pos.price

                dir_s = "Long" if direction == "Buy" else "Short"
                return PositionInfo(
                    direction   = dir_s,
                    quantity    = qty,
                    entry_price = avg_price,
                    contract    = self.contract,
                )

            return PositionInfo()   # 空手

        except Exception as e:
            print(f"❌ [Shioaji] 查詢倉位失敗：{e}")
            return PositionInfo()

    def get_all_positions(self) -> list[PositionInfo]:
        """
        查詢帳戶所有期貨庫存（大台/小台/微台全部）
        回傳 list[PositionInfo]，空手時回傳 []
        """
        self._check_connected()
        # SJ code 前綴 → 內部名稱對照
        _PREFIX_TO_CONTRACT = {
            "TXF":  "TX",
            "MXF":  "MTX",
            "TMF":  "XMTX",   # 微型臺指期貨（正確代碼）
            "IMXF": "XMTX",   # 舊版備用
        }
        result = []
        try:
            import shioaji as sj
            self._api.update_status()
            account   = self._get_account()
            positions = self._api.list_positions(account,
                            unit=sj.constant.Unit.Common)
            for pos in positions:
                code = getattr(pos, "code", "")
                matched_contract = None
                for prefix, cname in _PREFIX_TO_CONTRACT.items():
                    if code.startswith(prefix[:2]):      # TXF→TX, MXF→MX, IMXF→IM
                        matched_contract = cname
                        break
                if matched_contract is None:
                    continue                             # 非台指期，略過
                dir_s = "Long" if pos.direction == "Buy" else "Short"
                result.append(PositionInfo(
                    direction   = dir_s,
                    quantity    = pos.quantity,
                    entry_price = pos.price,
                    contract    = matched_contract,
                ))
        except Exception as e:
            print(f"❌ [Shioaji] 查詢全部倉位失敗：{e}")
        return result

    # ══════════════════════════════════════════════════
    # 委託查詢 / 撤單 / 改單
    # ══════════════════════════════════════════════════

    def get_account_balance(self) -> dict:
        """查詢期貨帳戶保證金 / 權益數 / 可用餘額"""
        self._check_connected()
        try:
            account = self._get_account()
            result  = {}
            # 方法 1：api.margin()
            try:
                m = self._api.margin(account)
                result = {
                    "equity":    float(getattr(m, "equity",            0) or 0),
                    "margin":    float(getattr(m, "margin_requirement", 0) or 0),
                    "available": float(getattr(m, "available_margin",   0) or 0),
                    "unrealized":float(getattr(m, "unrealized_pnl",     0) or 0),
                }
                if any(v != 0 for v in result.values()):
                    return result
            except Exception:
                pass
            # 方法 2：api.account_balance()
            try:
                b = self._api.account_balance()
                result = {
                    "equity":    float(getattr(b, "acc_equity",        0) or 0),
                    "available": float(getattr(b, "available_balance",  0) or 0),
                }
            except Exception:
                pass
            return result
        except Exception as e:
            print(f"[get_account_balance] {e}")
            return {}

    def get_fill_history(self) -> list[dict]:
        """查詢本次連線已成交委託"""
        filled = []
        if not self._last_trades:
            return []
        try:
            self._api.update_status()
            for trade in self._last_trades:
                status_obj = getattr(trade, "status", None)
                status_str = str(getattr(status_obj, "status", "")).lower()
                if "fill" not in status_str:
                    continue
                order_obj    = getattr(trade, "order", None)
                contract_obj = getattr(trade, "contract", None)
                filled.append({
                    "order_id":  str(getattr(order_obj,   "id",            "?")),
                    "action":    str(getattr(order_obj,   "action",        "?")),
                    "price":     float(getattr(status_obj,"price",         0) or 0),
                    "quantity":  int(getattr(status_obj,  "deal_quantity", 0) or 0),
                    "code":      str(getattr(contract_obj,"code",          "?")),
                    "status":    status_str,
                })
        except Exception as e:
            print(f"[get_fill_history] {e}")
        return filled

    def close_partial(self, target_contract: str, qty: int, price: float) -> OrderResult:
        """部分平倉：指定合約 + 指定口數（不超過實際持倉）"""
        self._check_connected()
        sj_code = _SJ_CODE.get(target_contract.upper())
        if not sj_code:
            return OrderResult(success=False, message=f"不支援的合約：{target_contract}")
        try:
            import shioaji as sj
            self._api.update_status()
            account   = self._get_account()
            positions = self._api.list_positions(account, unit=sj.constant.Unit.Common)

            target_pos = None
            for pos in positions:
                if getattr(pos, "code", "").startswith(sj_code[:2]):
                    target_pos = pos
                    break

            if target_pos is None:
                return OrderResult(success=False, message=f"{target_contract} 無持倉可平")

            pos_qty   = int(getattr(target_pos, "quantity", 0))
            close_qty = min(qty, pos_qty)
            if close_qty <= 0:
                return OrderResult(success=False, message=f"平倉口數無效（{qty}）")

            direction    = target_pos.direction
            c            = _get_contract_by_month(self._api, sj_code, 0)
            if c is None:
                return OrderResult(success=False, message=f"找不到合約物件：{target_contract}")

            close_action = sj.constant.Action.Sell if direction == "Buy" else sj.constant.Action.Buy
            order = self._api.Order(
                action     = close_action,
                price      = 0,
                quantity   = close_qty,
                price_type = sj.constant.FuturesPriceType.MKT,
                order_type = sj.constant.OrderType.ROD,
                octype     = sj.constant.FuturesOCType.Auto,
                account    = account,
            )
            trade = self._api.place_order(c, order)
            self._last_trades.append(trade)
            oid   = getattr(trade.order, "id", "?")
            dir_s = "多單" if direction == "Buy" else "空單"
            msg   = (f"[永豐{'模擬' if self.simulation else '真實'}] "
                     f"部分平{dir_s} {target_contract} {close_qty}口 @ 市價　#{oid}")
            print(f"🚪 {msg}")
            return OrderResult(success=True, order_id=str(oid),
                               message=msg, filled_qty=close_qty)
        except Exception as e:
            return OrderResult(success=False, message=f"部分平倉失敗：{e}")

    def _get_all_trades(self) -> list:
        """
        合併取得所有委託清單：
          1. api.list_trades()  → API 原生查詢（不受 bot 重啟影響）
          2. self._last_trades  → 本 session in-memory 補充（保留相容）
        去重以 order_id 為鍵，API 版本優先。
        """
        trades_by_id: dict[str, object] = {}
        # ── 優先：API 原生查詢（包含 bot 重啟前的委託）──────────
        try:
            api_trades = self._api.list_trades()
            for t in (api_trades or []):
                oid = str(getattr(getattr(t, "order", None), "id", ""))
                if oid:
                    trades_by_id[oid] = t
        except Exception as e:
            print(f"[_get_all_trades] api.list_trades() 失敗（{e}），退回 _last_trades")
        # ── 補充：本 session 送出的（若 api 查不到也能找到）───────
        for t in self._last_trades:
            oid = str(getattr(getattr(t, "order", None), "id", ""))
            if oid and oid not in trades_by_id:
                trades_by_id[oid] = t
        return list(trades_by_id.values())

    def get_pending_orders(self) -> list[dict]:
        """
        查詢所有未完全成交的委託。
        改用 api.list_trades() 查詢，不受 bot 重啟影響。
        """
        pending = []
        try:
            self._api.update_status()
            for trade in self._get_all_trades():
                status_obj = getattr(trade, "status", None)
                status_str = str(getattr(status_obj, "status", "")).lower()
                # Shioaji 可能回傳 "status.cancelled" / "cancelled" 兩種格式
                _DONE = ("filled", "cancelled", "failed", "exceptfilled", "partfilled")
                if any(s in status_str for s in _DONE):
                    continue
                order_obj    = getattr(trade, "order", None)
                contract_obj = getattr(trade, "contract", None)
                pending.append({
                    "order_id":   str(getattr(order_obj,   "id",            "?")),
                    "action":     str(getattr(order_obj,   "action",        "?")),
                    "price_type": str(getattr(order_obj,   "price_type",    "?")),
                    "price":      float(getattr(order_obj,  "price",         0) or 0),
                    "quantity":   int(getattr(order_obj,   "quantity",      0) or 0),
                    "deal_qty":   int(getattr(status_obj,  "deal_quantity", 0) or 0),
                    "code":       str(getattr(contract_obj, "code",          "?")),
                    "status":     status_str,
                })
        except Exception as e:
            print(f"[get_pending_orders] {e}")
        return pending

    def cancel_order_by_id(self, order_id: str) -> tuple[bool, str]:
        """取消指定委託單，回傳 (success, message)。使用 api.list_trades() 查詢，不受重啟影響。"""
        try:
            self._api.update_status()
            for trade in self._get_all_trades():
                oid = str(getattr(getattr(trade, "order", None), "id", ""))
                if oid != order_id:
                    continue
                status_str = str(getattr(getattr(trade, "status", None), "status", "")).lower()
                if status_str in ("filled", "cancelled"):
                    return False, f"委託 #{order_id[:8]} 已{status_str}，無法取消"
                # 市價單無法撤銷（交易所立即處理，不在等待佇列）
                price_type = str(getattr(getattr(trade, "order", None), "price_type", "")).upper()
                if price_type in ("MKT", "MARKET", "市價"):
                    return False, f"⚠️ 委託 #{order_id[:8]} 為市價單，無法撤銷\n市價單送出後立即送交易所，只能等待成交或失敗。"
                self._api.cancel_order(trade)
                return True, f"✅ 取消委託 #{order_id[:8]} 送出（請稍後確認狀態）"
            return False, f"❌ 找不到委託 #{order_id[:8]}（確認是否已成交或已撤）"
        except Exception as e:
            return False, f"❌ 取消失敗：{e}"

    def modify_order_price(self, order_id: str, new_price: float) -> tuple[bool, str]:
        """
        改價：使用 api.update_order(trade, price=new_price) 直接修改。
        不做撤單重送，避免產生兩張委託。
        """
        try:
            self._api.update_status()
            for trade in self._get_all_trades():
                oid = str(getattr(getattr(trade, "order", None), "id", ""))
                if oid != order_id:
                    continue
                status_str = str(getattr(getattr(trade, "status", None), "status", "")).lower()
                if status_str in ("filled", "cancelled"):
                    return False, f"委託 #{order_id[:8]} 已{status_str}，無法改價"
                # ── 直接改價（不撤單重送）────────────────────────
                self._api.update_order(trade, price=int(new_price))
                return True, f"✅ 改價完成：限價 {int(new_price)}　委託 #{oid[:8]}"
            return False, f"❌ 找不到委託 #{order_id[:8]}"
        except Exception as e:
            return False, f"❌ 改價失敗：{e}"

    def modify_order_qty(self, order_id: str, new_qty: int) -> tuple[bool, str]:
        """
        改口數：使用 api.update_order(trade, qty=new_qty) 直接修改。
        Shioaji 只允許減量（new_qty < 原始委託量）；不支援加量。
        """
        try:
            self._api.update_status()
            for trade in self._get_all_trades():
                oid = str(getattr(getattr(trade, "order", None), "id", ""))
                if oid != order_id:
                    continue
                status_str = str(getattr(getattr(trade, "status", None), "status", "")).lower()
                if status_str in ("filled", "cancelled"):
                    return False, f"委託 #{order_id[:8]} 已{status_str}，無法改量"
                orig_qty = int(getattr(getattr(trade, "order", None), "quantity", 0) or 0)
                if new_qty <= 0:
                    return False, f"❌ 口數必須 ≥ 1（輸入：{new_qty}）"
                if new_qty > orig_qty:
                    return False, f"❌ 只能減量，不能加量（原始：{orig_qty}口，輸入：{new_qty}口）"
                self._api.update_order(trade, qty=new_qty)
                return True, f"✅ 改量完成：{orig_qty}口 → {new_qty}口　委託 #{oid[:8]}"
            return False, f"❌ 找不到委託 #{order_id[:8]}"
        except Exception as e:
            return False, f"❌ 改量失敗：{e}"

    def cancel_all(self) -> bool:
        """撤銷所有未成交委託"""
        self._check_connected()
        try:
            for trade in self._last_trades:
                status = getattr(trade.status, "status", "")
                if status not in ("Filled", "Cancelled", "Failed"):
                    self._api.cancel_order(trade)
            self._last_trades.clear()
            print("[Shioaji] 全部撤單完成")
            return True
        except Exception as e:
            print(f"❌ [Shioaji] 撤單失敗：{e}")
            return False

    # ══════════════════════════════════════════════════
    # 內部
    # ══════════════════════════════════════════════════

    def _check_connected(self):
        """確保連線有效；若 Singleton 已被重置（斷線後重連），自動刷新 self._api"""
        from engine.broker_sinopac import get_api as _get_api
        fresh = _get_api()
        if fresh is not None:
            self._api       = fresh   # 更新可能已過時的 Singleton 引用
            self._connected = True
        elif not self._connected or self._api is None:
            raise RuntimeError("Shioaji 連線失敗，請確認網路與 API 金鑰")
