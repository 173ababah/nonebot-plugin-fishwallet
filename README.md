# nonebot-plugin-fishwallet 🐟

> 群里的「鲸圆券」经济系统：**每日补给 / 打工 / 签到 / 提督总督 / 金主档 / 转账 / 排行**。
> **零 LLM 开销** —— 纯账本，一分钱 token 都不花。

从跑了半年的 QQ 机器人（[肥鱼人设](https://github.com/173ababah)）里拆出来的经济模块，
规则和数值都是线上调过的。

## 命令

| 命令 | 说明 |
|------|------|
| `/coin` | 查余额（顺手结算初始金额和今日补给，并显示身份：提督/总督/金主） |
| `/coin 打工` | 挣钱；冷却默认 1 小时；上过舰还有额外加成 |
| `/coin 签到` | 连签递增（20 / 30 / 40 … 封顶 100） |
| `/coin 排行` | 余额榜（剔机器人号，只显示正余额） |
| `/coin 转账 @某人 100` | 给群友转账（不能转给自己、有上限、要够钱） |
| `/coin 上提督` `/coin 上总督` | 花钱升档，打工区间立刻变成"大合同" |

## 数值（全在 `.env`，`FISHWALLET_*`）

```ini
FISHWALLET_NAME=鲸圆券
FISHWALLET_START=10          # 新人初始
FISHWALLET_DAILY=10          # 每日补给
FISHWALLET_WORK_CD=3600      # 打工冷却(秒)
FISHWALLET_WORK_MIN=1
FISHWALLET_WORK_MAX=100      # 普通用户区间
FISHWALLET_WORK_TIDU_BASE=(100,300)
FISHWALLET_WORK_TIDU_MULT=(1.1,3.0)
FISHWALLET_WORK_ZONGDU_BASE=(300,500)
FISHWALLET_WORK_ZONGDU_MULT=(2.0,5.0)
FISHWALLET_TIDU_PRICE=1998
FISHWALLET_ZONGDU_PRICE=19998
FISHWALLET_PATRON_T1=1000    # 累计消费 → 金主
FISHWALLET_PATRON_T2=3000    # 累计消费 → 大金主
```

## 三条设计取舍（都踩过坑）

### 1. 惰性结算，不用定时任务

机器人可能几小时没消息，`cron` 补发会漏。做法：**每次读记录时**拿 `d`（上次结算日期）比今天，
不一样就补一次。这样不管中间断没断网，回来第一句话就把该给的补给补上。

### 2. 余额允许为负

别的插件（抽卡、炒股）可能把人扣穿。`add()` **不夹 0** —— 负余额得靠打工慢慢填，
夹 0 等于帮人免债。只有 `spend()` 会拒绝（余额不够就返回 False、不动账本）。

### 3. 金主档只看「累计消费」，不看余额

`sp` 记的是花出去的钱（爆米/上舰/转账），退款会把它扣回去 —— 否则有人反复"转账后退款"刷金主。
余额再多也不是金主，这条是线上用户定的。

## 作为库用（给别的插件记账）

```python
from nonebot_plugin_fishwallet import STORE   # 或自己 new 一个 Store(path)

ok = STORE.spend(uid, 5)          # 扣 5 张，不够返回 False
STORE.add(uid, 5)                 # 加钱（可为负余额填坑）
STORE.rec(uid)["c"]               # 查余额
```

`Store` 是纯 Python（无 nonebot 依赖），可以直接在别的项目里用。

## 测试

```bash
python -m pytest tests -q     # 16 passed
```

覆盖：惰性结算（同日/隔日）、扣钱失败不动账、负余额、退款回滚 `sp`、
打工冷却/分档/重复购买加成、连签、金主档、升档校验、转账校验、排行去重与排序。

## License

MIT
