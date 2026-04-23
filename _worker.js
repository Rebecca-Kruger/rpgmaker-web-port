// Generate an HMAC-SHA256 signature.
async function createSignature(text, secretKey) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secretKey), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(text));
  return Array.from(new Uint8Array(signature)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const secretKey = env.ACCESS_SECRET_KEY;
    if (!secretKey) {
      return new Response("Missing ACCESS_SECRET_KEY binding", { status: 500 });
    }

    // ==========================================
    // 1. Login API. Only this endpoint performs a KV read.
    // ==========================================
    if (request.method === "POST" && url.pathname === "/api/auth") {
      try {
        const { hash } = await request.json();
        const isValid = await env.AUTH_CODES.get(hash); // Query KV storage.
        
        if (isValid) {
          // Verification succeeded. Set a 30-day expiry.
          const exp = Date.now() + 1000 * 60 * 60 * 24 * 30;
          const payload = `${hash}.${exp}`;
          // Sign the payload with the private key.
          const sig = await createSignature(payload, secretKey);
          const token = `${payload}.${sig}`; // Token format: hash.expiry.signature

          const headers = new Headers();
          // Store the token in the browser cookie jar.
          headers.append("Set-Cookie", `rpg_token=${token}; HttpOnly; Secure; Path=/; Max-Age=${60 * 60 * 24 * 30}`);
          headers.append("Content-Type", "application/json");
          return new Response(JSON.stringify({ success: true }), { headers });
        } else {
          return new Response(JSON.stringify({ success: false, error: "Access code is invalid or expired" }), { status: 401, headers: { "Content-Type": "application/json" } });
        }
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: "Invalid request payload" }), { status: 400 });
      }
    }

    // ==========================================
    // 2. Edge guard. Signature verification performs no KV reads.
    // ==========================================
    const cookieHeader = request.headers.get("Cookie") || "";
    const match = cookieHeader.match(/rpg_token=([^;]+)/);
    let authorized = false;

    if (match) {
      const token = match[1];
      const parts = token.split('.');
      
      // Validate token shape: hash.expiry.signature.
      if (parts.length === 3) {
        const [hash, exp, sig] = parts;
        // First check: expiration.
        if (Date.now() < parseInt(exp)) {
          // Second check: recompute the signature to prevent tampering.
          const expectedSig = await createSignature(`${hash}.${exp}`, secretKey);
          if (sig === expectedSig) {
            authorized = true; // Access code is valid and the signature matches.
          }
        }
      }
    }

    // ==========================================
    // 3. Serve game assets or return the access page.
    // ==========================================
    if (authorized) {
      // Valid token: serve static assets without touching KV.
      return env.ASSETS ? env.ASSETS.fetch(request) : fetch(request); 
    }

    // Missing or invalid token: show the access page.
    return new Response(loginHTML, {
      headers: { "Content-Type": "text/html;charset=UTF-8" },
    });
  },
};

// ==========================================
// 4. Access page UI.
// ==========================================
const loginHTML = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>Technical Exploration Runtime</title>
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
        <h1>Technical Exploration Runtime</h1>
        <p>Enter the access code for technical testing</p>
        <input type="text" id="hash-input" placeholder="XXXX-XXXX-XXXX" autocomplete="off" autocorrect="off" spellcheck="false">
        <button onclick="verifyCode()">Verify and Launch</button>
        <div id="error-msg" class="error">Invalid access code. Please try again.</div>
    </div>

    <script>
        (function initDebugFlag() {
            try {
                const search = new URLSearchParams(window.location.search);
                if (search.get('audioDebug') === '1') {
                    sessionStorage.setItem('AUDIO_DEBUG', '1');
                    localStorage.removeItem('AUDIO_DEBUG');
                } else {
                    sessionStorage.removeItem('AUDIO_DEBUG');
                    localStorage.removeItem('AUDIO_DEBUG');
                }
            } catch (err) {}
        })();

        async function verifyCode() {
            const hash = document.getElementById('hash-input').value.trim();
            const errorMsg = document.getElementById('error-msg');
            const btn = document.querySelector('button');
            
            if(!hash) { errorMsg.style.display = 'block'; errorMsg.innerText = 'Access code is required'; return; }
            
            btn.innerText = 'Verifying secure signature...';
            btn.disabled = true;

            try {
                const res = await fetch('/api/auth', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hash: hash })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    btn.innerText = 'Access granted. Loading game...';
                    btn.style.background = '#30d158';
                    errorMsg.style.display = 'none';
                    setTimeout(() => window.location.href = window.location.pathname + window.location.search + window.location.hash, 800);
                } else {
                    btn.innerText = 'Verify and Launch';
                    btn.disabled = false;
                    errorMsg.innerText = data.error;
                    errorMsg.style.display = 'block';
                }
            } catch (err) {
                btn.innerText = 'Verify and Launch';
                btn.disabled = false;
                errorMsg.innerText = 'Network error. Please check your connection.';
                errorMsg.style.display = 'block';
            }
        }
    </script>
</body>
</html>
`;
