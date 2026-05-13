"""
券商 API 抽象基底類別
所有券商（模擬/康和/其他）都繼承此類別，實作相同介面
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class OrderResult:
    """下單結果"""
    success:    bool
    order_id:   str       = ""
    message:    str       = ""
    filled_price: Optional[float] = None
    filled_qty:   int     = 0
    timestamp:  str       = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class PositionInfo:
    """持倉資訊"""
    direction:   str    = "none"   # "Long" / "Short" / "none"
    quantity:    int    = 0
    entry_price: float  = 0.0
    contract:    str    = "MTX"
    unrealized_pnl: float = 0.0   # 未實現損益（元）
    unrealized_pts: float = 0.0   # 未實現損益（點）


class BrokerBase(ABC):
    """
    券商介面基底類別
    子類別必須實作：connect / buy / sell / close / get_position / cancel_all
    """

    def __init__(self, contract: str = "MTX", quantity: int = 1):
        self.contract = contract.upper()
        self.quantity = quantity
        self._connected = False

    # ── 必須實作 ──────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """連線到券商 API，回傳是否成功"""
        ...

    @abstractmethod
    def buy(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """做多開倉（或空頭回補）"""
        ...

    @abstractmethod
    def sell(self, price: float, qty: int = 1, order_type: str = "market") -> OrderResult:
        """做空開倉（或多頭平倉）"""
        ...

    @abstractmethod
    def close_position(self, price: float, order_type: str = "market") -> OrderResult:
        """平倉目前所有持倉"""
        ...

    @abstractmethod
    def get_position(self) -> PositionInfo:
        """查詢目前持倉"""
        ...

    @abstractmethod
    def cancel_all(self) -> bool:
        """取消所有未成交委託"""
        ...

    # ── 共用工具 ──────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_contract(self, contract: str):
        from .contract import get_contract
        get_contract(contract)          # 驗證合約代碼
        self.contract = contract.upper()

    def set_quantity(self, qty: int):
        if qty < 1:
            raise ValueError("口數必須 ≥ 1")
        self.quantity = qty
