from pathlib import Path


def main():
    p=Path('workbench/index.html');s=p.read_text(encoding='utf-8')
    s=s.replace('价格止损0.30% / 止盈0.60%','硬止损0.30% / 移动盈利保护')
    s=s.replace('<dt>最长持仓</dt><dd>探索5分钟 / 验证15分钟</dd>',
        '<dt>合约持仓</dt><dd>随趋势持有，无五分钟到期</dd>')
    s=s.replace('当前策略尚无盈利证明，实盘未接通。','合约按趋势与风控退出；五分钟仅检验预测。尚无盈利证明，实盘未接通。')
    p.write_text(s,encoding='utf-8')
    p=Path('workbench/app.js');s=p.read_text(encoding='utf-8')
    s=s.replace("const exits={","const exits={CANDLE_REVERSAL:'已收盘K线反转',TRAILING_PROFIT_EXIT:'移动盈利保护',")
    s=s.replace("$('reason').textContent=snapshot.account.halted?",
        "$('reason').textContent=snapshot.account.positions[selected]?'该品种持仓中：随趋势持有；两根已收盘一分钟K线确认反向时退出，保留硬止损及移动盈利保护。五分钟学习标签不会触发平仓。':snapshot.account.halted?")
    s=s.replace("'探索已平 '+(stats.PAPER_EXPLORATION?.closed||0)+' 笔，净收益 '+money(stats.PAPER_EXPLORATION?.net_pnl)",
        "'合约退出：K线反转 / 移动保护 / 风控，不按五分钟到期', '探索已平 '+(stats.PAPER_EXPLORATION?.closed||0)+' 笔，净收益 '+money(stats.PAPER_EXPLORATION?.net_pnl)")
    p.write_text(s,encoding='utf-8')


if __name__=='__main__':main()
