const monitor = require('./utils/monitor')

App({
  globalData: {
    apiBase: 'https://dashboard-4i3t.onrender.com'
  },

  onLaunch() {
    monitor.trackPageView('app_launch')
  },

  onShow(options) {
    // 仅从后台切回前台时上报（scene 区分冷启动/热启动）
    // options.scene 存在说明是冷启动触发 onShow，跳过避免和 onLaunch/onLoad 重复
    if (this._launched) {
      const pages = getCurrentPages()
      const page = pages.length > 0 ? pages[pages.length - 1].route : 'app_show'
      monitor.trackPageView(page)
    }
    this._launched = true
  }
})
