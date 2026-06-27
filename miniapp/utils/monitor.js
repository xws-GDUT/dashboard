/**
 * 服务监控 SDK - 微信小程序版
 * 上报 PV、点击事件到 service-monitor
 */
const MONITOR_HOST = 'https://service-monitor-8kj7.onrender.com'
const API = MONITOR_HOST + '/api/track'

let sessionId = ''
let pageEnterTime = 0

function getSessionId() {
  if (sessionId) return sessionId
  try {
    sessionId = wx.getStorageSync('_mon_sid')
  } catch (e) {}
  if (!sessionId) {
    sessionId = 'mp_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10)
    try {
      wx.setStorageSync('_mon_sid', sessionId)
    } catch (e) {}
  }
  return sessionId
}

function getUserId() {
  try {
    return wx.getStorageSync('_mon_uid') || ''
  } catch (e) {
    return ''
  }
}

function getSystemInfo() {
  try {
    return wx.getSystemInfoSync()
  } catch (e) {
    return {}
  }
}

function send(url, data) {
  wx.request({
    url: API + url,
    method: 'POST',
    header: { 'Content-Type': 'application/json' },
    data: data,
    timeout: 5000,
    success() {},
    fail() {}
  })
}

/**
 * 上报页面访问
 */
function trackPageView(pagePath) {
  const sysInfo = getSystemInfo()
  send('/pageview', {
    session_id: getSessionId(),
    user_id: getUserId(),
    page_url: pagePath || '',
    referrer: '',
    user_agent: sysInfo.model || '',
    screen_width: sysInfo.screenWidth || 0,
    screen_height: sysInfo.screenHeight || 0,
    language: sysInfo.language || '',
    platform: sysInfo.platform || '',
    app_version: sysInfo.version || '',
    timezone: ''
  })
}

/**
 * 上报点击事件
 */
function trackClick(event) {
  send('/click', {
    session_id: getSessionId(),
    user_id: getUserId(),
    page_url: getCurrentPagePath(),
    element_tag: event.type || 'tap',
    element_id: event.currentTarget ? (event.currentTarget.id || '') : '',
    element_class: '',
    element_text: '',
    pos_x: event.detail ? event.detail.x : 0,
    pos_y: event.detail ? event.detail.y : 0
  })
}

function getCurrentPagePath() {
  const pages = getCurrentPages()
  return pages.length > 0 ? pages[pages.length - 1].route : ''
}

/**
 * 设置用户标识（登录后调用）
 */
function setUserId(uid) {
  try {
    wx.setStorageSync('_mon_uid', uid)
  } catch (e) {}
}

module.exports = {
  trackPageView,
  trackClick,
  setUserId,
  getSessionId,
  getUserId
}
