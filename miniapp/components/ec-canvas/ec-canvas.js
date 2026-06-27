const WXCanvas = require('./wx-canvas')
const echarts = require('./echarts.min')

Component({
  properties: {
    canvasId: {
      type: String,
      value: 'ec-canvas'
    },
    ec: {
      type: Object
    }
  },

  data: {
    use2dCanvas: false
  },

  lifetimes: {
    attached() {
      // 检查 Canvas 2D 支持
      const canUse = wx.canIUse && wx.canIUse('canvas.type.2d')
      this.setData({ use2dCanvas: !!canUse })
    },

    ready() {
      // 延迟初始化，等 ec 属性更新
      if (!this.data.ec || !this.data.ec.option) {
        // ec 还未传入，等待 observer
        return
      }
      this._initChart()
    }
  },

  observers: {
    'ec.option'(option) {
      if (option) {
        // 选项更新时重新设置
        if (this.chart) {
          this.chart.setOption(option, true)
        } else {
          this._initChart()
        }
      }
    }
  },

  methods: {
    _initChart() {
      if (this._initializing) return
      this._initializing = true

      const ecData = this.data.ec || {}
      if (!ecData.option) {
        this._initializing = false
        return
      }

      if (this.data.use2dCanvas) {
        this._initNewCanvas(ecData)
      } else {
        this._initOldCanvas(ecData)
      }
    },

    _initNewCanvas(ecData) {
      const query = this.createSelectorQuery()
      query.select('.ec-canvas')
        .fields({ node: true, size: true })
        .exec(res => {
          this._initializing = false
          if (!res || !res[0] || !res[0].node) {
            console.error('[ec-canvas] Canvas node not found')
            return
          }

          const canvasNode = res[0].node
          const canvasWidth = res[0].width
          const canvasHeight = res[0].height
          const dpr = wx.getSystemInfoSync().pixelRatio

          const ctx = canvasNode.getContext('2d')
          const canvas = new WXCanvas(ctx, this.data.canvasId, true, canvasNode)

          echarts.setCanvasCreator(() => canvas)
          const chart = echarts.init(canvas, null, {
            width: canvasWidth,
            height: canvasHeight,
            devicePixelRatio: dpr
          })

          canvas.setChart(chart)
          chart.setOption(ecData.option, true)
          this.chart = chart
        })
    },

    _initOldCanvas(ecData) {
      this._initializing = false
      const ctx = wx.createCanvasContext(this.data.canvasId, this)
      const canvas = new WXCanvas(ctx, this.data.canvasId, false)

      echarts.setCanvasCreator(() => canvas)
      const chart = echarts.init(canvas, null, {
        width: 350,
        height: 220,
        devicePixelRatio: 1
      })

      canvas.setChart(chart)
      chart.setOption(ecData.option, true)
      this.chart = chart
    },

    touchStart(e) {
      if (this.chart && e.touches.length > 0) {
        const touch = e.touches[0]
        const handler = this.chart.getZr().handler
        handler.dispatch('mousedown', {
          zrX: touch.x, zrY: touch.y,
          preventDefault() {}, stopImmediatePropagation() {}, stopPropagation() {}
        })
        handler.dispatch('mousemove', {
          zrX: touch.x, zrY: touch.y,
          preventDefault() {}, stopImmediatePropagation() {}, stopPropagation() {}
        })
      }
    },

    touchMove(e) {
      if (this.chart && e.touches.length > 0) {
        const touch = e.touches[0]
        const handler = this.chart.getZr().handler
        handler.dispatch('mousemove', {
          zrX: touch.x, zrY: touch.y,
          preventDefault() {}, stopImmediatePropagation() {}, stopPropagation() {}
        })
      }
    },

    touchEnd(e) {
      if (this.chart) {
        const touch = e.changedTouches ? e.changedTouches[0] : {}
        const handler = this.chart.getZr().handler
        handler.dispatch('mouseup', {
          zrX: touch.x || 0, zrY: touch.y || 0,
          preventDefault() {}, stopImmediatePropagation() {}, stopPropagation() {}
        })
        handler.dispatch('click', {
          zrX: touch.x || 0, zrY: touch.y || 0,
          preventDefault() {}, stopImmediatePropagation() {}, stopPropagation() {}
        })
      }
    }
  }
})
