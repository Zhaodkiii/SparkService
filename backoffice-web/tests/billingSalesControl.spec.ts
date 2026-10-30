import {describe,it,vi,expect} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import Antd,{Switch,Modal} from 'ant-design-vue';
import View from '../src/views/BillingSalesControl.vue';
const mocks=vi.hoisted(()=>({get:vi.fn(),patch:vi.fn()}));
vi.mock('../src/api/http',()=>({default:mocks}));
vi.mock('../src/stores/auth',()=>({useAuthStore:()=>({user:{is_superuser:true}})}));
describe('sales controls',()=>{it('shows environment and requires reason and explicit confirmation',async()=>{
 mocks.get.mockResolvedValue({environment:'production',revision:0,diamond_redemption_enabled:false,membership_sales_enabled:false});
 const w=mount(View,{attachTo:document.body,global:{plugins:[Antd]}});await flushPromises();expect(w.text()).toContain('生产环境');
 await w.find('button').trigger('click');await flushPromises();
 w.findAllComponents(Switch)[0]!.vm.$emit('update:checked',true);await flushPromises();
 expect((document.querySelector('.ant-modal button.ant-btn-primary') as HTMLButtonElement).disabled).toBe(true);
 await new DOMWrapper(document.querySelector('textarea')!).setValue('验收后开放');await new DOMWrapper(document.querySelector('.ant-modal button.ant-btn-primary')!).trigger('click');await flushPromises();
 expect(mocks.patch).not.toHaveBeenCalled();expect(document.body.textContent).toContain('确认修改生产环境的销售设置');
 w.unmount();Modal.destroyAll();document.body.innerHTML='';
});});
