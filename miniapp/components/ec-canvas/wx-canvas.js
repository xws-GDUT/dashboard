/**
 * 微信小程序 Canvas 适配层
 * 将小程序 Canvas API 封装为 ECharts 可用的 Canvas 接口
 */
class WxCanvas {
  constructor(ctx, canvasId, isNew, canvasNode) {
    this.ctx = ctx
    this.canvasId = canvasId
    this.chart = null
    this.isNew = isNew
    this.canvasNode = canvasNode

    if (isNew) {
      this._initStyle(ctx)
    } else {
      this._initOld(ctx)
    }
  }

  getContext(contextType) {
    if (contextType === '2d') {
      return this.ctx
    }
  }

  setChart(chart) {
    this.chart = chart
  }

  addEventListener() {}
  removeEventListener() {}
  attachEvent() {}
  detachEvent() {}

  _initStyle(ctx) {
    // 新的 Canvas 2D 接口
    ctx.createRadialGradient = function () {
      return ctx.createCircularGradient(arguments)
    }
  }

  _initOld(ctx) {
    ctx.createRadialGradient = function () {
      return ctx.createCircularGradient(arguments)
    }
  }

  // 旧版 canvas 需要 draw
  draw() {
    if (!this.isNew) {
      this.ctx.draw(false)
    }
  }
}

module.exports = WxCanvas
