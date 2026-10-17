"""Update visible paper-policy labels and per-asset decision diagnostics."""
from pathlib import Path


def main():
    path=Path('workbench/index.html');text=path.read_text(encoding='utf-8')
    text=text.replace('这次为什么观望','当前交易判断')
    text=text.replace('<dl><div><dt>自动退出</dt>',
        '<div id="decision-diagnostics" class="hint"></div><dl><div><dt>自动退出</dt>')
    text=text.replace('只有通过验证的信号才允许模拟开仓。',
        '含小额探索模拟，探索交易独立记录，尚未通过盈利验证。')
    text=text.replace('最长持仓</dt><dd>15 分钟','最长持仓</dt><dd>探索5分钟 / 验证15分钟')
    path.write_text(text,encoding='utf-8')
    path=Path('workbench/app.js');text=path.read_text(encoding='utf-8')
    text=text.replace("const reasons={","const reasons={EXPLORATION_WARMUP:'正在积累至少60秒连续盘口观察。',RANGE_BELOW_COST_BUFFER:'近期价格区间不足以超过费用缓冲，暂不探索建仓。',FLAT_OR_WEAK_TREND:'近期方向不明确，保持观望。',EXPLORATION_CADENCE:'该品种仍在探索交易的十分钟间隔内。',EXPLORATION_CANDIDATE:'探索规则出现方向信号；未通过盈利验证，仅使用净值5%的保证金。',")
    text=text.replace('只有通过验证的信号才允许模拟开仓。','以净值5%保证金小额探索，探索盈亏独立记录；尚未证明盈利。')
    text=text.replace('自动观察已启用；没有合格信号时不建仓。','探索模拟已启用；波动、方向、事件和风控条件满足时才模拟建仓。')
    text=text.replace("t.symbol.replace('USDT','')+' / '+(t.direction===1?'多':'空')",
        "t.symbol.replace('USDT','')+' / '+(t.direction===1?'多':'空')+' / '+({MANUAL:'手动',PAPER_EXPLORATION:'探索',AUTOMATIC_QUALIFIED_COUNCIL:'验证策略'}[t.source]||t.source)")
    text=text.replace("renderReason();updateControls();}","renderReason();renderDecisionDiagnostics();updateControls();}")
    text=text.replace('renderMarkets();renderChart();renderReason();','renderMarkets();renderChart();renderReason();renderDecisionDiagnostics();')
    text+='''
function renderDecisionDiagnostics(){
 const d=snapshot?.decisions[selected],v=d?.diagnostics,target=$('decision-diagnostics');
 if(!target)return;target.replaceChildren();
 if(!v){target.textContent='等待本次运行的盘口诊断。';return;}
 const execution={POSITION_ALREADY_OPEN:'已有持仓',NO_ENTRY_AUTHORIZATION:'规则未允许开仓',STALE_DECISION:'决策已过期',STALE_EVENT_CONTEXT:'事件状态过期',EXPLORATION_SINGLE_POSITION_LIMIT:'已有一笔探索持仓',EXPLORATION_CADENCE:'十分钟探索间隔内',PAPER_POSITION_OPENED:'已模拟建仓',ACTION_NOT_ENTRY:'当前动作为观望或事件拦截',RISK_GATE:'风控拦截'};
 const p=d.p_up==null?'—':(d.p_up*100).toFixed(2)+'%';
 const classes=v.classes||{};
 const stats=snapshot.performance_by_source||{};
 for(const line of ['模型上涨分数（未校准）：'+p,
  '验证方向样本：'+v.directional_policy_samples+' / '+v.required_policy_samples,
  '近期区间 / 成本缓冲：'+v.observed_range_bps.toFixed(2)+' / '+v.cost_buffer_bps.toFixed(2)+' bps',
  '五分钟结果：涨 '+(classes.UP||0)+' / 跌 '+(classes.DOWN||0)+' / 成本内横盘 '+(classes.FLAT||0),
  '执行状态：'+(execution[d.execution_status]||actionNames[d.action]||'等待'),
  '探索已平 '+(stats.PAPER_EXPLORATION?.closed||0)+' 笔，净收益 '+money(stats.PAPER_EXPLORATION?.net_pnl)])target.append(el('div',line));
}
'''
    path.write_text(text,encoding='utf-8')


if __name__=='__main__':main()
