/**
 * dsh-fishbuddy-mac —— 入口壳
 *
 * 为什么这么薄：DSH 对插件模块按 URL 缓存，改了 lib 里的代码、重新启用插件，
 * 拿到的仍是第一次 import 的那份（不重启 DSH 不生效）。
 * 这里每次 apply 都带 ?v=时间戳 动态 import ./impl.js —— 重新启用即拿到新代码。
 */
export default {
  name: 'dsh-fishbuddy-mac',
  inject: ['sessionController', 'webServer', 'connection'],
  async apply(ctx) {
    const url = new URL('./impl.js', import.meta.url)
    url.searchParams.set('v', String(Date.now()))
    const mod = await import(url.href)
    return mod.default.apply(ctx)
  },
}
