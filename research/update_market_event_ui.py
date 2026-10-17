from pathlib import Path


def main():
    p=Path('workbench/index.html');s=p.read_text(encoding='utf-8')
    s=s.replace('合约按趋势与风控退出；五分钟仅检验预测。',
        '合约结合订单流、流动性与事件风险决策；做市商意图未知。五分钟仅检验预测。')
    s=s.replace('<dt>合约持仓</dt><dd>随趋势持有，无五分钟到期</dd>',
        '<dt>合约持仓</dt><dd>订单流与流动性反转退出</dd>')
    marker='<section class="panel"><div class="section-title"><h2>接下来关注</h2>'
    panel='<section class="panel"><div class="section-title"><h2>全球事件观察</h2><span id="news-coverage" class="small-pill">接入中</span></div><div id="global-news" class="hint"></div><p class="hint">标题尚未核实，不直接赋予涨跌方向。ETF金额、事前一致预期及完整全球覆盖仍缺失。</p></section>'
    if marker not in s:raise ValueError('NEWS_PANEL_TARGET')
    s=s.replace(marker,panel+marker);p.write_text(s,encoding='utf-8')
    p=Path('workbench/app.js');s=p.read_text(encoding='utf-8')
    s=s.replace("const reasons={","const reasons={ORDERFLOW_INCOMPLETE_OR_STALE:'订单流样本不完整、标记价或持仓量过期，暂停新建仓。',GLOBAL_CONTEXT_UNAVAILABLE:'全球消息上下文尚未更新，等待接入。',EVENT_RISK_VETO:'存在临近数据发布或新近高风险消息，暂缓新开仓。',FUNDING_WINDOW_UNRECONCILED:'临近资金费时刻，当前成本模型未覆盖，暂缓开仓。',MECHANISM_NOT_CONFIRMED:'成交方向与流动性证据尚未形成连续确认。',INSUFFICIENT_OBSERVATION:'观察时间不足，继续积累盘口证据。',MECHANISM_EXPLORATION_CANDIDATE:'成交方向与流动性机制连续确认；只允许小额未验证探索。',POSITION_SUPPORTED_OR_REVERSAL_UNCONFIRMED:'持仓方向仍有证据支持，或反向机制尚未连续确认。',OPPOSING_FLOW_LIQUIDITY_CONFIRMED:'相反方向成交和流动性机制已连续确认，准备退出。',")
    s=s.replace("const exits={","const exits={FLOW_LIQUIDITY_REVERSAL:'订单流与流动性反转',")
    s=s.replace('两根已收盘一分钟K线确认反向时退出，保留硬止损及移动盈利保护。',
        '成交方向与盘口消耗/补单连续确认反向时退出，结合事件风险，保留硬止损及移动盈利保护。')
    s=s.replace('合约退出：K线反转 / 移动保护 / 风控，不按五分钟到期',
        '合约退出：订单流/流动性反转、移动保护或风控；不按两根K线决定')
    s=s.replace('renderDecisionDiagnostics();updateControls();}', 'renderDecisionDiagnostics();renderGlobalEvents();updateControls();}')
    s=s.replace("fetch('/api/state',{cache:'no-store'})","fetch('/api/state',{cache:'no-store',headers:{'X-CQWE-UI':'market-event-v1'}})")
    s+='''
function renderGlobalEvents(){
 const context=snapshot?.global_events||{},target=$('global-news');if(!target)return;
 $('news-coverage').textContent=(context.fresh_sources||[]).length+' / '+(context.source_count||8)+' 来源新鲜';
 target.replaceChildren();
 const names={FED:'美联储',SEC:'SEC',BLS:'BLS',ECB:'欧洲央行',BOE:'英国央行',BBC_WORLD:'BBC世界新闻',COINTELEGRAPH:'Cointelegraph',EIA:'EIA'};
 for(const [key,label] of Object.entries(names)){
  const item=context.sources?.[key];target.append(el('div',label+'：'+(!item?'未查询':item.status==='CAPTURED'?'已采集':'暂不可用')));
 }
 const alerts=context.potential_acute_events||[];
 target.append(el('p',alerts.length?'新近潜在风险标题（未确认）：':'未检测到新近急性风险标题；不代表没有全球事件。'));
 for(const item of alerts.slice(0,4))target.append(el('div',item.title));
 const d=snapshot.decisions[selected],diag=$('decision-diagnostics');if(!d||!diag)return;
 const e=d.market_evidence||{},label={LIQUIDITY_CONTINUATION:'流动性延续',POSSIBLE_ABSORPTION:'可能吸收',SAMPLED_LIQUIDATION_CONTINUATION:'抽样强平后延续'};
 diag.append(el('div','主动成交方向：'+(e.flow==null?'未知':e.flow.toFixed(3))+'；消耗/补单：'+(e.depletion??0).toFixed(3)+' / '+(e.refill??0).toFixed(3)));
 diag.append(el('div','标记价/OI：'+(e.mark_fresh?'新鲜':'缺失')+' / '+(e.oi_fresh?'新鲜':'缺失')+'；强平：'+(e.liquidations_available?'抽样已接入':'未知')));
 for(const h of d.mechanism_hypotheses||[])diag.append(el('div',(label[h.id]||h.id)+'：'+(h.direction===1?'上行':'下行')+'证据；连续 '+d.mechanism_confirmations+' 次'));
 diag.append(el('div','做市商身份、意图和完整止损单：不可见。'));
 const models=snapshot.mechanism_learning?.[selected];if(models)diag.append(el('div','树突节点：含事件 / 去成交方向 / 去事件 / 冻结；已成熟 '+(models.scores.market_event?.n||0)+' 个标签'));
}
'''
    p.write_text(s,encoding='utf-8')


if __name__=='__main__':main()
