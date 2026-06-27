## 行情早知道 — 微信小程序开发指南

### 项目结构

```
miniapp/
├── app.js              # 全局配置（API地址）
├── app.json            # 小程序配置
├── app.wxss            # 全局样式（可选）
├── project.config.json # 开发者工具配置
├── sitemap.json        # 站点地图
├── pages/
│   └── index/
│       ├── index.wxml  # 首页布局
│       ├── index.wxss  # 首页样式
│       ├── index.js    # 首页逻辑
│       └── index.json  # 页面配置
└── utils/
    └── api.js          # API 请求封装
```

### 使用步骤

#### 1. 注册小程序

打开 https://mp.weixin.qq.com/ → 注册 → 选择「小程序」

#### 2. 下载微信开发者工具

https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

#### 3. 导入项目

- 打开微信开发者工具
- 选择「导入项目」
- 目录选择 `/workspace/miniapp`
- AppID 填入你注册时获得的 AppID

#### 4. 配置服务器域名

在微信公众平台 → 开发 → 开发管理 → 服务器域名：

| 类型 | 域名 |
|------|------|
| request合法域名 | `https://dashboard-4i3t.onrender.com` |

#### 5. 安装 ECharts 组件

小程序中使用 ECharts 需要引入组件：

```bash
# 下载 echarts-for-weixin
npm install echarts-for-weixin
# 将 ec-canvas 目录复制到 miniapp/components/
```

或直接在 GitHub 下载：https://github.com/ecomfe/echarts-for-weixin

#### 6. 预览和发布

- 点击「编译」→ 在模拟器中预览
- 点击「预览」→ 手机扫码真机预览
- 点击「上传」→ 提交审核 → 发布

### 技术说明

| 项目 | 说明 |
|------|------|
| 后端 | 复用现有 Flask API，无需改动 |
| 数据获取 | 7 个并行请求，先到先渲染 |
| 图表 | ECharts M1-M2 剪刀差走势图 |
| 下拉刷新 | 支持 |
| 超时 | 单次请求 10 秒超时 |

### 注意事项

1. 小程序要求 HTTPS 域名，Render 已满足
2. 需要在小程序后台配置 `request合法域名`
3. ECharts 组件需要手动下载放入 `components/` 目录
4. 首屏加载可能较慢（AKShare 数据获取），建议加 loading 动画
