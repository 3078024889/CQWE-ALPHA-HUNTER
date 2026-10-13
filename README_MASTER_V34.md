# CQWE V3.4 | 真实前向树突学习的安全闭环

- **V3.3已确认在用户Windows成功运行**，但尚未有盈利证据；V3.4新增独立的6候选在线研究链，不修改V3.3运行账户。
- V3.3命令行缺陷修复：`live_paper_v33`默认写入 `reports/v33_cash_account`，而不是误写V3.2目录；旧文件、账本不删除。
- 每5分钟读取最近400根完整公开K线，用预登记的6个哥白尼候选各自产生预测；下一次取得目标K线完整收盘后，才使用其方向标签对候选单独更新。
- 每条证据包含时间戳、行情哈希、冻结基因型、权重、误差累计、前驱哈希；没有新K线不重复记录，缺口不事后补写。
- 初始实验只固定 BNBUSDT（事前选定），其余三市场继续由原系统监控。扩大标的必须另起预登记实验，不能暗中择优。
- **重要**：由于5分钟行情收盘后的自然延迟，预测可能在目标K线开盘后才注册，因此只形成目标K线收盘前已记录的预测；它不是开盘可执行的盈利证明。
- 方向命中率与误差平方和只用于科研，未计算真实成交、账户净收益或独立显著性。不自动选择胜者，不改写冻结V3.3权重，不接入交易API。

## Windows安装
解压ZIP至 `D:\CQWE_MASTER_V34` 后仅应出现路径 `D:\CQWE_MASTER_V34\CQWE_MASTER_V34\INSTALL_MASTER_V34.ps1`。

执行 `INSTALL_MASTER_V34.ps1`。安装器尊重既有自动任务、Git状态、运行数据与日志。

先手动运行：
`C:\Python314\python.exe -m cqwe.forward_dendrites_v34`

确认成功，再运行：
`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE\alpha-hunter\ENABLE_DENDRITES_V34.ps1"`

查看：`Get-Content D:\CQWE\alpha-hunter\reports\collection_logs\dendrites_v34.log -Tail 20`。

## 核心限制与后续
任何中断超过1根K线，当前研究链拒绝事后拟造预测。需要另开完整证据谱系的恢复机制；不删除旧谱系。此版本并未包含实时订单簿、新闻、资金费率、自动下单、独立账户收益证明或自动模型晋升。
