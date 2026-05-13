"""
模擬下單券商
功能完整，邏輯與真實下單完全一致，只差最後一層不真實送出委託
用於測試策略邏輯是否正確，不怕手滑
"""

from .base import BrokerBase, OrderResult, PositionInfo
from .contract import get_contract, point_value
import uuid
from datetime import datetime


class SimulatorBroker(BrokerBase):
    """
    模擬券商 — 完整實作所有下單邏輯
    持倉狀態存在記憶體，重啟後清空（不影響 data/state.json）
    """

    def __init__(self, contract: str = "MTX", quantity: int = 1):
        super().__init__(contract, quantity)
        self._position = PositionInfo()
        self._orders: list[dict] = []
        self._trade_log: list[dict] = []

    def connect(self) -> bool:
        self._connected = True
        print("✅ [模擬] 券商連線成功")
        return True

    def buy(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """
        做多（新倉/加碼）或空頭回補。
        - 已持多單：加碼（數量累加，均價更新）
        - 已持空單：全部回補（平倉）
        - 空手：新開多單
        """
        oid  = str(uuid.uuid4())[:8]
        now  = datetime.now().strftime("%H:%M:%S")
        spec = get_contract(self.contract)
        pos  = self._position

        if pos.direction == "Short":
            # ── 空頭回補（平倉）──
            close_qty = min(qty, pos.quantity)
            pnl_pts   = pos.entry_price - price
            pnl_amt   = pnl_pts * spec["point_value"] * close_qty
            self._log_trade("平空（回補）", price, close_qty, pnl_pts, pnl_amt)
            remaining = pos.quantity - close_qty
            if remaining <= 0:
                self._position = PositionInfo()
            else:
                self._position = PositionInfo(
                    direction="Short", quantity=remaining,
                    entry_price=pos.entry_price, contract=self.contract
                )
            msg = f"[模擬] 空頭回補 {close_qty}口 @ {price:.0f}　損益 {pnl_pts:+.0f}點（{pnl_amt:+,.0f}元）"

        elif pos.direction == "Long":
            # ── 多頭加碼（均價計算）──
            total_qty  = pos.quantity + qty
            avg_price  = (pos.entry_price * pos.quantity + price * qty) / total_qty
            self._position = PositionInfo(
                direction="Long", quantity=total_qty,
                entry_price=avg_price, contract=self.contract
            )
            msg = f"[模擬] 多頭加碼 +{qty}口 @ {price:.0f}　累計 {total_qty}口 均價 {avg_price:.0f}"

        else:
            # ── 空手：多頭新倉 ──
            self._position = PositionInfo(
                direction="Long", quantity=qty,
                entry_price=price, contract=self.contract
            )
            msg = f"[模擬] 做多開倉 {qty}口 @ {price:.0f}"

        print(f"📈 {now} {msg}")
        return OrderResult(success=True, order_id=oid, message=msg,
                           filled_price=price, filled_qty=qty)

    def sell(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """
        做空（新倉/加碼）或多頭平倉。
        - 已持空單：加碼（數量累加，均價更新）
        - 已持多單：全部平倉
        - 空手：新開空單
        """
        oid  = str(uuid.uuid4())[:8]
        now  = datetime.now().strftime("%H:%M:%S")
        spec = get_contract(self.contract)
        pos  = self._position

        if pos.direction == "Long":
            # ── 多頭平倉 ──
            close_qty = min(qty, pos.quantity)
            pnl_pts   = price - pos.entry_price
            pnl_amt   = pnl_pts * spec["point_value"] * close_qty
            self._log_trade("平多", price, close_qty, pnl_pts, pnl_amt)
            remaining = pos.quantity - close_qty
            if remaining <= 0:
                self._position = PositionInfo()
            else:
                self._position = PositionInfo(
                    direction="Long", quantity=remaining,
                    entry_price=pos.entry_price, contract=self.contract
                )
            msg = f"[模擬] 多頭平倉 {close_qty}口 @ {price:.0f}　損益 {pnl_pts:+.0f}點（{pnl_amt:+,.0f}元）"

        elif pos.direction == "Short":
            # ── 空頭加碼（均價計算）──
            total_qty  = pos.quantity + qty
            avg_price  = (pos.entry_price * pos.quantity + price * qty) / total_qty
            self._position = PositionInfo(
                direction="Short", quantity=total_qty,
                entry_price=avg_price, contract=self.contract
            )
            msg = f"[模擬] 空頭加碼 +{qty}口 @ {price:.0f}　累計 {total_qty}口 均價 {avg_price:.0f}"

        else:
            # ── 空手：空頭新倉 ──
            self._position = PositionInfo(
                direction="Short", quantity=qty,
                entry_price=price, contract=self.contract
            )
            msg = f"[模擬] 做空開倉 {qty}口 @ {price:.0f}"

        print(f"📉 {now} {msg}")
        return OrderResult(success=True, order_id=oid, message=msg,
                           filled_price=price, filled_qty=qty)

    def close_position(self, price: float, order_type: str = "market") -> OrderResult:
        """平倉所有持倉"""
        pos = self._position
        if pos.direction == "none" or pos.quantity == 0:
            return OrderResult(success=False, message="[模擬] 目前空手，無倉位可平")
        if pos.direction == "Long":
            return self.sell(price, pos.quantity, order_type)
        else:
            return self.buy(price, pos.quantity, order_type)

    def get_position(self) -> PositionInfo:
        pos = self._position
        if pos.direction != "none" and pos.entry_price > 0:
            # 這裡沒有即時報價，unrealized_pnl 先留 0
            pass
        return pos

    def cancel_all(self) -> bool:
        print("[模擬] 取消所有委託（模擬無委託佇列）")
        return True

    def get_trade_log(self) -> list[dict]:
        return self._trade_log

    def _log_trade(self, action: str, price: float, qty: int, pnl_pts: float, pnl_amt: float):
        self._trade_log.append({
            "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action":  action,
            "price":   price,
            "qty":     qty,
            "pnl_pts": pnl_pts,
            "pnl_amt": pnl_amt,
            "contract": self.contract,
        })
