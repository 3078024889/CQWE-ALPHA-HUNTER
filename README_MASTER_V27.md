# CQWE V2.7｜依赖收敛与局部变异实验登记

本版不是交易盈利模型升级，而是可审计的实验治理升级。

- 全仓库 AST 静态引用扫描，包括 cqwe 与 tests；区分确实被导入、保护模块、以及“静态未证明被调用”的模块。**静态未引用不等于可安全删除**。
- 真实执行删除模块数量：**0**。原因：缺少对 Windows CLI、动态调用和历史兼容性的完整证明；不谎报已经清理旧模块。
- 逐项登记 V2.6 诊断关联的局部变异研究，冻结问题定义；不得仅靠回看过的30天历史晋升。
- 自动晋升关闭、真实下单关闭、Git远端推送关闭。保留旧证据、报告、行情和 Git 历史。

## Windows

安装路径 `D:\CQWE_MASTER_V27\CQWE_MASTER_V27\INSTALL_MASTER_V27.ps1`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V27\CQWE_MASTER_V27\INSTALL_MASTER_V27.ps1"
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.mutation_governor_v27 --repo . --postmortem reports\v26_dendritic_postmortem.json --output reports\v27_mutation_registry.json
& "C:\Python314\python.exe" -m unittest discover -s tests -q
```

成功标志：`CQWE_V27_LOCAL_VERIFIED`、`CQWE_V27_REGISTRY_PASS`。继续使用真实新行情和更完整的交易约束作为未来变异验收前提。
