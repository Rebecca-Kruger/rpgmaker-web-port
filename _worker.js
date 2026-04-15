// 你可以把这串字符换成任何你喜欢的乱码，这是你服务器的“终极防伪私钥”
// 绝对不要泄露给别人！
const SECRET_KEY = "RPG_MAKER_SUPER_SECRET_KEY_2026";

// 核心黑科技：生成不可伪造的 HMAC-SHA256 加密签名
async function createSignature(text) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(SECRET_KEY), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(text));
  return Array.from(new Uint8Array(signature)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // ==========================================
    // 1. API 接口：处理登录，只在这里消耗 1 次 KV 读取！
    // ==========================================
    if (request.method === "POST" && url.pathname === "/api/auth") {
      try {
        const { hash } = await request.json();
        const isValid = await env.AUTH_CODES.get(hash); // 查阅 KV 数据库
        
        if (isValid) {
          // 验证成功！计算过期时间（30天）
          const exp = Date.now() + 1000 * 60 * 60 * 24 * 30;
          const payload = `${hash}.${exp}`;
          // 用私钥给这个玩家签发一个独一无二的加密签名
          const sig = await createSignature(payload);
          const token = `${payload}.${sig}`; // 最终的通行证格式：哈希码.过期时间.防伪签名

          const headers = new Headers();
          // 把通行证种在玩家的浏览器里
          headers.append("Set-Cookie", `rpg_token=${token}; HttpOnly; Secure; Path=/; Max-Age=${60 * 60 * 24 * 30}`);
          headers.append("Content-Type", "application/json");
          return new Response(JSON.stringify({ success: true }), { headers });
        } else {
          return new Response(JSON.stringify({ success: false, error: "激活码无效或已过期" }), { status: 401, headers: { "Content-Type": "application/json" } });
        }
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: "请求格式错误" }), { status: 400 });
      }
    }

    // ==========================================
    // 2. 边缘拦截器：纯数学解密验证，0 次 KV 读取！
    // ==========================================
    const cookieHeader = request.headers.get("Cookie") || "";
    const match = cookieHeader.match(/rpg_token=([^;]+)/);
    let authorized = false;

    if (match) {
      const token = match[1];
      const parts = token.split('.');
      
      // 检查通行证格式是否完整 (哈希码.时间戳.签名)
      if (parts.length === 3) {
        const [hash, exp, sig] = parts;
        // 第一关：检查有没有过期
        if (Date.now() < parseInt(exp)) {
          // 第二关：服务器在内存中重新计算一次签名，比对是否一致（防止伪造）
          const expectedSig = await createSignature(`${hash}.${exp}`);
          if (sig === expectedSig) {
            authorized = true; // 密码正确，且签名一致，绝对是合法玩家！
          }
        }
      }
    }

    // ==========================================
    // 3. 放行游戏资源，或者打回登录页
    // ==========================================
    if (authorized) {
      // 身份完全合法，秒速放行静态资源，全程不碰 KV 数据库
      return env.ASSETS ? env.ASSETS.fetch(request) : fetch(request); 
    }

    // 没通行证，或者伪造通行证，直接拦截并展示登录页
    return new Response(loginHTML, {
      headers: { "Content-Type": "text/html;charset=UTF-8" },
    });
  },
};

// ==========================================
// 4. 高颜值登录界面 UI
// ==========================================
const loginHTML = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>云端卡带机 - 官方正版授权</title>
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <style>
        body { margin: 0; padding: 0; background-color: #0c0c0e; color: #fff; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; overflow: hidden; }
        .bg-glow { position: absolute; width: 300px; height: 300px; background: radial-gradient(circle, rgba(0,122,255,0.2) 0%, rgba(0,0,0,0) 70%); top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: -1; }
        .container { text-align: center; width: 85%; max-width: 400px; padding: 40px 20px; background: rgba(30, 30, 35, 0.6); backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); border-radius: 24px; border: 1px solid rgba(255,255,255,0.08); box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
        h1 { font-size: 24px; margin-bottom: 8px; font-weight: 600; letter-spacing: 1px; }
        p { font-size: 14px; color: #888; margin-bottom: 30px; }
        input { width: 90%; padding: 16px; font-size: 16px; text-align: center; border-radius: 12px; border: none; outline: none; background: rgba(0,0,0,0.4); color: #fff; letter-spacing: 2px; transition: 0.3s; box-sizing: border-box; border: 1px solid rgba(255,255,255,0.1); }
        input:focus { border-color: #007aff; box-shadow: 0 0 0 4px rgba(0, 122, 255, 0.2); background: rgba(0,0,0,0.6); }
        button { width: 90%; padding: 16px; font-size: 16px; font-weight: bold; border-radius: 12px; border: none; background: #007aff; color: #fff; cursor: pointer; transition: 0.2s; box-sizing: border-box; margin-top: 20px; }
        button:active { transform: scale(0.96); background: #005bb5; }
        .error { color: #ff453a; font-size: 14px; margin-top: 15px; display: none; font-weight: 500; }
    </style>
</head>
<body>
    <div class="bg-glow"></div>
    <div class="container">
        <h1>云端卡带机</h1>
        <p>请输入作者提供的正版激活码</p>
        <input type="text" id="hash-input" placeholder="XXXX-XXXX-XXXX" autocomplete="off" autocorrect="off" spellcheck="false">
        <button onclick="verifyCode()">验证并接入</button>
        <div id="error-msg" class="error">激活码错误，请重新输入</div>
    </div>

    <script>
        async function verifyCode() {
            const hash = document.getElementById('hash-input').value.trim();
            const errorMsg = document.getElementById('error-msg');
            const btn = document.querySelector('button');
            
            if(!hash) { errorMsg.style.display = 'block'; errorMsg.innerText = '激活码不能为空'; return; }
            
            btn.innerText = '正在验证安全签名...';
            btn.disabled = true;

            try {
                const res = await fetch('/api/auth', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hash: hash })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    btn.innerText = '接入成功！正在装载游戏...';
                    btn.style.background = '#30d158';
                    errorMsg.style.display = 'none';
                    setTimeout(() => window.location.reload(), 800);
                } else {
                    btn.innerText = '验证并接入';
                    btn.disabled = false;
                    errorMsg.innerText = data.error;
                    errorMsg.style.display = 'block';
                }
            } catch (err) {
                btn.innerText = '验证并接入';
                btn.disabled = false;
                errorMsg.innerText = '网络连接异常，请检查网络';
                errorMsg.style.display = 'block';
            }
        }
    </script>
</body>
</html>
`;
