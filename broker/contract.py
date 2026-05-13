"""
合約規格定義
大台 TX / 小台 MTX / 微台 XMTX
"""

CONTRACTS = {
    "TX": {
        "name":        "大台（台指期）",
        "code":        "TX",
        "point_value": 200,       # 每點 200 元
        "tick_size":   1,         # 最小跳動 1 點
        "margin":      184000,    # 保證金（約）
    },
    "MTX": {
        "name":        "小台（小型台指期）",
        "code":        "MTX",
        "point_value": 50,        # 每點 50 元
        "tick_size":   1,
        "margin":      46000,
    },
    "XMTX": {
        "name":        "微台（微型台指期）",
        "code":        "XMTX",
        "point_value": 10,        # 每點 10 元
        "tick_size":   1,
        "margin":      9200,
    },
}


def get_contract(code: str) -> dict:
    code = code.upper()
    if code not in CONTRACTS:
        raise ValueError(f"不支援的合約代碼：{code}，可用：TX / MTX / XMTX")
    return CONTRACTS[code]


def point_value(code: str) -> int:
    return get_contract(code)["point_value"]


def contract_name(code: str) -> str:
    return get_contract(code)["name"]
