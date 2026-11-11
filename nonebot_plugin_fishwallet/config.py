"""配置（.env 前缀 FISHWALLET_）。数值都能改，默认值来自线上跑了半年的那套。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Config(BaseModel):
    fishwallet_enabled: bool = Field(default=True, description="总开关")
    fishwallet_name: str = Field(default="鲸圆券", description="货币名（会出现在所有文案里）")
    fishwallet_start: int = Field(default=10, description="新人初始金额")
    fishwallet_daily: int = Field(default=10, description="每天补给（惰性结算：下次交互时补）")
    fishwallet_work_cd: float = Field(default=3600.0, description="打工冷却（秒）")
    fishwallet_work_min: int = Field(default=1, description="普通用户打工下限")
    fishwallet_work_max: int = Field(default=100, description="普通用户打工上限")
    fishwallet_work_tidu_base: tuple = Field(default=(100, 300), description="提督打工基础区间")
    fishwallet_work_tidu_mult: tuple = Field(default=(1.1, 3.0), description="提督打工随机倍率")
    fishwallet_work_zongdu_base: tuple = Field(default=(300, 500), description="总督打工基础区间")
    fishwallet_work_zongdu_mult: tuple = Field(default=(2.0, 5.0), description="总督打工随机倍率")
    fishwallet_tidu_price: int = Field(default=1998, description="提督价格")
    fishwallet_zongdu_price: int = Field(default=19998, description="总督价格")
    fishwallet_patron_t1: int = Field(default=1000, description="累计消费到多少算「金主」")
    fishwallet_patron_t2: int = Field(default=3000, description="累计消费到多少算「大金主」")
    fishwallet_donate_min: int = Field(default=1, description="转账下限")
    fishwallet_donate_max: int = Field(default=1_000_000_000, description="转账上限")
    fishwallet_donate_cd: float = Field(default=3.0, description="转账冷却（秒）")
    fishwallet_rank_top: int = Field(default=10, description="排行显示几名")
