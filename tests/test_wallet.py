"""账本 + 规则的单元测试（不依赖 nonebot，随机源可注入）。"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nonebot_plugin_fishwallet"))

import economy  # noqa: E402
from store import Store  # noqa: E402


def _store(**kw):
    d = tempfile.mkdtemp()
    return Store(os.path.join(d, "coins.json"), **kw)


# ---------------- store ----------------

def test_initial_and_daily_settlement():
    s = _store(start=10, daily=10)
    rec = s.rec("100")
    assert rec["c"] == 20 and rec["got"] == 20      # 初始 10 + 今日补给 10
    assert s.rec("100")["got"] == 0                 # 同一天再来不再补
    assert s.rec("100")["c"] == 20


def test_next_day_settles_again():
    s = _store(start=0, daily=7)
    s.rec("100")
    r = s.raw("100")
    r["d"] = "2000-01-01"                          # 假装上次结算是很久以前
    s.save()
    rec = s.rec("100")
    assert rec["got"] == 7


def test_spend_and_insufficient():
    s = _store(start=100, daily=0)
    assert s.spend("1", 30) is True
    assert s.rec("1")["c"] == 70
    assert s.spend("1", 1000) is False             # 不够 → 不动账本
    assert s.rec("1")["c"] == 70


def test_add_allows_negative_balance_recovery():
    s = _store(start=0, daily=0)
    r = s.raw("1")
    r["c"] = -50
    s.save()
    assert s.rec("1")["c"] == -50
    assert s.add("1", 20) == -30                   # 加钱先填坑，不夹 0


def test_refund_rolls_back_spent():
    s = _store(start=100, daily=0)
    s.spend("1", 40)
    assert s.rec("1")["sp"] == 40
    s.refund("1", 40)
    rec = s.rec("1")
    assert rec["c"] == 100 and rec["sp"] == 0


def test_empty_records_cleaned():
    s = _store(start=0, daily=0)
    s.rec("ghost")
    s.save()
    assert "ghost" not in s.all_users()


# ---------------- economy ----------------

def test_work_cooldown():
    rng = random.Random(1)
    rec = {"c": 0, "w": 1000.0}
    info = economy.work_info(rec, now=1100.0, cd=3600, rng=rng)
    assert info["ok"] is False and info["left"] > 0


def test_work_plain_range_and_fav_extra():
    rng = random.Random(7)
    rec = {"c": 0, "w": 0.0, "fv": 3}
    info = economy.work_info(rec, now=10_000.0, cd=3600, plain=(1, 100), rng=rng)
    assert info["ok"]
    assert 1 <= info["base"] <= 100 + 50 + 10 * 2
    assert info["extra"] >= 10 + 10 * 2            # 上舰加成 = 10~50 + 10×(次数-1)


def test_work_tidu_scales_with_base_and_mult():
    rng = random.Random(3)
    rec = {"c": 0, "w": 0.0, "t": 2}
    info = economy.work_info(rec, now=10_000.0, cd=3600, rng=rng)
    assert info["ok"]
    assert 100 <= info["base"] <= 300
    assert 1.1 <= info["mult"] <= 3.0
    assert info["amt"] == max(1, round(info["base"] * info["mult"]))


def test_work_zongdu_and_repeat_bonus():
    rng = random.Random(5)
    rec = {"c": 0, "w": 0.0, "t": 3, "zb": 2}
    info = economy.work_info(rec, now=10_000.0, cd=3600, rng=rng)
    assert info["boost"] == 400                    # 200 × 2
    assert info["mb"] == 0.6
    assert 500 <= info["base"] <= 500 + 400        # 300~500 基础 + 加成
    assert info["mult"] >= 2.0 + 0.6


def test_sign_streak_and_reward():
    assert economy.sign_streak({"qs": "2026-11-11"}, today="2026-11-11", yesterday="2026-11-10") == 0
    assert economy.sign_streak({"qs": "2026-11-10", "st": 4}, today="2026-11-11", yesterday="2026-11-10") == 5
    assert economy.sign_streak({"qs": "2026-11-01"}, today="2026-11-11", yesterday="2026-11-10") == 1
    assert economy.sign_reward(1) == 20
    assert economy.sign_reward(5) == 60
    assert economy.sign_reward(999) == 100         # 封顶


def test_patron_tiers():
    assert economy.patron_tier(0) == 0
    assert economy.patron_tier(999) == 0
    assert economy.patron_tier(1000) == 1
    assert economy.patron_tier(3000) == 2
    assert economy.patron_name(2) == "大金主"


def test_upgrade_rules():
    rec = {"c": 5000, "t": 0}
    ok, why = economy.can_upgrade(rec, 2, tidu_price=1998, zongdu_price=19998)
    assert ok is True
    ok, why = economy.can_upgrade(rec, 3, tidu_price=1998, zongdu_price=19998)
    assert ok is False and "总督" in why
    ok, why = economy.can_upgrade({"c": 0, "t": 2}, 2, tidu_price=1998, zongdu_price=19998)
    assert ok is False


def test_donate_checks():
    rec = {"c": 100}
    assert economy.donate_check(rec, 50, to_uid="2", from_uid="1")[0] is True
    assert "自己" in economy.donate_check(rec, 50, to_uid="1", from_uid="1")[1]
    assert "余额" in economy.donate_check(rec, 500, to_uid="2", from_uid="1")[1]
    assert "最少" in economy.donate_check(rec, 0, to_uid="2", from_uid="1")[1]
    ok, why = economy.donate_check(rec, 50, to_uid="2", from_uid="1",
                                   last_ts=100.0, now=101.0, cd=3.0)
    assert ok is False and "秒后" in why


def test_rank_rows_sorted_and_filtered():
    users = {"1": {"c": 100, "sp": 0}, "2": {"c": 300, "sp": 5},
             "3": {"c": 0}, "bot": {"c": 9999}, "4": {"c": 300, "sp": 9}}
    rows = economy.rank_rows(users, top=3, exclude=["bot"])
    assert [r["uid"] for r in rows] == ["4", "2", "1"]
    assert all(r["c"] > 0 for r in rows)


def test_fmt_amount():
    assert economy.fmt_amount(1234) == "1234 鲸圆券"
    assert "万" in economy.fmt_amount(23456)
    assert "亿" in economy.fmt_amount(250000000)
