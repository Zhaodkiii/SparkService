"""Safe, actionable gateway errors. Never store raw responses or signed requests."""
from .domain import Unavailable


class GatewayError(Unavailable):
    def __init__(self, code, category, message, action):
        self.gateway_code = code
        self.category = category
        self.action = action
        super().__init__(message)


def alipay_error(code):
    known = {
        'ACQ.SELLER_BALANCE_NOT_ENOUGH': ('balance', '商家可用余额不足，退款受阻', '请补足实际收款商户的可用余额，或等待待结算资金到账后重试退款'),
        'isv.insufficient-isv-permissions': ('permission', '支付宝接口权限不足', '请检查应用已签约产品及接口权限后恢复处理'),
        'isv.insufficient-user-permissions': ('permission', '支付宝商户授权不足', '请核对收款商户授权后恢复处理'),
        'isv.invalid-signature': ('configuration', '支付宝请求签名校验失败', '请检查当前交易使用的配置版本及密钥、编码设置'),
        'ACQ.REFUND_AMT_NOT_EQUAL_TOTAL': ('business', '退款金额不符合渠道要求', '请核对原支付和已退款金额后人工处理'),
        'ACQ.REFUND_AMT_NOT_VALID': ('business', '退款金额不符合渠道要求', '请核对原支付和已退款金额后人工处理'),
        'ACQ.REFUND_AMT_NOT_ENOUGH': ('business', '超过可退金额', '请先查询渠道退款记录，核对是否已通过其他入口退款'),
        'ACQ.TRADE_HAS_FINISHED': ('business', '交易已结束，渠道不允许本次操作', '请核对交易状态和可退款期限'),
        'ACQ.TRADE_STATUS_ERROR': ('business', '支付宝交易状态不允许本次操作', '请查询原交易及退款状态后核对处理'),
    }
    category,message,action=known.get(code,('business','支付宝拒绝本次请求','请根据渠道错误码核对商户权限、交易状态及支付宝账单后处理'))
    # Unknown provider strings may contain echoed request data: retain only a bounded code.
    safe=code if isinstance(code,str) and len(code)<=100 and all(c.isalnum() or c in '._-' for c in code) else 'ALIPAY_BUSINESS_ERROR'
    return GatewayError(safe,category,message,action)
