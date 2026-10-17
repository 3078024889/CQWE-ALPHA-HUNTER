"""Loopback-only paper trading workbench. No private exchange endpoints or keys."""
import argparse
import copy
from decimal import Decimal as D
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import webbrowser

from .copernican_experiment_v81_v85 import digest
from .event_forward_loop import capture,ForwardLoop
from .event_council_bridge import combine
from .four_market_core import SYMBOLS
from .four_market_runner import checked
from .historical_curriculum import public
from .local_autopilot import exclusive
from .paper_observer_v2 import PaperObserver
from .mechanism_exit import evaluate as mechanism_exit,POLICY as EXIT_POLICY
from .market_evidence import MarketEvidence
from .copernican_market_policy import MarketCouncil
from .global_event_context import GlobalContext
from .liquidation_watch import LiquidationWatch
from .market_context import ContextCache
from .portfolio_router import PortfolioRouter
from .strategy_research_loop import ResearchLoop
from .unified_dendritic_paper import UnifiedCouncil,POLICY as UNIFIED_POLICY

BASE=Path(__file__).resolve().parent.parent


def now_ms():return time.time_ns()//1000000


class PaperDesk:
    def __init__(self,path,leverage=10):
        if type(leverage) is not int or leverage not in (1,10):raise ValueError('模拟杠杆仅支持1倍或10倍')
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,hash TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,result TEXT NOT NULL)')
        row=self.db.execute('SELECT payload,hash FROM state WHERE id=1').fetchone()
        if row:
            if hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:raise ValueError('模拟账户存档校验失败')
            self.state=json.loads(row[0])
        else:
            self.state={'initial':'10','cash':'10','peak':'10','positions':{},'trades':[],
                        'fees':'0','halted':False,'automatic':False,'running':False,'leverage':leverage,
                        'stage_started_ms':now_ms()}
            self.save()
        old_leverage=self.state.get('leverage',1)
        if old_leverage!=leverage:
            if self.state['positions']:
                self.db.close()
                raise ValueError('现有持仓必须按原杠杆退出后才能切换')
            self.state.setdefault('stage_history',[]).append({'ended_ms':now_ms(),'leverage':old_leverage,
                'cash':self.state['cash'],'fees':self.state['fees'],'trades':len(self.state['trades'])})
            self.state['stage_started_ms']=now_ms()
        self.state['leverage']=leverage
        self.state['margin_model']='CROSS_PAPER_PROXY'
        self.state['maintenance_rate_assumption']='0.01'
        # Restart never resumes opening positions without the user's Start action.
        self.state.update(running=False,automatic=False)
        self.state.setdefault('cooldown_until',{});self.save();self.db.commit()

    def save(self):
        blob=json.dumps(self.state,sort_keys=True,ensure_ascii=False,allow_nan=False)
        self.db.execute('INSERT OR REPLACE INTO state VALUES(1,?,?)',(blob,hashlib.sha256(blob.encode()).hexdigest()))

    @staticmethod
    def price(quote,at):
        if not quote or not 0<=at-quote['observed_ms']<=10000:raise ValueError('行情已过期，等待最新报价后再操作')
        bid,ask=D(str(quote['bid'])),D(str(quote['ask']))
        if not bid.is_finite() or not ask.is_finite() or not 0<bid<=ask:raise ValueError('报价无效')
        return bid,ask

    def equity(self,quotes):
        equity=D(self.state['cash'])
        for s,p in self.state['positions'].items():
            q=quotes.get(s)
            px=D(str(q['bid' if p['direction']==1 else 'ask'])) if q else D(p['entry'])
            equity+=D(p['direction'])*D(p['quantity'])*(px-D(p['entry']))
        return equity

    def open(self,symbol,direction,amount,quotes,at,source,reversal=False):
        if symbol not in SYMBOLS or type(direction) is not int or direction not in (-1,1):raise ValueError('请选择有效品种和方向')
        if not self.state['running']:raise ValueError('请先启动工作台')
        if self.state['halted']:raise ValueError('账户达到模拟回撤上限，已停止开仓')
        if symbol in self.state['positions']:raise ValueError('该品种已有持仓，请先平仓')
        if source not in ('MANUAL','PAPER_DENDRITIC_ENSEMBLE') and not reversal and at<self.state['cooldown_until'].get(symbol,0):raise ValueError('平仓后等待五分钟再评估')
        amount=D(str(amount))
        if not amount.is_finite() or amount<=0:raise ValueError('请输入大于零的模拟金额')
        bid,ask=self.price(quotes.get(symbol),at)
        equity=self.equity(quotes)
        reserved=sum((D(p.get('margin',p['notional'])) for p in self.state['positions'].values()),D(0))
        if amount>equity*D('.25') or amount+reserved>equity*D('.5'):raise ValueError('超过保证金额度：单币最多净值25%，总保证金最多50%')
        leverage=self.state['leverage'];notional=amount*leverage
        entry=(ask*(1+D('.0002'))) if direction==1 else bid*(1-D('.0002'))
        quantity=notional/entry;fee=notional*D('.0005')
        if amount+reserved+fee>equity:raise ValueError('可用保证金不足以覆盖开仓费用')
        self.state['cash']=str(D(self.state['cash'])-fee);self.state['fees']=str(D(self.state['fees'])+fee)
        p={'symbol':symbol,'direction':direction,'quantity':str(quantity),'entry':str(entry),
           'notional':str(notional),'margin':str(amount),'leverage':leverage,
           'entry_fee':str(fee),'opened_ms':at,'expires_ms':None,'source':source,'exit_policy':EXIT_POLICY}
        self.state['positions'][symbol]=p
        return {'message':'已模拟建仓','position':copy.deepcopy(p)}

    def close(self,symbol,quotes,at,reason):
        if symbol not in self.state['positions']:raise ValueError('该品种没有持仓')
        p=self.state['positions'][symbol];bid,ask=self.price(quotes.get(symbol),at)
        exit_price=bid*(1-D('.0002')) if p['direction']==1 else ask*(1+D('.0002'))
        quantity=D(p['quantity']);fee=quantity*exit_price*D('.0005')
        gross=D(p['direction'])*quantity*(exit_price-D(p['entry']))
        self.state['cash']=str(D(self.state['cash'])+gross-fee);self.state['fees']=str(D(self.state['fees'])+fee)
        trade={**p,'closed_ms':at,'exit':str(exit_price),'exit_fee':str(fee),
               'net_pnl':str(gross-fee-D(p['entry_fee'])),'reason':reason}
        self.state['trades']=(self.state['trades']+[trade])[-500:]
        del self.state['positions'][symbol]
        self.state['cooldown_until'][symbol]=at+300000
        return {'message':'已模拟平仓','trade':trade}

    def action(self,request,quotes,at):
        ident=request.get('request_id')
        if not isinstance(ident,str) or not 8<=len(ident)<=80:raise ValueError('请求标识无效')
        existing=self.db.execute('SELECT result FROM actions WHERE id=?',(ident,)).fetchone()
        if existing:return json.loads(existing[0])
        before=copy.deepcopy(self.state)
        try:
            with self.db:
                kind=request.get('action')
                if kind=='start':
                    if self.state['halted']:raise ValueError('已达到回撤上限，账户保持停止开仓')
                    policy=request.get('policy',self.state.get('active_policy','LEGACY'))
                    if policy not in ('LEGACY',UNIFIED_POLICY):raise ValueError('未知模拟策略')
                    if policy!=self.state.get('active_policy','LEGACY') and self.state['positions']:raise ValueError('切换模拟策略前须先处理已有持仓')
                    self.state['active_policy']=policy
                    if policy==UNIFIED_POLICY and 'ensemble_stage' not in self.state:
                        self.state['ensemble_stage']={'started_ms':at,'initial_equity':str(self.equity(quotes)),
                            'initial_fees':self.state['fees'],'prior_trade_count':len(self.state['trades']),
                            'policy':UNIFIED_POLICY,'profitability_proven':False}
                    self.state.update(running=True,automatic=request.get('mode')=='automatic',observation_enabled=True)
                    result={'message':'已启动自动模拟，等待合格信号' if self.state['automatic'] else '已启动手动模拟'}
                elif kind=='pause':
                    self.state.update(running=False,automatic=False,observation_enabled=True)
                    result={'message':'已暂停开仓；继续观察学习，已有持仓继续监测风控'}
                elif kind=='disable_family':
                    family=request.get('family')
                    if family not in ('vol_rsi','ts_momentum','residual_pair','cross_momentum'):raise ValueError('未知策略族')
                    disabled=self.state.setdefault('disabled_strategy_families',[])
                    if family not in disabled:disabled.append(family)
                    result={'message':'已停用该策略族的新组合贡献；保留研究对照与持仓风控'}
                elif kind=='open':
                    if self.state['automatic']:raise ValueError('请切换为手动模式后操作')
                    result=self.open(request.get('symbol'),request.get('direction'),request.get('amount'),quotes,at,'MANUAL')
                elif kind=='close':
                    if request.get('symbol') in self.state.get('ensemble_position',{}).get('members',[]):
                        self.close_ensemble(quotes,at,'MANUAL_GROUP_CLOSE');result={'message':'已模拟平仓整个组合，保留对冲腿一致性'}
                    else:result=self.close(request.get('symbol'),quotes,at,'MANUAL_CLOSE')
                elif kind=='close_all':
                    for symbol in self.state['positions']:self.price(quotes.get(symbol),at)
                    initial_count=len(self.state['positions'])
                    if self.state.get('ensemble_position'):self.close_ensemble(quotes,at,'MANUAL_CLOSE_ALL')
                    results=[self.close(s,quotes,at,'MANUAL_CLOSE_ALL') for s in list(self.state['positions'])]
                    self.state.pop('ensemble_position',None)
                    self.state.update(running=False,automatic=False)
                    result={'message':f'已模拟平仓 {initial_count} 笔','results':results}
                else:raise ValueError('不支持的操作')
                self.save();self.db.execute('INSERT INTO actions VALUES(?,?)',(ident,json.dumps(result,ensure_ascii=False)))
            return result
        except Exception:
            self.state=before;raise

    def close_ensemble(self,quotes,at,reason):
        group=self.state.get('ensemble_position')
        if not group:return
        members=[s for s in group['members'] if s in self.state['positions']]
        for s in members:self.price(quotes.get(s),at)
        closed=[self.close(s,quotes,at,reason)['trade'] for s in members]
        self.state.setdefault('ensemble_groups',[]).append({'id':group['id'],'opened_ms':group['opened_ms'],'closed_ms':at,
            'reason':reason,'net_pnl':str(sum((D(t['net_pnl']) for t in closed),D(0))),'legs':len(closed)})
        self.state['ensemble_groups']=self.state['ensemble_groups'][-200:]
        self.state.pop('ensemble_position',None);self.state['ensemble_cooldown_until']=at+90000

    def unified_cycle(self,quotes,plan,at,margin_exit):
        self.state['ensemble_execution_status']='WAITING_FOR_ENSEMBLE'
        group=self.state.get('ensemble_position')
        fresh_plan=plan and plan.get('policy')==UNIFIED_POLICY and 0<=at-plan.get('at_ms',0)<=10000
        if group:
            members=[s for s in group['members'] if s in self.state['positions']]
            try:
                prices={s:self.price(quotes.get(s),at) for s in members}
            except ValueError:
                self.state['ensemble_execution_status']='GROUP_QUOTES_STALE';return
            risks=[mechanism_exit(self.state['positions'][s],*prices[s],at,None) for s in members]
            reason=('SIMULATED_MARGIN_EXIT' if margin_exit else 'DRAWDOWN_LIMIT' if self.state['halted'] else
                    next((r for r in risks if r),None))
            if not reason and fresh_plan and plan.get('action')=='CLOSE_BASKET':reason='ENSEMBLE_DIRECTION_CHANGED'
            if reason:
                self.close_ensemble(quotes,at,reason);self.state['ensemble_execution_status']='GROUP_CLOSED_REASSESS'
            else:self.state['ensemble_execution_status']='GROUP_HOLD'
            return
        # Existing manual positions keep their original risk protection.
        if self.state['positions']:
            for s,p in list(self.state['positions'].items()):
                try:bid,ask=self.price(quotes.get(s),at)
                except ValueError:continue
                reason='DRAWDOWN_LIMIT' if self.state['halted'] else mechanism_exit(p,bid,ask,at,None)
                if reason:self.close(s,quotes,at,reason)
            self.state['ensemble_execution_status']='MANUAL_POSITIONS_PRESENT';return
        if not self.state['running'] or not self.state['automatic'] or self.state['halted']:return
        if at<self.state.get('ensemble_cooldown_until',0):self.state['ensemble_execution_status']='GROUP_COOLDOWN';return
        if not fresh_plan or plan.get('action')!='OPEN_BASKET':return
        if plan.get('paper_only') is not True or plan.get('real_orders_enabled') is not False or plan.get('active_families',0)<2:return
        weights=plan.get('weights',{});gross=sum(abs(float(w)) for w in weights.values())
        if not weights or not math.isfinite(gross) or not .05<=gross<=1.0000001:raise ValueError('INVALID_ENSEMBLE_EXPOSURE')
        for s in weights:self.price(quotes.get(s),at)
        capital=self.equity(quotes);ident='ensemble-'+str(at);before=copy.deepcopy(self.state)
        try:
            for s,w in weights.items():
                self.open(s,1 if w>0 else -1,str(capital*D('.05')*D(str(abs(w)))),quotes,at,'PAPER_DENDRITIC_ENSEMBLE')
                self.state['positions'][s].update(group_id=ident,strategy_id=UNIFIED_POLICY,
                    entry_evidence={'families':plan['families'],'experts':plan['experts'],'neural':plan['neural'],'weights':weights})
            self.state['ensemble_position']={'id':ident,'opened_ms':at,'members':list(weights),'weights':weights,
                                               'margin_budget_fraction':.05,'leverage':self.state['leverage']}
            self.state['ensemble_execution_status']='GROUP_OPENED'
        except (ValueError,KeyError,ArithmeticError):
            self.state=before;self.state['ensemble_execution_status']='GROUP_OPEN_REJECTED_ATOMICALLY'

    def cycle(self,quotes,decisions,at,candles=None,ensemble=None):
        before=copy.deepcopy(self.state)
        try:
            with self.db:
                equity=self.equity(quotes);peak=max(D(self.state['peak']),equity)
                self.state['peak']=str(peak)
                maintenance=D(0)
                for s,p in self.state['positions'].items():
                    q=quotes.get(s)
                    px=D(str((q['bid']+q['ask'])/2)) if q else D(p['entry'])
                    maintenance+=D(p['quantity'])*px*(D(self.state['maintenance_rate_assumption'])+D('.0007'))
                margin_exit=bool(self.state['positions']) and equity<=maintenance
                if equity<=peak*D('.9') or margin_exit:self.state.update(halted=True,running=False,automatic=False)
                if self.state.get('active_policy')==UNIFIED_POLICY:
                    self.unified_cycle(quotes,ensemble,at,margin_exit);self.save();return
                for symbol,p in list(self.state['positions'].items()):
                    try:bid,ask=self.price(quotes.get(symbol),at)
                    except ValueError:continue
                    reason=('SIMULATED_MARGIN_EXIT' if margin_exit else 'DRAWDOWN_LIMIT' if self.state['halted'] else
                            mechanism_exit(p,bid,ask,at,decisions.get(symbol)))
                    if reason:self.close(symbol,quotes,at,reason)
                if self.state['running'] and self.state['automatic'] and not self.state['halted']:
                    # A position exit invalidates this frame's entry comparisons.
                    closed_this_frame=len(self.state['trades'])>len(before['trades'])
                    ordered=sorted(decisions.items(),key=lambda item:(item[1].get('portfolio_route',{}).get('rank',999),item[0]))
                    for symbol,decision in ordered:
                        qualified=any(n.get('eligible') is True and n.get('weight',0)>0 for n in decision.get('nodes',[]))
                        exploration=(decision.get('exploration_allowed') is True and decision.get('paper_only') is True
                                     and decision.get('execution_enabled') is False)
                        blocked=('EXIT_FRAME_REASSESS' if closed_this_frame else
                                 'POSITION_ALREADY_OPEN' if symbol in self.state['positions'] else
                                 'NO_ENTRY_AUTHORIZATION' if not (qualified or exploration) else
                                 'STALE_DECISION' if not 0<=at-decision.get('at_ms',0)<=10000 else
                                 'STALE_EVENT_CONTEXT' if decision.get('event_context_fresh') is not True else None)
                        if blocked:
                            decision['execution_status']=blocked;continue
                        direction={'OPEN_LONG':1,'OPEN_SHORT':-1}.get(decision.get('action'))
                        if not direction:decision['execution_status']='ACTION_NOT_ENTRY'
                        if direction:
                            try:
                                fraction=D('.05') if exploration and not qualified else D('.2')
                                source='PAPER_EXPLORATION' if exploration and not qualified else 'AUTOMATIC_QUALIFIED_COUNCIL'
                                route=decision.get('portfolio_route',{})
                                # Only the internal, fresh router may shorten a cooldown, never the UI.
                                last=max((t for t in self.state['trades'] if t['symbol']==symbol),key=lambda t:t['closed_ms'],default=None)
                                reversal=bool(route.get('reverse_after_close') is True and route.get('rank')==1
                                    and route.get('signal_duration_ms',0)>=90000 and route.get('regime_direction')==direction
                                    and last and last.get('reason')=='FLOW_LIQUIDITY_REVERSAL' and last['direction']==-direction
                                    and 90000<=at-last['closed_ms']<300000)
                                if source=='PAPER_EXPLORATION':
                                    if sum(p['source']=='PAPER_EXPLORATION' for p in self.state['positions'].values())>=1:
                                        decision['execution_status']='EXPLORATION_SINGLE_POSITION_LIMIT';continue
                                    if not reversal and at-self.state.setdefault('last_exploration',{}).get(symbol,-600000)<600000:
                                        decision['execution_status']='EXPLORATION_CADENCE';continue
                                self.open(symbol,direction,str(self.equity(quotes)*fraction),quotes,at,source,reversal=reversal)
                                self.state['positions'][symbol]['strategy_id']=decision.get('policy','LEGACY_PAPER_POLICY')
                                self.state['positions'][symbol]['entry_evidence']={
                                    'at_ms':at,'hypotheses':decision.get('mechanism_hypotheses',[]),
                                    'market':decision.get('market_evidence',{}),
                                    'event_risk':decision.get('global_event_context',{}),
                                    'portfolio_route':route,'market_background':decision.get('market_background',{}),
                                    'model_scores':decision.get('nodes',[])}
                                decision['execution_status']='PAPER_POSITION_OPENED'
                                if source=='PAPER_EXPLORATION':
                                    self.state['last_exploration'][symbol]=at
                            except ValueError as exc:
                                decision['execution_status']='RISK_GATE';decision['execution_detail']=str(exc)
                self.save()
        except Exception:
            self.state=before;raise


class Workbench:
    def __init__(self,root,book_state=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.desk=PaperDesk(self.root/'paper.sqlite3')
        self.stop=threading.Event();self.thread=None;self.book_state=book_state
        self.quotes={};self.history={s:[] for s in SYMBOLS};self.decisions={}
        self.errors=[];self.event_status={};self.learning={};self.last_cycle=None
        self.news=GlobalContext(self.root/'global_news');self.liquidations=LiquidationWatch()
        self.current_evidence={};self.global_events={}
        self.research_status={};self.strategy_catalog={}
        self.ensemble_plan={}
        catalog=BASE/'reports/strategy_research_registry_20261016.json'
        if catalog.exists():self.strategy_catalog=json.loads(catalog.read_text(encoding='utf-8'))
        cards=BASE/'reports/unified_candidate_cards_20261016.json'
        if cards.exists():self.strategy_catalog['candidate_cards']=json.loads(cards.read_text(encoding='utf-8'))['candidates']
        path=BASE/'reports/macro_watch_plan_expanded_20261016.json'
        self.events=checked(json.loads(path.read_text(encoding='utf-8')))['events']
        report=BASE/'reports/event_forward_validation_20261016.json'
        if report.exists():self.learning=checked(json.loads(report.read_text(encoding='utf-8')))
        if self.desk.state['positions'] or self.desk.state.get('observation_enabled'):self.ensure_worker()

    def ensure_worker(self):
        if not self.thread or not self.thread.is_alive():
            self.news.start();self.liquidations.start()
            self.thread=threading.Thread(target=self.worker,name='CQWE-paper-observer',daemon=True);self.thread.start()

    def worker(self):
        loop=None;research=None;histories={};last_history=0;market=MarketEvidence();background=ContextCache(public);context_cursor=0
        try:
            loop=ForwardLoop(self.root/'events.sqlite3')
            research=ResearchLoop(self.root/'strategy_shadow_v1.sqlite3',public,self.strategy_catalog.get('candidates',[]))
            with self.lock:
                observer=PaperObserver(self.desk.state.get('observer'))
                council=MarketCouncil(self.desk.state.get('market_council'))
                router=PortfolioRouter(self.desk.state.get('portfolio_router'))
                unified=UnifiedCouncil(self.desk.state.get('unified_council'))
            while not self.stop.is_set():
                with self.lock:active=self.desk.state['running'] or self.desk.state.get('observation_enabled') or bool(self.desk.state['positions'])
                if not active:self.stop.wait(1);continue
                research.refresh_one(now_ms())
                # At most one slow history request per cycle; cache the rest.
                refresh_symbol=SYMBOLS[context_cursor%len(SYMBOLS)];context_cursor+=1
                contexts={s:background.get(s,now_ms(),refresh=s==refresh_symbol) for s in SYMBOLS}
                quotes={};errors=[];at=now_ms();batches={}
                event_active=any(0<=at-e['scheduled_ms']<=60000 for e in self.events)
                for symbol in SYMBOLS:
                    if self.stop.is_set():break
                    try:
                        quotes[symbol]=capture(symbol)
                        try:batches[symbol]=market.capture(symbol,quotes[symbol],self.liquidations.snapshot(symbol,now_ms()))
                        except Exception as exc:errors.append(symbol+' 订单流: '+str(exc))
                        if event_active and at-last_history>=30000:
                            raw=public('klines',{'symbol':symbol,'interval':'1m','limit':62})
                            histories[symbol]=[{'time':r[0],'open':r[1],'close':r[4]} for r in raw if r[6]<at]
                    except Exception as exc:errors.append(symbol+': '+str(exc))
                if event_active:last_history=at
                at=now_ms();event_status=loop.tick(at,self.events,quotes,histories)
                global_events=self.news.snapshot(at)
                research_status=research.tick(quotes,at)
                decisions={s:{'symbol':s,'at_ms':at,'action':'OBSERVE','reason':'NO_QUALIFIED_SIGNAL',
                              'nodes':[],'p_up':None,'execution_enabled':False} for s in SYMBOLS}
                for s,q in quotes.items():
                    decision=observer.frame(s,q,at)
                    if decision:
                        try:evidence=market.frame(s,q,batches.get(s),at)
                        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
                            errors.append(s+' 证据已隔离: '+str(exc))
                            evidence={'at_ms':at,'ready':False,'reason':'REJECTED_MARKET_CONTEXT','features':[0.]*8}
                        self.current_evidence[s]=evidence
                        with self.lock:position=copy.deepcopy(self.desk.state['positions'].get(s))
                        decision=council.decide(s,q,decision,evidence,global_events,event_status,at,position)
                        decisions[s]=combine(decision,event_status,at)
                with self.lock:decisions=router.route(decisions,contexts,copy.deepcopy(self.desk.state),at)
                with self.lock:current_positions=copy.deepcopy(self.desk.state['positions'])
                with self.lock:disabled=self.desk.state.get('disabled_strategy_families',[]).copy()
                ensemble_targets=copy.deepcopy(research.targets)
                if ensemble_targets:
                    for key in ensemble_targets:
                        if key.split(':',1)[0] in disabled:ensemble_targets[key]={}
                ensemble=unified.decide(ensemble_targets,research.last_proposed,quotes,self.current_evidence,
                                        global_events,event_status,at,current_positions)
                ensemble['disabled_families']=disabled
                if self.book_state:
                    try:
                        path=Path(self.book_state)
                        if path.stat().st_size>10000000:raise ValueError('盘口状态过大')
                        book=checked(json.loads(path.read_text(encoding='utf-8')))
                        # External councils are retained as comparison, never bypass integrated event/flow gates.
                        for s,d in book.get('engine',book).get('council',{}).items():
                            if s in decisions:decisions[s]['external_shadow_council']=d
                    except Exception as exc:errors.append('盘口策略状态: '+str(exc))
                with self.lock:
                    self.quotes.update(quotes);self.decisions=decisions;self.event_status=event_status
                    self.errors=errors;self.last_cycle=at;self.global_events=global_events
                    self.research_status=research_status
                    self.ensemble_plan=ensemble
                    for s,q in quotes.items():self.history[s]=(self.history[s]+[{'t':q['observed_ms'],'p':(q['bid']+q['ask'])/2}])[-180:]
                    self.desk.state['observer']=copy.deepcopy(observer.state)
                    self.desk.state['market_council']=copy.deepcopy(council.state)
                    self.desk.state['portfolio_router']=copy.deepcopy(router.state)
                    self.desk.state['unified_council']=copy.deepcopy(unified.state)
                    self.desk.cycle(self.quotes,decisions,at,ensemble=ensemble)
                    for s,t in self.desk.state.get('last_exploration',{}).items():
                        if s in observer.state['banks']:observer.state['banks'][s]['last_exploration_ms']=t
                self.stop.wait(5)
        except Exception as exc:
            with self.lock:
                self.errors=['观察进程已停止: '+str(exc)]
                self.desk.state.update(running=False,automatic=False)
                with self.desk.db:self.desk.save()
        finally:
            if loop:loop.close()
            if research:research.close()

    def action(self,request):
        with self.lock:result=self.desk.action(request,self.quotes,now_ms())
        self.ensure_worker()
        return result

    def snapshot(self):
        with self.lock:
            state=copy.deepcopy(self.desk.state);at=now_ms();equity=self.desk.equity(self.quotes)
            observer=state.pop('observer',{})
            council=state.pop('market_council',{})
            state.pop('portfolio_router',None)
            state.pop('unified_council',None)
            margin=sum((D(p.get('margin',p['notional'])) for p in state['positions'].values()),D(0))
            notional=sum((D(p['notional']) for p in state['positions'].values()),D(0))
            return {'mode':'PUBLIC_DATA_PAPER_ONLY','real_orders':0,'profitability_proven':False,
                    'ui_version':'unified-dendritic-paper-v1',
                    'futures_exit_policy':EXIT_POLICY,'prediction_horizon_seconds':300,
                    'paper_execution_policy':'UNVALIDATED_DENDRITIC_ENSEMBLE_EXPERIMENT' if state.get('active_policy')==UNIFIED_POLICY else 'EXPLORATION_AND_VALIDATED_SEPARATELY',
                    'performance_by_source':{source:{'closed':sum(t['source']==source for t in state['trades']),
                        'net_pnl':str(sum((D(t['net_pnl']) for t in state['trades'] if t['source']==source),D(0)))}
                        for source in ('MANUAL','PAPER_EXPLORATION','AUTOMATIC_QUALIFIED_COUNCIL','PAPER_DENDRITIC_ENSEMBLE')},
                    'margin_used':str(margin),'notional_exposure':str(notional),
                    'available_margin':str(equity-margin),
                    'at_ms':at,'last_cycle_ms':self.last_cycle,'account':state,'equity':str(equity),
                    'net_pnl':str(equity-D(state['initial'])),'quotes':copy.deepcopy(self.quotes),
                    'history':copy.deepcopy(self.history),'decisions':copy.deepcopy(self.decisions),
                    'errors':self.errors.copy(),'events':sorted([e for e in self.events if e['scheduled_ms']>=at],key=lambda e:e['scheduled_ms'])[:6],
                    'event_counts':self.event_status.get('counts',{}),
                    'book_labels':{s:b['n'] for s,b in observer.get('banks',{}).items()},
                    'mechanism_learning':{s:{'scores':b['scores'],'updates':{k:m['updates'] for k,m in b['models'].items()}}
                                          for s,b in council.get('banks',{}).items()},
                    'global_events':copy.deepcopy(self.global_events),
                    'strategy_research':copy.deepcopy(self.research_status),
                    'strategy_catalog':copy.deepcopy(self.strategy_catalog),
                    'unified_ensemble':copy.deepcopy(self.ensemble_plan),
                    'global_data_coverage_complete':False,
                    'learning':{k:self.learning.get(k) for k in ('calendar_entries','event_types','asset_windows','historical_groups','tests','model_archives')},
                    'worker_running':bool(self.thread and self.thread.is_alive()),
                    'funding_modelled':False,'exchange_minimums_validated':False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def send(self,status,data,kind='application/json; charset=utf-8'):
        raw=data.encode('utf-8') if isinstance(data,str) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(raw)

    def host_valid(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.host_valid() or self.headers.get('Sec-Fetch-Site')=='cross-site':self.send(403,{'error':'仅允许本机访问'});return
        if self.path=='/api/state':self.send(200,self.server.app.snapshot())
        elif self.path=='/favicon.ico':self.send(204,'','image/x-icon')
        elif self.path=='/bootstrap.js':self.send(200,'window.CQWE_TOKEN='+json.dumps(self.server.token)+';','text/javascript; charset=utf-8')
        elif self.path in ('/','/app.js','/style.css'):
            name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[self.path]
            kind={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[self.path]
            self.send(200,(BASE/'workbench'/name).read_text(encoding='utf-8'),kind)
        else:self.send(404,{'error':'页面不存在'})

    def do_POST(self):
        self.connection.settimeout(5)
        origin=self.headers.get('Origin')
        valid_origin=origin in (None,f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        if not self.host_valid() or not valid_origin or not secrets.compare_digest(self.headers.get('X-CQWE-Token',''),self.server.token):
            self.send(403,{'error':'本机操作校验失败，请重新打开页面'});return
        if self.path!='/api/action':self.send(404,{'error':'接口不存在'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096:
                if 0<length<=65536:self.rfile.read(length)
                raise ValueError('请求超过允许大小')
            raw=self.rfile.read(length)
            if self.headers.get('Content-Type')!='application/json':raise ValueError('请求格式无效')
            request=json.loads(raw)
            if not isinstance(request,dict):raise ValueError('请求格式无效')
            self.send(200,self.server.app.action(request))
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:self.send(400,{'error':str(exc)})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8765)
    p.add_argument('--root',default='D:/CQWE_DATA/workbench_v1');p.add_argument('--book-state');p.add_argument('--open',action='store_true')
    p.add_argument('--background-log',action='store_true')
    a=p.parse_args();root=Path(a.root);root.mkdir(parents=True,exist_ok=True)
    if a.background_log:
        import sys
        sys.stdout=sys.stderr=(root/'server.log').open('a',encoding='utf-8',buffering=1)
    with exclusive(root):
        app=Workbench(root,a.book_state)
        server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.app=app;server.token=secrets.token_urlsafe(32)
        if __import__('os').name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x4000)
        print(f'哥白尼模拟工作台 http://127.0.0.1:{a.port} | Ctrl+C 关闭',flush=True)
        if a.open:webbrowser.open(f'http://127.0.0.1:{a.port}')
        try:server.serve_forever(poll_interval=.5)
        except KeyboardInterrupt:pass
        finally:
            app.stop.set()
            app.news.stop.set();app.liquidations.close()
            if app.thread:app.thread.join(timeout=40)
            server.server_close();app.desk.db.close()


if __name__=='__main__':main()
