# CQWE V1.4 — Research Evidence Engine / 全量科研总包

## 实现审计结论

- 公开量化框架 Freqtrade 的前瞻偏差审查：禁止信号使用未来栏。
- Polymarket 开源研究机器人：借鉴深度逐档成交、部分成交的拒绝逻辑、过期行情拒绝、双腿匹配与成本缓冲；不复制实盘登录或下注功能。
- 成功故事不是业绩证明。收益截图、模拟盘口价差与单笔高收益不能取代已实现成交与资金流水。
- 预测市场、二元事件的监管和市场准入依司法管辖区不同；本包完全离线，**不连接Polymarket或任何交易账户**。

## V1.4 新增 `cqwe.edge_lab_v14`

1. 逐档价量加权：买入YES、NO两腿的深度够不够；不是只比较顶部最优价。
2. 三重失效保护：事件互补关系未证实 / 行情未知或过期 / 交易成本吞噬价差。
3. 即使所有条件合格也只输出 `RESEARCH_CANDIDATE_ONLY`，不报告“无风险利润”。
4. 交易事件的事后成本压力测试，拒绝小样本、无留出样本和成本后非正均值。
5. 原始币安K线SHA256与连续性验证。
6. 只读JSON输入，不包含交易API、账户密钥或任何后台服务。

## 运行（Windows）

```powershell
cd D:\CQWE\alpha-hunter
& 'C:\Python314\python.exe' -m unittest discover -v
& 'C:\Python314\python.exe' -m cqwe.edge_lab_v14 manifest --inputs 'data\v12\BTCUSDT_5m_30d.json' 'data\v12\ETHUSDT_5m_30d.json' --output 'reports\v14_manifest.json'
```

预测市场模拟案例（**人为构造，仅用于测试数学与风险闸门，不是现实报价**）：

```powershell
& 'C:\Python314\python.exe' -m cqwe.edge_lab_v14 books --input 'examples\synthetic_books.json' --output 'reports\v14_synthetic_books.json'
```

附带的 `reference_source/` 是完整的截至V1.3参考源码快照，供代码审计/灾难恢复；安装器只添加V1.4文件，不覆盖正式项目已有模块和数据。

## 尚未完成

- 没有在线订单簿监测或真正的事件互补关系认证。
- 没有账户资金对账、实盘成交、动态交易所手续费、双腿同步成交或结算保证。
- 没有可证明的量化正期望、个人净利润、交易信号的统计显著性。
- 原V1.2历史OI覆盖不足仍未解决。V1.4绝不把它误写成已覆盖。

## Research references

- https://docs.freqtrade.io/en/2026.5/lookahead-analysis/
- https://github.com/zostaff/poly-arbitrage-bot
- https://github.com/josemlopez/polymarket-arbitrage
- https://github.com/sedarged/polymarket-bot/blob/main/docs/paper-trading.md
- https://github.com/TimoWasTaken/tradingbot

参考开源项目的架构思想，未拷贝第三方受版权保护的源文件。
