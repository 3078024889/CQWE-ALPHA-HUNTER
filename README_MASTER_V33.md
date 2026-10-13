# CQWE V3.3 | 哥白尼有界树突实验 + 全平仓虚拟账户

本版本不承诺盈利，**不启用真实交易**，不访问账户API或密钥。

## 改动
- 删除 V3.3 执行链中半仓减仓：只允许 `BUY`、`ADD`、`SELL`，卖出立即平掉全仓。
- 更正 V3.2 趋势加仓专家拼写：`trend_volume` / `breakout`。仍须受 `$10`现金和最低模拟成交额限制；默认$6建仓剩约$4时无法加仓，属于正常拒绝。
- 保护已有 `reports/v32_cash_account` 日志，V3.3独立记录到 `reports/v33_cash_account`。启用新任务之前检查V3.2是否存在持仓/待执行单；若有则拒绝自动切换，不能暗中丢弃持仓。
- V3.3 只在K线收盘之后登记模拟意图，按预先登记的后续K线开盘价格进行历史观察性模拟。
- 哥白尼实验空间五轴：拓扑6、响应6、可塑性6、记忆6、元学习6，共7776理论组合。只预登记6组对照；每个机制有独立实现，不能将参数枚举冒充已完成进化。
- 已看过的历史4币数据只用于研究、回归诊断；按时间60/20/20分段的最后一段**不能宣称为从未利用过的独立外样本**。事件收益代理不是实际/模拟账户PnL，不参与晋升。

## 安装
解压到 `D:\CQWE_MASTER_V33\CQWE_MASTER_V33`，执行 `INSTALL_MASTER_V33.ps1`。
本包不会删除 V3.2 模块或原始证据。只有完成动态依赖审计和兼容测试，才能删除旧模块。

## 命令
`C:\Python314\python.exe -m cqwe.live_paper_v33`

`C:\Python314\python.exe -m cqwe.copernican_lab_v33 --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json --output reports\v33_copernican_research.json`

首次运行测试通过并确认旧V3.2账户没有持仓/排队意图后，执行 `D:\CQWE\alpha-hunter\ENABLE_ACCOUNT_V33.ps1` **替换同名5分钟虚拟账户任务**，而不是创建第四个资金账户；V3.1滚动观察与V3.0每小时研究继续保持。

## 研究安全边界
- 只做无杠杆、现金现货纸面研究；示例最低成交额$5不是交易所真实过滤器。
- 强制全平仍只在后续K线进行模拟，无法保证滑点、跳空与真实成交。
- 任何实验不自动晋升、改写历史、下单、发送密钥或推送GitHub。
