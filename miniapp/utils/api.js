const app = getApp()

/**
 * GET 请求
 */
function get(url) {
  return request('GET', url)
}

/**
 * 通用请求
 */
function request(method, url) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + url,
      method: method,
      timeout: 10000,
      success(res) {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject(new Error('HTTP ' + res.statusCode))
        }
      },
      fail(err) {
        console.error('[API]', url, err)
        reject(err)
      }
    })
  })
}

module.exports = { get }
