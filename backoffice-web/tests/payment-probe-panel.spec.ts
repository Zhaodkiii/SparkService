import {describe,it,expect,vi,afterEach} from 'vitest';
import {mount,flushPromises,type VueWrapper} from '@vue/test-utils';
import Antd from 'ant-design-vue';
import Panel,{type Probe} from '../src/components/print/PaymentProbePanel.vue';
let wrapper:VueWrapper|undefined;
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.useRealTimers()});
const probe=(extra:Partial<Probe>={}):Probe=>({id:'12345678-1234-1234-1234-123456789012',state:'created',created_at:'2026-10-24T00:00:00Z',expires_at:'2099-01-01T00:00:00Z',last_error:'',can_resume:true,expired:false,...extra});
const props=(p:Probe)=>({tests:[p],versionId:4,channel:'支付宝',link:'traveldiary-paytest://launch?id=example',linkProbeId:p.id,busy:false,disabled:false,deviceEnabled:true,checked:true});
function panel(p:Probe){wrapper=mount(Panel,{props:props(p),global:{plugins:[Antd]}});return wrapper}
describe('payment probe panel',()=>{
 it('uses a fixed square SVG and a single active action without duplicating resume buttons',()=>{const w=panel(probe());expect(w.find('.probe-qr').exists()).toBe(true);const qr=w.findComponent({name:'AQrcode'});expect(qr.props('size')).toBe(224);expect(qr.props('type')).toBe('svg');expect(w.find('.probe-qr svg').exists()).toBe(true);expect(w.text()).not.toContain('继续现有测试');expect(w.text()).not.toContain('显示二维码');expect(w.text()).toContain('作废测试');expect(w.text()).not.toContain('取消并确认关单')});
 it('hides QR immediately after expiry without a network refresh',async()=>{vi.useFakeTimers({toFake:['Date','setInterval','clearInterval']});vi.setSystemTime(new Date('2026-10-24T00:00:00Z'));const w=panel(probe({expires_at:'2026-10-24T00:00:02Z'}));expect(w.find('.probe-qr').exists()).toBe(true);await vi.advanceTimersByTimeAsync(3000);expect(w.find('.probe-qr').exists()).toBe(false);expect(w.text()).toContain('扫码已过期');expect(w.text()).toContain('重新创建测试单');expect(w.text()).not.toContain('显示二维码')});
 it('keeps historical rows read-only while a current test exists',async()=>{const p=probe();const w=panel(p);await w.setProps({tests:[p,probe({id:'old',state:'expired',can_resume:false,expired:true})]});expect(w.text()).not.toContain('关闭后重新创建');await w.find('.ant-collapse-header').trigger('click');await flushPromises();expect(w.find('.probe-history').text()).not.toContain('创建新的测试单');expect(w.find('.probe-history').text()).not.toContain('显示二维码')});
 it('shows an active record outside the last ten history records and hides a mismatched QR',async()=>{const w=panel(probe({state:'discarded',can_resume:false}));const active=probe({id:'active-older'});await w.setProps({active,linkProbeId:'another-record'});expect(w.find('.current-probe').text()).toContain('active-older');expect(w.find('.probe-qr').exists()).toBe(false);expect(w.text()).toContain('显示二维码')});
 it('does not offer new payments while an expired launched trade is unresolved',()=>{const w=panel(probe({state:'unknown',expires_at:'2020-01-01T00:00:00Z',can_resume:false,expired:true}));expect(w.text()).toContain('查询支付结果');expect(w.text()).toContain('取消并确认关单');expect(w.text()).not.toContain('创建新的测试单');expect(w.find('.probe-qr').exists()).toBe(false)});
});
