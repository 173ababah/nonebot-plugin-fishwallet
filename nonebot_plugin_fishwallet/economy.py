"""规则层（纯函数 + 可注入随机源，方便单测）。

三条规则是线上定下来的，别随手改：

1. **打工按会员档分档**：普通 1~100（上过舰再加 10~50 + 10×(次数-1)）、
   提督 100~300 × 1.1~3.0、总督 300~500 × 2.0~5.0。
   重复买提督每次基础 +50；重复买总督每次基础 +200、倍率再 +0.3。
2. **金主档只看累计消费**（爆米 + 上舰 + 转账都算 `sp`），跟余额无关。
3. **转账**要校验：不能给自己、金额上下限、余额要够、冷却。
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

TIER_NORMAL, TIER_TIDU, TIER_ZONGDU = 0, 2, 3
TIER_NAMES = {TIER_NORMAL: "雏草姬", TIER_TIDU: "提督", TIER_ZONGDU: "总督"}


def tier_name(t: int) -> str:
    return TIER_NAMES.get(int(t), "雏草姬")


def tier_of(rec: Dict[str, Any]) -> int:
    return max(0, min(3, int(rec.get("t") or 0)))


def work_info(rec: Dict[str, Any], *,
              now: Optional[float] = None,
              cd: float = 3600.0,
              plain: Tuple[int, int] = (1, 100),
              tidu_base: Tuple[int, int] = (100, 300),
              tidu_mult: Tuple[float, float] = (1.1, 3.0),
              zongdu_base: Tuple[int, int] = (300, 500),
              zongdu_mult: Tuple[float, float] = (2.0, 5.0),
              fav_bonus: Tuple[int, int] = (10, 50),
              fav_per_ship: int = 10,
              rng: Optional[random.Random] = None) -> Dict[str, Any]:
    """算这次打工能拿多少（**不写账本**，写账本由调用方做）。"""
    rng = rng or random
    now = time.time() if now is None else now
    left = float(cd) - (now - float(rec.get("w") or 0.0))
    tier = tier_of(rec)
    tb = max(0, int(rec.get("tb") or 0))
    zb = max(0, int(rec.get("zb") or 0))
    boost = 50 * tb + 200 * zb            # 重复购买带来的基础加成
    mb = 0.3 * zb                        # 总督的基础倍率加成
    if left > 0:
        return {"ok": False, "left": int(left), "amt": 0, "extra": 0,
                "tier": tier, "base": 0, "mult": 0.0, "boost": boost, "mb": mb}

    extra, base, mult = 0, 0, 0.0
    if tier >= TIER_ZONGDU:
        lo, hi = sorted(zongdu_base)
        base = rng.randint(lo + boost, hi + boost)
        mlo, mhi = sorted(zongdu_mult)
        mult = round(rng.uniform(mlo, mhi) + mb, 2)      # 先定到 2 位再乘，回执里显示的数就是算的数
        amt = max(1, int(round(base * mult)))
    elif tier >= TIER_TIDU:
        lo, hi = sorted(tidu_base)
        base = rng.randint(lo + boost, hi + boost)
        mlo, mhi = sorted(tidu_mult)
        mult = round(rng.uniform(mlo, mhi), 2)
        amt = max(1, int(round(base * mult)))
    else:
        lo, hi = sorted(plain)
        amt = rng.randint(lo, hi)
        if int(rec.get("fv") or 0) > 0:
            flo, fhi = sorted(fav_bonus)
            extra = rng.randint(flo, fhi) + fav_per_ship * (int(rec["fv"]) - 1)
            amt += extra
        base = amt
        mult = 1.0
    return {"ok": True, "left": 0, "amt": amt, "extra": extra, "tier": tier,
            "base": base, "mult": round(mult, 2), "boost": boost, "mb": mb}


def sign_reward(streak: int, *, base: int = 20, step: int = 10, cap: int = 100) -> int:
    """签到奖励：连签越多越多，`base + step×(连签-1)`，封顶 `cap`。"""
    streak = max(1, int(streak))
    return min(cap, base + step * (streak - 1))


def sign_streak(rec: Dict[str, Any], *, today: str, yesterday: str) -> int:
    """算新的连签天数（读 `qs` 上次签到日期）。今天已签返回 0 表示"别给"。

    `yesterday` 由调用方算（这样才能注入时间做测试）。
    """
    qs = str(rec.get("qs") or "")
    if qs == today:
        return 0
    if qs == yesterday:
        return int(rec.get("st") or 0) + 1
    return 1


def patron_tier(spent: int, *, t1: int = 1000, t2: int = 3000) -> int:
    """0 = 普通；1 = 金主；2 = 大金主（只看累计消费）。"""
    sp = max(0, int(spent))
    if t2 > 0 and sp >= t2:
        return 2
    if t1 > 0 and sp >= t1:
        return 1
    return 0


def patron_name(t: int) -> str:
    return "大金主" if t >= 2 else ("金主" if t == 1 else "")


def can_upgrade(rec: Dict[str, Any], want: int, *, tidu_price: int, zongdu_price: int) -> Tuple[bool, str]:
    """能不能买/升级到 `want` 档。"""
    cur = tier_of(rec)
    want = int(want)
    if want <= cur:
        return False, "你现在已经是%s了" % tier_name(cur)
    price = zongdu_price if want >= TIER_ZONGDU else tidu_price
    if int(rec.get("c") or 0) < price:
        return False, "还差 %d 才能上%s" % (price - int(rec.get("c") or 0), tier_name(want))
    return True, ""


def upgrade_cost(want: int, *, tidu_price: int = 1998, zongdu_price: int = 19998) -> int:
    return int(zongdu_price if int(want) >= TIER_ZONGDU else tidu_price)


def donate_check(store_rec: Dict[str, Any], amt: int, *,
                 to_uid: str, from_uid: str,
                 lo: int = 1, hi: int = 1_000_000_000,
                 last_ts: float = 0.0, now: Optional[float] = None,
                 cd: float = 3.0) -> Tuple[bool, str]:
    """转账前置校验（纯函数）。"""
    amt = int(amt)
    if str(to_uid) == str(from_uid):
        return False, "不能转给自己"
    if amt < lo:
        return False, "最少转 %d" % lo
    if amt > hi:
        return False, "单笔最多 %d" % hi
    now = time.time() if now is None else now
    if last_ts and now - float(last_ts) < float(cd):
        return False, "别急，%d 秒后再转" % max(1, int(float(cd) - (now - float(last_ts))))
    if int(store_rec.get("c") or 0) < amt:
        return False, "余额不够（现在 %d）" % int(store_rec.get("c") or 0)
    return True, ""


def rank_rows(users: Dict[str, Dict[str, Any]], *, top: int = 10,
              exclude: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """按余额排行（只看正余额；`exclude` 用来剔机器人号）。"""
    ban = set(str(x) for x in (exclude or []))
    rows = []
    for uid, rec in (users or {}).items():
        if str(uid) in ban or not isinstance(rec, dict):
            continue
        bal = int(rec.get("c") or 0)
        if bal <= 0:
            continue
        rows.append({"uid": str(uid), "c": bal, "sp": int(rec.get("sp") or 0),
                     "t": tier_of(rec)})
    rows.sort(key=lambda r: (-r["c"], -r["sp"]))
    return rows[:max(1, int(top))]


def fmt_amount(n: int, unit: str = "鲸圆券") -> str:
    n = int(n)
    if n >= 10000_0000:
        return "%.2f 亿" % (n / 10000_0000.0)
    if n >= 10000:
        return "%.2f 万" % (n / 10000.0)
    return "%d %s" % (n, unit)

