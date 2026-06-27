const api = require('../../utils/api')
const monitor = require('../../utils/monitor')

Page({
  data: {
    loaded: 0,
    total: 7,
    warming: true,
    intlGold: {},
    shuibei: {},
    sgeGold: {},
    m2: {},
    m1m2: {},
    cpi: {},
    bond: {},
    lpr: {},
    fund: {},
    oil: {},
    m1m2Chart: {}
  },

  onLoad() {
    monitor.trackPageView('pages/index/index')
    this.warmUp()
  },

  onPullDownRefresh() {
    this.warmUp().then(() => wx.stopPullDownRefresh())
  },

  // 刷新按钮点击监控
  onRefreshTap() {
    monitor.trackClick({ type: 'button', currentTarget: { id: 'btn_refresh' } })
    this.warmUp()
  },

  // 先发一个轻量请求唤醒 Render 服务，再加载数据
  async warmUp() {
    this.setData({ loaded: 0, warming: true })
    try {
      await api.get('/healthz')
    } catch (e) {
      // 即使预热失败也继续加载
      console.warn('预热请求失败，继续加载:', e)
    }
    this.setData({ warming: false })
    this.loadAll()
  },

  async loadAll() {
    const tasks = [
      { key: 'intlGold', url: '/api/intl_gold', handler: d => ({
        price_usd_oz: '$' + d.price_usd_oz,
        price_cny_gram: '¥' + d.price_cny_gram + '/g',
        fx_rate: d.fx_rate
      }) },
      { key: 'gold', url: '/api/gold_live', handler: d => {
        this.setData({ sgeGold: { price: '¥' + d.price_cny_gram + '/g' }, shuibei: { buy: '¥' + d.shuibei_buy + '/g', spread: '¥' + d.shuibei_spread + '/g' } })
        return {}
      }},
      { key: 'm1m2', url: '/api/m1m2_live', handler: d => ({
        gap: (d.gap >= 0 ? '+' : '') + d.gap + '%',
        m1: d.m1_yoy + '%',
        m2: d.m2_yoy + '%'
      }) },
      { key: 'bond', url: '/api/bond_live', handler: d => ({ yield: d.yield_10y + '%' }) },
      { key: 'lpr', url: '/api/lpr_live', handler: d => d },
      { key: 'static', url: '/api/static_data', handler: d => {
        this.setData({
          m2: d.m2 ? { cagr: d.m2.cagr_20y + '%', period: d.m2.data_period, multiple: d.m2.growth_multiple } : {},
          cpi: d.cpi ? { cagr: d.cpi.cagr_20y + '%', max: d.cpi.cpi_max + '%', min: d.cpi.cpi_min + '%' } : {},
          oil: {
            sz: d.oil_sz ? '¥' + d.oil_sz.price : '--',
            szDate: d.oil_sz ? d.oil_sz.data_date : '',
            qz: d.oil_qz ? '¥' + d.oil_qz.price : '--',
            qzDate: d.oil_qz ? d.oil_qz.data_date : ''
          },
          fund: d.fund_rate ? { first: d.fund_rate.first_5y_plus + '%', second: d.fund_rate.second_5y_plus + '%' } : {}
        })
        return {}
      }},
      { key: 'chart', url: '/api/m1m2_monthly', handler: d => {
        this.updateChart(d)
        return {}
      }}
    ]

    tasks.forEach(task => {
      api.get(task.url).then(data => {
        const result = task.handler(data)
        if (Object.keys(result).length > 0) {
          const update = {}
          update[task.key] = result
          this.setData(update)
        }
        this.setData({ loaded: this.data.loaded + 1 })
      }).catch(() => {
        this.setData({ loaded: this.data.loaded + 1 })
      })
    })
  },

  updateChart(data) {
    if (!data || !data.length) return
    const labels = data.map(d => d.month)
    const gapData = data.map(d => parseFloat((d.m1_yoy - d.m2_yoy).toFixed(2)))

    this.setData({
      m1m2Chart: {
        lazyLoad: true,
        option: {
          grid: { top: 20, bottom: 30, left: 50, right: 20 },
          xAxis: {
            type: 'category',
            data: labels,
            axisLabel: { fontSize: 9, color: '#64748b' }
          },
          yAxis: {
            type: 'value',
            axisLabel: { fontSize: 10, color: '#64748b', formatter: v => (v >= 0 ? '+' : '') + v + '%' }
          },
          series: [{
            type: 'bar',
            data: gapData.map(v => ({
              value: v,
              itemStyle: { color: v >= 0 ? '#10b981' : '#ef4444' }
            })),
            barMaxWidth: 20
          }],
          tooltip: {
            trigger: 'axis',
            formatter: p => p[0].axisValue + '\n剪刀差: ' + (p[0].value >= 0 ? '+' : '') + p[0].value.toFixed(2) + '%'
          }
        }
      }
    })
  }
})
