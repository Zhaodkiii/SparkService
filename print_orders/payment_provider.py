from contextlib import contextmanager
from types import SimpleNamespace
from . import wechat, alipay
from .payment_config import config
from .domain import Unavailable


@contextmanager
def wx(cfg):
    token=wechat.active_config.set(cfg)
    try: yield
    finally: wechat.active_config.reset(token)


def proxy(a, refund=None):
    return SimpleNamespace(id=a.id,title=a.order.title,total_fen=a.amount,payment_expires_at=a.expires_at,
                           refund_reason=refund.reason if refund else '',refund_number=refund.id.hex if refund else '')


def create(a):
    cfg=config(a.config)
    if a.config.channel_id=='alipay': return {'order_string':alipay.create(a,cfg)}, ''
    with wx(cfg):
        prepay=a.prepay_id or wechat.create(proxy(a))
        return wechat.app_parameters(prepay), prepay


def query(a):
    cfg=config(a.config)
    if a.config.channel_id=='wechat':
        with wx(cfg): data=wechat.query(proxy(a))
        if data.get('trade_state')=='SUCCESS':
            if data.get('appid')!=cfg['APPID'] or data.get('mchid')!=cfg['MCHID']: raise ValueError('Merchant mismatch')
            return paid_wechat(a,data)
        return {'state':{'CLOSED':'closed','REVOKED':'closed','NOT_EXIST':'absent','PAYERROR':'failed'}.get(data.get('trade_state'),'pending')}
    data=alipay.request('alipay.trade.query',{'out_trade_no':a.id.hex},cfg)
    if data.get('trade_status') in ('TRADE_SUCCESS','TRADE_FINISHED'): return paid_alipay(a,data)
    return {'state':{'TRADE_CLOSED':'closed','NOT_EXIST':'absent'}.get(data.get('trade_status'),'pending')}


def paid_wechat(a,data):
    if data.get('out_trade_no')!=a.id.hex or data.get('amount',{}).get('total')!=a.amount or data.get('amount',{}).get('currency')!='CNY' or not data.get('transaction_id'): raise ValueError('Payment mismatch')
    return {'state':'succeeded','provider_id':data['transaction_id']}


def paid_alipay(a,data):
    if data.get('out_trade_no')!=a.id.hex or alipay.fen(data.get('total_amount'))!=a.amount or not data.get('trade_no'): raise ValueError('Payment mismatch')
    return {'state':'succeeded','provider_id':data['trade_no']}


def close(a):
    cfg=config(a.config)
    if a.config.channel_id=='wechat':
        with wx(cfg): wechat.close(proxy(a))
    else: alipay.request('alipay.trade.close',{'out_trade_no':a.id.hex},cfg)


def _wx_refund_result(r,data):
    a=r.attempt
    if data.get('out_refund_no')!=r.id.hex or data.get('out_trade_no')!=a.id.hex or data.get('amount',{}).get('refund')!=r.amount or data.get('amount',{}).get('total')!=a.amount: raise ValueError('Refund mismatch')
    return {'state':{'SUCCESS':'success','CLOSED':'exception','ABNORMAL':'exception'}.get(data.get('status'),'processing'),'provider_id':data.get('refund_id','')}


def query_refund(r):
    a=r.attempt; cfg=config(a.config)
    if a.config.channel_id=='wechat':
        with wx(cfg): data=wechat.query_refund(proxy(a,r))
        if data.get('refund_absent'): return {'state':'absent','provider_id':''}
        return _wx_refund_result(r,data)
    data=alipay.request('alipay.trade.fastpay.refund.query',{'out_trade_no':a.id.hex,'out_request_no':r.id.hex},cfg)
    # Alipay may return code=10000 with no refund fields when no refund exists.
    if not data.get('refund_status') and data.get('refund_amount') is None:
        return {'state':'absent','provider_id':''}
    if data.get('out_trade_no')!=a.id.hex or data.get('out_request_no')!=r.id.hex or alipay.fen(data.get('refund_amount'))!=r.amount: raise ValueError('Refund mismatch')
    if data.get('trade_no') and data['trade_no']!=a.provider_id: raise ValueError('Refund mismatch')
    return {'state':'success' if data.get('refund_status')=='REFUND_SUCCESS' else 'processing','provider_id':data.get('trade_no','')}


def refund(r):
    """Submit the same immutable refund number; queries use query_refund only."""
    a=r.attempt; cfg=config(a.config)
    if a.config.channel_id=='wechat':
        with wx(cfg): data=wechat.refund(proxy(a,r))
        return _wx_refund_result(r,data)
    data=alipay.request('alipay.trade.refund',{'out_trade_no':a.id.hex,'out_request_no':r.id.hex,'refund_amount':alipay.money(r.amount),'refund_reason':r.reason},cfg)
    if data.get('out_trade_no')!=a.id.hex or data.get('trade_no')!=a.provider_id or alipay.fen(data.get('refund_fee'))!=r.amount: raise ValueError('Refund mismatch')
    if data.get('fund_change')=='Y': return {'state':'success','provider_id':data['trade_no']}
    # code=10000 alone is not a confirmation of funds movement.
    return query_refund(r) if data.get('fund_change') in ('N',None) else {'state':'processing','provider_id':data['trade_no']}
