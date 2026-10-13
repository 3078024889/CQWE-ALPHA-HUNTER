# CQWE V2.3 — 证据压力复核 / Evidence stress lab

基于 V2.2 已验证的 V2.1 自适应研究证据，逐轮复核四种学习规则的成本敏感性及正向区段分布。

- 不是回测策略晋升器，也不是 $10 统一账户净利润。
- 对每个有事件的区段，把 **额外往返交易成本** 设为 0、5、10、20 bps；假设成本变化只作敏感性推演。
- 从 V2.0 保存的聚合均值与报告下界机械减去新增成本，不宣称重新计算独立置信区间。
- 记录跨连续区段的正信号数量，但不当作独立统计复现（每段模型有在线更新）。
- 任何结果均为 RESEARCH_ONLY_NEEDS_NEW_PROSPECTIVE_DATA，未授权交易。

## Install

双层同名目录：`D:\CQWE_MASTER_V23\CQWE_MASTER_V23`

`powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V23\CQWE_MASTER_V23\INSTALL_MASTER_V23.ps1"`

## Read-only run

`& "C:\Python314\python.exe" -m cqwe.evidence_stress_v23 --store "reports\v21_evidence" --output "reports\v23_cost_stress.json" --extra-cost-bps 0 5 10 20`

结果包含每条规则每段事件数、扣额外成本后的事件均值及报告下界、正向区段数量；没有模拟真实成交，也不会修改原证据存储。
