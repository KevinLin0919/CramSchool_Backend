import { createRouter, createWebHashHistory } from 'vue-router'
import UploadView from '../views/UploadView.vue'
import { BRAND } from '../api'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', name: 'upload', component: UploadView, meta: { title: '建立模板' } },
    { path: '/label/:id?', name: 'label', component: () => import('../views/LabelView.vue'), meta: { title: '標註答案區' } },
    { path: '/:pathMatch(.*)*', redirect: { name: 'upload' } },
  ],
})
router.afterEach((to) => { document.title = `${to.meta.title || '建立模板'}｜${BRAND}` })
export default router
