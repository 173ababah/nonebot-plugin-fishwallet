"""账本存储（JSON，原子写）。

设计要点：

1. **惰性结算**：不做定时任务。每次读某人记录时顺手补「初始金额」和「今日补给」，
   用 `d`（最后结算日期）判断。机器人可能几小时没消息，定时器不可靠，惰性最稳。
2. **余额允许为负**：别的插件（抽卡/炒股）可能把人扣成负的，负余额要靠打工慢慢填，
   所以 `add` 不夹 0；只有 `spend` 才会拒绝。
3. **空记录自动清理**：一个人金币、消费、打工时间全是 0/空 → 从文件里删掉，别越滚越大。

记录字段（都在一个 dict 里，短键是为了文件小）：

| 键 | 含义 |
|----|------|
| `c` | 余额 |
| `d` | 上次每日补给日期 `YYYY-MM-DD` |
| `w` | 上次打工时间戳 |
| `sp` | 累计消费（金主档就看它） |
| `fv` | 上过几次舰（打工有额外加成） |
| `t` | 会员档：0 普通 / 2 提督 / 3 总督 |
| `tb` / `zb` | 提督/总督重复购买次数（每次加基础） |
| `qs` | 上次签到日期 |
| `init` | 是否已发过初始金额 |
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()

EMPTY = {"c": 0, "d": "", "w": 0.0, "sp": 0, "fv": 0, "t": 0, "tb": 0, "zb": 0, "qs": ""}


def today() -> str:
    return time.strftime("%Y-%m-%d")


class Store:
    """一个 JSON 文件 = 一个世界的账本。"""

    def __init__(self, path: str, *, start: int = 10, daily: int = 10):
        self.path = path
        self.start = int(start)
        self.daily = int(daily)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._stamp = 0.0
        self._load()

    # ---- 文件 ----
    def _load(self) -> None:
        try:
            st = os.stat(self.path)
            if st.st_mtime == self._stamp:
                return
            with open(self.path, "r", encoding="utf-8-sig") as f:
                raw = json.load(f)
            self._data = raw if isinstance(raw, dict) else {}
            self._stamp = st.st_mtime
        except FileNotFoundError:
            self._data, self._stamp = {}, 0.0
        except (OSError, ValueError):
            pass

    def _save(self) -> bool:
        for uid, rec in list(self._data.items()):
            if not isinstance(rec, dict):
                self._data.pop(uid, None)
                continue
            if not any(rec.get(k) for k in ("c", "sp", "w", "fv", "t", "tb", "zb", "qs")):
                self._data.pop(uid, None)
        try:
            d = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(d, exist_ok=True)
            tmp = self.path + ".tmp"
            with _lock:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, self.path)
            try:
                self._stamp = os.stat(self.path).st_mtime
            except OSError:
                pass
            return True
        except OSError:
            return False

    # ---- 读 ----
    def rec(self, uid: str) -> Dict[str, Any]:
        """取记录，**顺手结算**初始金额与今日补给。返回的 `got` 是本次补了多少。"""
        uid = str(uid or "")
        if not uid:
            return dict(EMPTY, got=0)
        self._load()
        rec = self._data.get(uid)
        if not isinstance(rec, dict):
            rec = {}
            self._data[uid] = rec
        got = 0
        if not rec.get("init"):
            rec["init"] = 1
            rec["c"] = int(rec.get("c") or 0) + self.start
            got += self.start
        if str(rec.get("d") or "") != today():
            rec["d"] = today()
            rec["c"] = int(rec.get("c") or 0) + self.daily
            got += self.daily
        for k, v in EMPTY.items():
            rec.setdefault(k, v)
        if got:
            self._save()
        out = {k: rec.get(k, EMPTY[k]) for k in EMPTY}
        out["c"] = int(rec.get("c") or 0)
        out["sp"] = int(rec.get("sp") or 0)
        out["fv"] = int(rec.get("fv") or 0)
        out["t"] = max(0, min(3, int(rec.get("t") or 0)))
        out["tb"] = max(0, int(rec.get("tb") or 0))
        out["zb"] = max(0, int(rec.get("zb") or 0))
        out["got"] = got
        return out

    def raw(self, uid: str) -> Dict[str, Any]:
        """直接拿可变字典（写操作用；调用方负责 `save()`）。"""
        self._load()
        rec = self._data.get(str(uid or ""))
        if not isinstance(rec, dict):
            rec = {"c": 0, "d": today(), "w": 0.0, "sp": 0, "fv": 0, "t": 0, "tb": 0, "zb": 0, "qs": ""}
            self._data[str(uid or "")] = rec
        return rec

    def all_users(self) -> Dict[str, Dict[str, Any]]:
        self._load()
        return {k: v for k, v in self._data.items() if isinstance(v, dict)}

    def save(self) -> bool:
        return self._save()

    # ---- 写 ----
    def add(self, uid: str, n: int) -> int:
        """加金额（**不夹 0**：负余额要靠加钱先填坑）。返回新余额。"""
        self.rec(uid)
        rec = self.raw(uid)
        rec["c"] = int(rec.get("c") or 0) + int(n)
        self._save()
        return rec["c"]

    def spend(self, uid: str, n: int) -> bool:
        """扣钱；不够就返回 False 且不动账本。"""
        n = int(n)
        if n <= 0:
            return False
        rec = self.rec(uid)
        if rec["c"] < n:
            return False
        r = self.raw(uid)
        r["c"] = int(r.get("c") or 0) - n
        r["sp"] = int(r.get("sp") or 0) + n
        self._save()
        return True

    def refund(self, uid: str, n: int) -> int:
        """退款（同时把累计消费扣回去，免得刷消费升金主）。返回新余额。"""
        n = max(0, int(n))
        rec = self.raw(uid)
        rec["c"] = int(rec.get("c") or 0) + n
        rec["sp"] = max(0, int(rec.get("sp") or 0) - n)
        self._save()
        return int(rec["c"])


def touch_work(store: Store, uid: str, ts: Optional[float] = None) -> None:
    r = store.raw(uid)
    r["w"] = float(ts if ts is not None else time.time())
    store.save()
