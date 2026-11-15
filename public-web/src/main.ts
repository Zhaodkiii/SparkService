import {createApp} from 'vue'
import PublicApp from './PublicApp.vue'
import router from './router'
createApp(PublicApp).use(router).mount('#app')
