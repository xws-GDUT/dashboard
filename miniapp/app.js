const monitor = require('./utils/monitor')

App({
  globalData: {
    apiBase: 'https://dashboard-4i3t.onrender.com'
  },

  onLaunch() {
    // 启动时上报
    monitor.trackPageView('app_launch')
  },

  onShow() {
    // 从后台切回前台时上报
    const pages = getCurrentPages()
    const page = pages.length > 0 ? pages[pages.length - 1].route : 'app_show'
    monitor.trackPageView(page)
  }
})
