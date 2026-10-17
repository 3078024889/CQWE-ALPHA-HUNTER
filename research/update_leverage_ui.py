"""Apply explicit UI copy/field changes for the fixed 10x paper configuration."""
from pathlib import Path


def replace(path,changes):
    p=Path(path);text=p.read_text(encoding='utf-8')
    for old,new in changes:
        if old not in text:raise ValueError('UI_TARGET_MISSING: '+old)
        text=text.replace(old,new)
    p.write_text(text,encoding='utf-8')


def main():
    replace('workbench/index.html',[
      ('<span class="pill">模拟交易</span>','<span class="pill">模拟合约 10×</span>'),
      ('持仓 / 总额度','已用保证金 / 额度'),
      ('<strong id="exposure">$0.00 / $5.00</strong>','<strong id="exposure">$0.00 / $5.00</strong><small id="notional-exposure">名义仓位 $0.00 · 10倍</small>'),
      ('<th>模拟金额</th>','<th>保证金 / 名义仓位</th>'),
      ('模拟金额 / USDT','模拟保证金 / USDT'),
      ('<div class="trade-buttons">','<p id="order-preview" class="hint">2 USDT 保证金 × 10倍 = 20 USDT 名义仓位</p><div class="trade-buttons">'),
      ('单币最多净值 25%，总仓位最多 50%。不使用杠杆；模拟数量未核对交易所最小下单量。',
       '固定10倍。单币保证金最多净值25%，总保证金最多50%；手续费按名义仓位计算，尚未核对交易所最小下单量。'),
      ('止损 30 / 止盈 60 bps','价格止损0.30% / 止盈0.60%'),
      ('公共报价模拟不包含真实成交、资金费与交易所数量限制。',
       '全仓模拟；保证金退出按1%假设维持率估算，非币安真实强平。未计资金费及交易所数量限制。')])
    replace('workbench/app.js',[
      ("DRAWDOWN_LIMIT:'回撤限制'","DRAWDOWN_LIMIT:'回撤限制',SIMULATED_MARGIN_EXIT:'模拟保证金不足退出'"),
      ("(p.direction===1?'多':'空'))","(p.direction===1?'多':'空')+' / '+(p.leverage||1)+'倍')"),
      ("el('td',money(p.notional,2))","el('td',money(p.margin||p.notional,2)+' / '+money(p.notional,2))"),
      ("const used=Object.values(a.positions).reduce((sum,p)=>sum+Number(p.notional),0)",
       "const used=Number(snapshot.margin_used||0)"),
      ("$('exposure').textContent=money(used,2)+' / '+money(Number(snapshot.equity)*.5,2);",
       "$('exposure').textContent=money(used,2)+' / '+money(Number(snapshot.equity)*.5,2);$('notional-exposure').textContent='名义仓位 '+money(snapshot.notional_exposure,2)+' · '+(a.leverage||1)+'倍';"),
      ("$('symbol').onchange=updateControls;","$('symbol').onchange=updateControls;$('amount').oninput=updateControls;"),
      ("const manual=mode()==='manual';","const manual=mode()==='manual';$('order-preview').textContent=Number($('amount').value||0).toFixed(2)+' USDT 保证金 × '+(a?.leverage||10)+'倍 = '+(Number($('amount').value||0)*(a?.leverage||10)).toFixed(2)+' USDT 名义仓位';")])


if __name__=='__main__':main()
