# CQWE MASTER V1.9 | 树突局部学习与证据继承

此版本延续V1.8；只读、离线、无杠杆、无真实交易。

## 主要机制
- 相同系统的局部节点（币种×市场状态×专家）在事件到期后依据净收益更新权重。
- 节点变异采用可控且可重现的状态版本/检查点；不修改源码、不执行生成代码。
- 训练成果以JSON检查点和SHA256记录；重叠历史拒绝重新学习。
- 分离训练期与冻结留出期；冻结留出期不更新状态，防止独立检验污染。
- 保留原V1.8统一虚拟账户作为真实对照；V1.9留出期事件收益不能当作账户利润。

## Windows安装
`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V19\CQWE_MASTER_V19\INSTALL_MASTER_V19.ps1"`

## 实际历史研究
`C:\Python314\python.exe -m cqwe.local_learning_v19 --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json --output reports\v19_local_learning.json --checkpoint reports\v19_state.json`

**重要：** 相同数据运行第二次会明确拒绝重叠学习，不能通过反复喂同一段历史积累虚假经验。检查点继续学习需要新的、不重叠的后续数据，并有独立时间验证。研究尚不支持实时常驻服务和真钱下单。

## 对照
`C:\Python314\python.exe -m cqwe.unified_paper_v18 --inputs data\v12\BTCUSDT_5m_30d.json data\v12\ETHUSDT_5m_30d.json data\v12\SOLUSDT_5m_30d.json data\v12\BNBUSDT_5m_30d.json --min-notional-usd 1 --output reports\v18_baseline.json`

小说《哥白尼》的树突网络和边缘情况为启发来源，不等于小说提供了盈利算法或经验证的AI实现。
