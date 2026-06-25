// Cloudflare Worker - Render 保活脚本
// 每14分钟 ping 一次，防止免费实例休眠
// 部署: npx wrangler deploy

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // /ping - 手动触发健康检查
    if (url.pathname === '/ping') {
      const result = await pingRender(env.RENDER_URL, env.HEALTH_ENDPOINT || '/healthz');
      return new Response(JSON.stringify(result), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // /status - 查看状态
    if (url.pathname === '/status') {
      return new Response(JSON.stringify({
        target: env.RENDER_URL,
        endpoint: env.HEALTH_ENDPOINT || '/healthz',
        lastCheck: env.LAST_CHECK || 'never',
        status: env.LAST_STATUS || 'unknown'
      }), { headers: { 'Content-Type': 'application/json' } });
    }
    
    // 首页
    return new Response('🔁 Render Keepalive Worker is running', {
      headers: { 'Content-Type': 'text/plain' }
    });
  },
  
  // Cron 触发器 - 每14分钟执行
  async scheduled(event, env, ctx) {
    const result = await pingRender(env.RENDER_URL, env.HEALTH_ENDPOINT || '/healthz');
    console.log(`[${new Date().toISOString()}] Ping ${env.RENDER_URL}: ${result.status} (${result.httpCode})`);
  }
};

async function pingRender(renderUrl, endpoint) {
  const url = `${renderUrl}${endpoint}`;
  const maxRetries = 2;
  
  for (let i = 0; i <= maxRetries; i++) {
    try {
      const resp = await fetch(url, { 
        method: 'GET',
        signal: AbortSignal.timeout(30000)
      });
      return { status: 'ok', httpCode: resp.status, retries: i, time: new Date().toISOString() };
    } catch (e) {
      if (i === maxRetries) {
        return { status: 'error', error: e.message, retries: i, time: new Date().toISOString() };
      }
      // 等待后重试
      await new Promise(r => setTimeout(r, 2000));
    }
  }
}
