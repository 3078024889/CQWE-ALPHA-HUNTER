"""Readable coverage, descriptive impact ranking and held-out node results."""
import collections
import csv
import datetime as dt
import json
from pathlib import Path
import statistics

from cqwe.four_market_runner import checked

NAMES={'US_CPI':'美国CPI','US_PPI':'美国PPI','US_NFP':'官方非农','US_ADP':'ADP就业',
       'US_JOLTS':'JOLTS职位空缺','US_RETAIL':'零售销售','US_PCE':'PCE/收入支出',
       'US_GDP':'GDP各次估计','US_CLAIMS':'初请失业金','US_ECI':'就业成本指数',
       'US_IMPORT_EXPORT':'进出口价格','US_PRODUCTIVITY':'生产率与成本',
       'FED_RATE':'美联储','ECB_RATE':'欧洲央行','BOE_RATE':'英国央行','BOJ_RATE':'日本央行',
       'BOC_RATE':'加拿大央行','RBA_RATE':'澳洲联储','RBNZ_RATE':'新西兰联储','SNB_RATE':'瑞士央行'}


if __name__=='__main__':
    root=Path('D:/CQWE_DATA/event_history_20261016')
    impact=checked(json.loads((root/'impact_report.json').read_text(encoding='utf-8')))
    catalog=json.loads(Path(impact['catalog_snapshot']).read_text(encoding='utf-8'))
    pointer=checked(json.loads((root/'learning_latest.json').read_text(encoding='utf-8')))
    learned=checked(json.loads(Path(pointer['path']).read_text(encoding='utf-8')))
    spike=checked(json.loads((root/'spike_casebook.json').read_text(encoding='utf-8')))
    numbers=json.loads(Path('reports/archived_release_values_20261016.json').read_text(encoding='utf-8'))
    out=Path('reports/event_history_20261016.md')
    text=['# 哥白尼历史事件研究：2024-10-16 至 2026-10-16',
          '',f"已提取{len(catalog['events'])}条事件目录、{len(catalog['counts'])}种类型；完成{impact['complete_market_windows']}个分钟级币种窗口和{impact['daily_responses_count']}个日期级响应。",
          '', '**这是描述性事件窗口研究和历史模型实验，不是已确认的因果效应或可执行盈利。**',
          '', '## 来源与覆盖', '', '| 类型 | 目录事件数 | 时间处理 |','|---|---:|---|']
    for kind,n in catalog['counts'].items():
        kinds={e['time_granularity'] for e in catalog['events'] if e['event_type']==kind}
        text.append(f"| {NAMES.get(kind,kind)} | {n} | {'日期级' if 'DATE_ONLY' in kinds else '分钟级；含标准发布时间与历史日历记录'} |")
    text+=['','CPI/PPI/JOLTS/非农等取自BLS日历；ADP、零售、PCE、GDP及初请取自FRED公开发布日历（美国中部时间）；央行使用各行原始资料。已保留下载原文、公开检索文本及哈希。历史日历并非首次发布的时间版本。',
        '', '部分BLS受2025年政府停摆影响的旧计划日期已排除，再使用FRED发布日历补充延期记录，例如2025-10-24 CPI。全年覆盖并不齐全：部分源只有2025年起的记录。',
        '', f"另查阅CPI/PPI/非农/JOLTS共{numbers['attempted']}条归档记录，保守提取{numbers['extracted']}条数值，包括月率、非农增加岗位或职位空缺水平，未提取项保留缺失。归档材料可能含后续更正，不声称全部是已认证的首次版本。市场一致预期没有可靠历史源，故不计算‘超预期’。数值见`archived_release_values_20261016.json`，尚未输入事前方向模型。",
        '', '## 重点观察排序：BTC公布后15分钟', '',
        '按窗口绝对收益中位数排序，只列至少8个事件的类型。它衡量波动关注度，不代表方向可预测，也未做多重比较校正。公布前窗口可能已有预期交易，因此不是独立对照组。',
        '', '| 类型 | 事件数 | 绝对收益中位数(bps) | 相对公布前窗口变化(bps) | 上涨比例 |', '|---|---:|---:|---:|---:|']
    stats=[s for s in impact['statistics'] if s['symbol']=='BTCUSDT' and s['horizon']==900 and s['events']>=8]
    for s in sorted(stats,key=lambda s:s['median_abs_return_bps'],reverse=True):
        delta=s['median_abs_change_vs_pre_bps']
        text.append(f"| {NAMES.get(s['event_type'],s['event_type'])} | {s['events']} | {s['median_abs_return_bps']:.2f} | {delta:.2f} | {s['up_fraction']:.1%} |")
    text+=['','## 历史树突节点学习', '',
        f"同一时刻的多条消息先归组，按{learned['groups']}个事件时刻依时间切分60%训练、20%验证、20%冻结留出。比较固定0.5、全局频率、事件类型频率和四分支16维树突节点。标签成熟后才能更新；验证与留出不更新参数。验证阶段选择节点，再评估留出。",
        '', '特征包含事件类型、UTC时段、星期和公布前价格变化，不含公布后收益、未来标签或事后补填的市场预期。这是回顾性按时间模拟，尚不是前向实时交易验证。',
        '', '| 品种与期限 | 验证选中节点 | 留出数 | 选中Brier | 固定0.5 Brier |', '|---|---|---:|---:|---:|']
    for key,kind in learned['chosen_from_validation'].items():
        s=learned['scores'][key]['holdout'][kind];base=learned['scores'][key]['holdout']['frozen'];n=s['n']
        if n:text.append(f"| {key} | {kind} | {n} | {s['brier_sum']/n:.5f} | {base['brier_sum']/base['n']:.5f} |")
    text+=['','Brier越低表示概率误差越小。没有真实成交、手续费/滑点/资金费对账、修订前宏观数据库或独立多期验证，因此没有自动晋级为交易策略。',
        '', '## 插针样本', '',
        f"已提取{spike['count']}条至少20bps影线的分钟样本并按币种和时间去重，范围仅限本次已采集事件窗口。记录影线、成交量、成交笔数、与日历的时间差。历史盘口、完整强平、跨所比较和消息确认不足，原因统一保留未确定；不会把每根影线解释成做市商扫损。",
        '', '## 未覆盖事项', '',
        '- ISM/PMI、消费者信心、更多国家经济数据、其他央行及更完整会议议程仍需来源适配。',
        '- 政治讲话、战争、ETF申赎和黑客事件的两年全量历史尚未取得，不能声称所有全球事件样本已齐。',
        '- 日期级会议/部分央行结果是当地日期的24小时变化，不是精确宣布后的5分钟效果。',
        '- 计划/标准公布时间窗口与已经逐条确认实际公布时间的窗口必须继续核对。',
        '', f"原始证据目录：`{root}`。完整四币统计见`impact_statistics_20261016.csv`。无实盘订单，无盈利证明。"]
    out.write_text('\n'.join(text)+'\n',encoding='utf-8')
    target=Path('reports/impact_statistics_20261016.csv')
    with target.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(impact['statistics'][0]));writer.writeheader();writer.writerows(impact['statistics'])
    print(json.dumps({'report':str(out),'csv':str(target),'top_btc_15m':sorted(stats,key=lambda s:s['median_abs_return_bps'],reverse=True)[:5]},ensure_ascii=False))
