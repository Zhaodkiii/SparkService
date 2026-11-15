import {createRouter,createWebHistory} from 'vue-router'
export default createRouter({history:createWebHistory(),routes:[
 {path:'/',redirect:'/experience/books'},
 {path:'/experience/books',component:()=>import('../BookApp.vue')},
 {path:'/invite/:token',component:()=>import('../features/invitations/InvitationLanding.vue')},
 {path:'/download',component:()=>import('../features/invitations/InvitationLanding.vue')},
 {path:'/:pathMatch(.*)*',component:()=>import('../features/invitations/InvitationLanding.vue')},
]})
