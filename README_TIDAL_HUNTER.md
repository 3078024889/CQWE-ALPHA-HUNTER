# 首个哥白尼潮汐猎手：合约订单簿研究链

本实现直接位于本地仓库 `D:\CQWE\alpha-hunter`，不需要下载ZIP。它已实际接入币安USD-M公开增量深度和主动成交，支持模拟建仓/平仓、成熟标签学习、状态继承和断流保护。**尚未证明盈利；不托管账户，不读取密钥，不发送真实订单。**

## 已解决的关键缺口

旧V42/V43/V47接的是现货深度，不能直接视为合约订单簿。新模块使用合约`U/u/pu`协议，REST快照与缓存增量桥接后才提供有效报价；后续每次检查`pu == previous u`。缺口、异常价格、交叉订单簿或已知深度不足都会中止使用该订单簿。

当前深度连接为`wss://fstream.binance.com/public/ws/<symbol>@depth@100ms`，成交连接为`wss://fstream.binance.com/market/ws/<symbol>@aggTrade`。它们使用币安当前的端点分流。没有把现货的同步规则或旧合约单连接地址照搬进来。

## 做市商研究对应哪些机制

做市商通常通过双边报价提供流动性，其经济结果受到价差、费用、库存暴露、逆向选择、排队和对冲成本共同影响。库存偏斜可以让报价朝减少库存的方向移动；收到可能有信息含量的成交冲击后，报价可能变宽或撤回。不同提供者的竞争也会改变可见价差与深度。

本项目观察的是这些机制的聚合结果。市场按价格聚合的L2没有做市商身份、每笔订单队列、隐藏数量或机构间对冲信息；不能据此数出做市商数量，更不能宣称已经识别某家机构的持仓或意图。深度减少可能来自成交、撤单及两者的组合；不会直接当作我们的被动挂单成交。

实现的四维输入：五档深度不平衡、最优档订单流不平衡OFI、最近两秒主动买卖成交额差、短时中价变化。它们输入两个非线性树突分支。只有未来报价成熟后才更新权重与关联记忆。

预先固定的对照包括线性模型、冻结树突、现金基线、深度不平衡方向和一个反向报价倾向代理。最后一个仅是简化的反向信号对照，**不是完整Avellaneda–Stoikov策略，也不是实际做市商收益**。所有被动成交计数保持为零。

参考的一手研究：

- [Avellaneda–Stoikov：High-frequency trading in a limit order book](https://math.nyu.edu/~avellane/HighFrequencyTrading.pdf)，库存风险与信息不对称风险、双边报价。
- [Cont–Kukanov–Stoikov：The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)，OFI与短时价格变化的实证研究；不能直接外推为币安盈利证明。
- [币安合约本地订单簿同步协议](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)。
- [币安WebSocket分流与迁移说明](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice)。

## 建仓、平仓与“滚仓”的实际含义

这是显式标记的虚拟无杠杆实验账户，初始虚拟余额10 USDT，与真实账户余额无关。历史成熟信号经过描述性净成本筛选，并与当前深度和主动成交方向一致时，才允许生成模拟建仓意图。至少需要30个有方向的成熟样本；该筛选未修正序列相关或多重比较，不能视为统计显著性或实盘准入。

模拟生命周期为：空仓 → 入场等待 → 单一多仓/空仓 → 退出等待 → 平仓及冷却 → 新一轮。没有同时堆叠多空或摊平亏损。模拟入场最多使用已平仓虚拟现金的一半，扣除费用预算后，按公开合约过滤器进行数量取整。**浮盈不计入下一笔仓位预算。**关闭虚拟仓位后的余额变化才影响下一笔模拟预算。

成交假设包括250毫秒延迟，随后出现的新鲜深度、逐档VWAP、每档最多使用可见数量的10%、双边假设手续费。延迟过大、流动性不足、最低名义金额或现金不满足时拒绝模拟成交。退出通过反向操作减少已有虚拟仓位，不产生新反向仓位。

停止条件包括模拟损失阈值、模拟盈利阈值、持有时间、反向信号和回撤；这些都是固定实验参数，未经优化验证。发生缺口或断流时撤销未执行意图，保留并披露已有虚拟敞口，不用旧报价伪造平仓。

未建模资金费率、真实撮合队列、实际手续费等级、真实延迟分布、保证金、清算和参与者对冲。这不是可直接下实盘合约订单的执行器。扩大本金后，流动性容量、冲击和保证金约束均会变化；小额实验成功也不能证明数亿元资金可以复制。

## 成长、修复与可复现性

每次预测先落盘，记录当时的订单簿、特征、模型摘要和预测；未来五秒的可用报价形成成熟标签后才学习。过期标签和跨断流标签丢弃。每个采集记录包含顺序号、前条摘要和自身摘要。

序列缺口会触发暂停和重新获取快照；WebSocket故障允许有限重连，并清空跨缺口的特征状态和未成熟预测，保留此前成熟的权重。修复次数有上限；无法恢复就记录失败。暂停、修复、失败均不会被算作成功学习或盈利。

通过`--previous checkpoint.json`继承树突/线性/冻结模型和过去统计，验证上下文、参数边界和更新计数。**模型记忆可以跨会话继承；虚拟账户和持仓目前不跨会话继承**，报告显式标注这一点，不能将多个会话各自的10 USDT叠加为一条资金曲线。

`--replay`重新校验原始记录链、重建原始深度、核对每一个派生订单簿，再重算预测、标签、模型状态和虚拟账本。摘要只能证明内部一致性；本地文件不等同于第三方不可篡改时间戳或交易所成交证明。

## 本次真实运行

首段45秒BTCUSDT采集成功：434个同步订单簿帧、498个聚合成交事件、8个成熟预测，1389条链记录；无序列修复事件。重新回放后，原始深度、学习状态和虚拟账本一致。所有模型的成本后代理均值为负或无交易；没有因此提高仓位。

源记录：`D:\CQWE_DATA\tidal_hunter\BTCUSDT_1792028784551536400_f17c57be`。

当次公开`exchangeInfo`返回BTCUSDT市价数量步长0.001、最低名义金额50 USDT。10 USDT虚拟无杠杆账户无法通过这个最低金额；程序不会把提高杠杆作为绕过条件。该规则是采集时快照，不保证未来不变。

后续90秒运行继承首段checkpoint，用于验证真实流上的跨会话学习。最终计数、回放与测试结果将记录在`reports/tidal_hunter_validation_20261015.json`。

## 使用

本机已验证Python为`C:\Python314\python.exe`，已安装`websocket-client 1.9.2`。代码运行只使用该依赖和标准库。

```powershell
Set-Location 'D:\CQWE\alpha-hunter'
& 'C:\Python314\python.exe' -m unittest tests.test_tidal_hunter -v
& .\RUN_TIDAL_HUNTER.ps1 -Symbol BTCUSDT -Seconds 90
```

继续模型记忆或验证既有会话：

```powershell
& 'C:\Python314\python.exe' -m cqwe.tidal_hunter --seconds 90 --previous 'D:\CQWE_DATA\tidal_hunter\BTCUSDT_1792028784551536400_f17c57be\checkpoint.json'
& 'C:\Python314\python.exe' -m cqwe.tidal_hunter --replay 'D:\CQWE_DATA\tidal_hunter\BTCUSDT_1792028784551536400_f17c57be'
```

每个会话都有`capture.jsonl`、`checkpoint.json`和`report.json`。采集时长限制15—600秒，写盘预算和消息队列均有限制；没有安装定时任务或后台实盘进程。

## 仓库状态

已核对本地origin指向用户提供的GitHub仓库。2026-10-15检查时，本地HEAD为`ab20b4f`，远端main为`b90ce10`，本地已有39个提交尚未包含于远端main；此外有之前版本的未跟踪源码。本批新增文件保留在本地工作区，没有重置、覆盖或推送这些历史修改。
