# CQWE V2.8 — 冻结权重、严格晚于历史检查点的离线对照实验

新增 `cqwe/forward_experiment_v28.py`，复用 V2.1 校验过的检查点和 V2.7 变异登记簿，在未参加先前训练且时间戳严格晚于检查点的新 5 分钟 OHLCV 文件中，冻结 `(0.12,0.0)` 规则权重，预注册 `.10` 和 `.20` 两个局部节点阈值，分别用**各自独立的单一$10虚拟资金账户**进行下一开盘价假设成交、手续费和滑点核算。两种方案是互斥对照，不能将其资金相加。

严格防范：时间戳不晚于学习截止、与截止时间不连续、市场集合变化、旧行情文件哈希重复、证据哈希损坏、非法成本、样本不足、空权重；都必须失败，而不是回退重复回测。前24个新K线仅用于建立新片段指标窗口。

当前已使用的30天历史数据**禁止**重新标记为独立前向样本。这里仅验证时间顺序，不保证数据选择独立、盘口可成交或真实盈利。只做研究，不连接交易所，不自动批准策略。

## 安装（解压到D:\CQWE_MASTER_V28）
`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V28\CQWE_MASTER_V28\INSTALL_MASTER_V28.ps1"`

## 运行（仅在另行取得之后的新行情并保存成与V12相同JSON结构后）
```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.forward_experiment_v28 `
  --registry "reports\v27_mutation_registry.json" `
  --store "reports\v21_evidence" `
  --inputs "data\future\BTCUSDT_5m.json" "data\future\ETHUSDT_5m.json" "data\future\SOLUSDT_5m.json" "data\future\BNBUSDT_5m.json" `
  --output "reports\v28_forward_experiment.json"
```
新行情不存在时不要执行命令，更不要修改旧行情时间戳来骗过检查。

## 清理
本版不删除已被CLI/测试引用的历史代码，继续保留原有完整依赖。仅新增一个有独立边界的分析模块以及专用测试；下一轮评估动态入口与移除证明。
