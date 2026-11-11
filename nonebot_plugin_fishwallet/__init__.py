"""nonebot-plugin-fishwallet —— 群里的「鲸圆券」经济系统。

命令：

| 命令 | 说明 |
|------|------|
| `/coin` | 查余额（顺手结算初始/每日补给） |
| `/coin 打工` | 打工挣钱（有冷却，会员档不同区间不同） |
| `/coin 签到` | 每日签到（连签递增） |
| `/coin 排行` | 余额榜（前 N 名） |
| `/coin 转账 @某人 100` | 给群友转账 |
| `/coin 上提督` / `/coin 上总督` | 花钱升档（打工区间立刻变成大合同） |

设计：**零 LLM 开销**，纯账本。所有数值走 `.env`，`FISHWALLET_*`。
"""

from __future__ import annotations

import os
import time

from nonebot import get_plugin_config, on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from . import economy
from .config import Config
from .store import Store

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-fishwallet",
    description="群经济系统：每日补给 / 打工 / 签到 / 提督总督 / 金主档 / 转账 / 排行",
    usage="/coin | /coin 打工 | /coin 签到 | /coin 排行 | /coin 转账 @某人 100 | /coin 上提督",
    type="application",
    config=Config,
    homepage="https://github.com/173ababah/nonebot-plugin-fishwallet",
    supported_adapters={"~onebot.v11"},
)

cfg = get_plugin_config(Config)
STORE = Store(os.path.join(os.getcwd(), "data", "fishwallet", "coins.json"),
              start=cfg.fishwallet_start, daily=cfg.fishwallet_daily)
UNIT = cfg.fishwallet_name

coin_cmd = on_command("coin", aliases={"鲸圆券", "金币"}, priority=15, block=True)


def _uid(event: Event) -> str:
    for name in ("get_user_id",):
        fn = getattr(event, name, None)
        if callable(fn):
            try:
                return str(fn())
            except Exception:
                pass
    return ""


def _yesterday() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))


@coin_cmd.handle()
async def _(event: Event, arg: Message = CommandArg()):
    if not cfg.fishwallet_enabled:
        await coin_cmd.finish("经济系统关着呢（FISHWALLET_ENABLED=false）")
    uid = _uid(event)
    if not uid:
        await coin_cmd.finish("认不出你是谁…")
    text = arg.extract_plain_text().strip()
    rec = STORE.rec(uid)

    if not text:
        head = "你有 **%d** %s" % (rec["c"], UNIT)
        if rec["got"]:
            head += "（刚到账 %d）" % rec["got"]
        extra = []
        if rec["t"]:
            extra.append(economy.tier_name(rec["t"]))
        pn = economy.patron_name(economy.patron_tier(rec["sp"]))
        if pn:
            extra.append(pn)
        if extra:
            head += "\n身份：%s" % " · ".join(extra)
        head += "\n累计消费 %d · 上舰 %d 次" % (rec["sp"], rec["fv"])
        await coin_cmd.finish(head)

    sub, _, rest = text.partition(" ")
    sub = sub.strip()

    if sub in ("打工", "上班", "搬砖"):
        info = economy.work_info(
            rec, cd=cfg.fishwallet_work_cd,
            plain=(cfg.fishwallet_work_min, cfg.fishwallet_work_max),
            tidu_base=tuple(cfg.fishwallet_work_tidu_base),
            tidu_mult=tuple(cfg.fishwallet_work_tidu_mult),
            zongdu_base=tuple(cfg.fishwallet_work_zongdu_base),
            zongdu_mult=tuple(cfg.fishwallet_work_zongdu_mult))
        if not info["ok"]:
            m = max(1, info["left"] // 60)
            await coin_cmd.finish("刚干完，歇 %d 分钟再来" % m)
        STORE.add(uid, info["amt"])
        r = STORE.raw(uid)
        r["w"] = time.time()
        STORE.save()
        msg = "打工赚了 **%d** %s" % (info["amt"], UNIT)
        if info["extra"]:
            msg += "（含上舰加成 %d）" % info["extra"]
        if info["tier"]:
            msg += "\n%s合同：基础 %d × %.2f" % (
                economy.tier_name(info["tier"]), info["base"], info["mult"])
        await coin_cmd.finish(msg + "\n现在有 %d" % STORE.rec(uid)["c"])

    if sub in ("签到", "签"):
        today = time.strftime("%Y-%m-%d")
        streak = economy.sign_streak(rec, today=today, yesterday=_yesterday())
        if streak == 0:
            await coin_cmd.finish("今天已经签过了")
        amt = economy.sign_reward(streak)
        r = STORE.raw(uid)
        r["qs"] = today
        r["st"] = streak
        r["c"] = int(r.get("c") or 0) + amt
        STORE.save()
        await coin_cmd.finish("签到成功，连签 %d 天 → **%d** %s" % (streak, amt, UNIT))

    if sub in ("排行", "排行版", "rank"):
        rows = economy.rank_rows(STORE.all_users(), top=cfg.fishwallet_rank_top,
                                 exclude=[getattr(event, "self_id", "")])
        if not rows:
            await coin_cmd.finish("还没有人有%s" % UNIT)
        lines = ["%s 排行：" % UNIT]
        for i, r in enumerate(rows, 1):
            tag = economy.tier_name(r["t"]) if r["t"] else ""
            lines.append("%d. %s — %d %s%s" % (i, r["uid"], r["c"], UNIT,
                                               ("（%s）" % tag) if tag else ""))
        await coin_cmd.finish("\n".join(lines))

    if sub in ("转账", "给") or sub.startswith("转账"):
        parts = rest.split()
        target = ""
        amt = 0
        for p in parts:
            qq = "".join(ch for ch in p if ch.isdigit())
            if qq and len(qq) >= 5 and not target:
                target = qq
            elif qq and not amt:
                amt = int(qq)
        ok, why = economy.donate_check(
            rec, amt, to_uid=target, from_uid=uid,
            lo=cfg.fishwallet_donate_min, hi=cfg.fishwallet_donate_max,
            last_ts=float(rec.get("w") or 0.0), cd=0.0)   # 冷却用专门的键，见 README
        if not ok:
            await coin_cmd.finish(why)
        STORE.spend(uid, amt)
        STORE.add(target, amt)
        await coin_cmd.finish("转给 %s **%d** %s" % (target, amt, UNIT))

    if sub in ("上提督", "上总督", "买提督", "买总督"):
        want = economy.TIER_ZONGDU if "总督" in sub else economy.TIER_TIDU
        ok, why = economy.can_upgrade(rec, want,
                                      tidu_price=cfg.fishwallet_tidu_price,
                                      zongdu_price=cfg.fishwallet_zongdu_price)
        if not ok:
            await coin_cmd.finish(why)
        cost = economy.upgrade_cost(want, tidu_price=cfg.fishwallet_tidu_price,
                                    zongdu_price=cfg.fishwallet_zongdu_price)
        if not STORE.spend(uid, cost):
            await coin_cmd.finish("余额不够（要 %d）" % cost)
        r = STORE.raw(uid)
        r["t"] = want
        if want >= economy.TIER_ZONGDU:
            r["zb"] = int(r.get("zb") or 0) + 1
        else:
            r["tb"] = int(r.get("tb") or 0) + 1
        STORE.save()
        await coin_cmd.finish("恭喜上了%s！打工区间立刻变大（花了 %d %s）" %
                             (economy.tier_name(want), cost, UNIT))

    await coin_cmd.finish(
        "/coin 查余额\n/coin 打工\n/coin 签到\n/coin 排行\n/coin 转账 @某人 100\n/coin 上提督")
