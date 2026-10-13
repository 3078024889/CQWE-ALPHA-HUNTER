# CQWE V2.9 — 官方只读行情采集与冻结前向实验输入门禁

本轮修复 V2.8 缺少 `data/future/*.json` 导致的运行阻塞。只使用 Binance 官方提供的无需API Key的 `https://data-api.binance.vision/api/v3/klines`，5分钟现货K线，BTC/ETH/SOL/BNB，限制为已收盘K线；不接入交易账号、API密钥、订单、杠杆或任何付费服务。

官网文档： https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md

## 安装
解压整个ZIP到 `D:\CQWE_MASTER_V29`，应出现 `D:\CQWE_MASTER_V29\CQWE_MASTER_V29\INSTALL_MASTER_V29.ps1`，然后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\CQWE_MASTER_V29\CQWE_MASTER_V29\INSTALL_MASTER_V29.ps1"
```

## 采集（可以每天重复，增量追加；每次都先验证V2.1检查点）

```powershell
cd D:\CQWE\alpha-hunter
& "C:\Python314\python.exe" -m cqwe.public_data_v29 --store "reports\v21_evidence" --output-dir "data\future"
```

`forward_ready=false` 时请等待下次采集，不能补造历史。`forward_ready=true` 时可执行 V2.8 原有的 `-m cqwe.forward_experiment_v28` 命令，输入是 `data\future\[SYMBOL]_5m.json` 四个文件。

官方接口可能因位置、网络或访问政策不可用；报错时不应使用绕过地域限制的办法。数据尚未取到不能宣称前向实验成功。

注意：V2.8只校验市场集合/时间先后/源哈希，不证明数据统计独立性，也不证明真实成交。严禁将前向模拟收益计为真实收入。V2.9没有删除可能仍被CLI或历史证据依赖的模块。
