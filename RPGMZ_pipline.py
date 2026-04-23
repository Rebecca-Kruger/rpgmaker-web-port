import os
import json
import sys
import re
from pipeline.audio import convert_audio_to_m4a, sanitize_audio_filenames, validate_audio_consistency
from pipeline.config import load_cloudflare_credentials, load_runtime_config
from pipeline.deploy import deploy_to_cloudflare
from pipeline.resources import (
    apply_mtools_translation,
    apply_patch,
    clean_pc_build,
    convert_video_to_mp4,
    decrypt_assets,
    fix_resource_percent_symbols,
    patch_system_json,
)
from pipeline.workspace import get_valid_project_name, prepare_www_workspace

# ==========================================
# 1. 基础环境配置
# ==========================================
RUNTIME = load_runtime_config()
BASE_DIR = RUNTIME.base_dir
WWW_DIR = RUNTIME.www_dir
PATCH_ZIP = RUNTIME.patch_zip
SYSTEM_JSON_PATH = RUNTIME.system_json_path
VPAD_HTML_PATH = RUNTIME.vpad_html_path
GAME_NAME = RUNTIME.game_name

# ==========================================
# 核心流水线函数
# ==========================================

def patch_problematic_plugin_params():
    """只修复当前已定位的高风险插件参数，不做全量重写。"""
    print("\n>>> 步骤 6: 定点修复 iOS 高风险插件参数...")
    plugins_path = os.path.join(WWW_DIR, "js", "plugins.js")
    if not os.path.exists(plugins_path):
        print("  [-] 未找到 plugins.js，跳过插件参数修复。")
        return

    with open(plugins_path, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        print("  [!] plugins.js 格式异常，跳过插件参数修复。")
        return

    prefix = content[:start]
    suffix = content[end + 1:]
    plugins = json.loads(content[start:end + 1])
    changed = False

    for plugin in plugins:
        if plugin.get("name") == "LL_StandingPicture" and plugin.get("status"):
            params = plugin.get("parameters", {})
            if params.get("bootCachePictures") == "true":
                params["bootCachePictures"] = "false"
                plugin["parameters"] = params
                changed = True
                print("  [+] 已关闭 LL_StandingPicture 的启动预缓存 (bootCachePictures=false)")

    if changed:
        with open(plugins_path, "w", encoding="utf-8") as f:
            f.write(prefix)
            json.dump(plugins, f, ensure_ascii=False, indent=2)
            f.write(suffix if suffix else ";\n")
    else:
        print("  [-] 未发现需要修复的目标插件参数。")

def step2_patch_index_html():
    """向 index.html 注入环境欺骗、PWA、虚拟手柄，并物理阉割引擎 PC 模式"""
    print("\n>>> 步骤 2: 注入跨平台兼容补丁、移动端手柄与引擎物理降维打击...")
    index_path = os.path.join(WWW_DIR, "index.html")
    
    # ==========================================
    # 阶段一：处理 index.html (注入假环境与 UI)
    # ==========================================
    if not os.path.exists(index_path):
        print("  [!] 致命错误：找不到 index.html，流水线强制终止！")
        sys.exit(1)

    with open(index_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 1. Polyfill 注入 (欺骗环境 - 终极 Proxy 黑洞版)
    mock_begin = "<!-- [Nix Inject Begin] -->"
    mock_end = "<!-- [Nix Inject End] -->"
    mock_script = """
        <!-- [Nix Inject Begin] -->
        <script type="text/javascript">
            // 1. 提前抢占底层环境判断！
            window.Utils = window.Utils || {};
            window.Utils.isNwjs = function() { return false; };
            window.Utils.isMobileDevice = function() { return true; }; // 顺便开启移动端优化
            
            window.process = {
                env: {},
                mainModule: { filename: 'index.html' },
                platform: 'browser',
                arch: 'x64',  // 伪造 64 位系统架构
                versions: { node: '14.16.0', nw: '0.49.2' }, // 伪造较新的 PC 引擎版本号，防止插件嫌弃环境太老
                argv: [], // 伪造空启动参数，避免 includes 报错
                execPath: '/Game.exe', // 伪造可执行文件路径
                cwd: function() { return '/'; }, // 伪造根目录
                chdir: function(dir) { return; }, // 拦截更改目录指令
                exit: function() {
                    console.warn('[Nix 防火墙] 拦截了退出游戏指令');
                    // 网页端无法直接关闭标签页，可以重定向到主页，或者直接忽略
                    // window.location.href = '/';
                },
                on: function(event, callback) {
                    console.warn('[Nix 防火墙] 拦截并挂起了系统级事件监听: ' + event);
                    return this; // 返回 this 以支持链式调用，例如 process.on().on()
                },
                uptime: function() { return performance.now() / 1000; }, // 伪造开机时间，防某些计时插件报错
                // 高精度计时器伪造 (专治 Effekseer 粒子特效引擎崩溃)
                hrtime: function(prev) {
                    var now = performance.now(); // 浏览器自带高精度毫秒
                    var sec = Math.floor(now / 1000);
                    var nano = Math.floor((now % 1000) * 1000000);
                    if (prev) {
                        sec -= prev[0];
                        nano -= prev[1];
                        if (nano < 0) {
                            sec--;
                            nano += 1000000000;
                        }
                    }
                    return [sec, nano];
                }
            };

            // 2. [究极防弹形态] 完美模拟 NW.js 环境并带有雷达监控
            const createNwMock = () => {
                const mock = new Proxy(function() {}, {
                    get: (target, prop) => {
                        if (typeof prop === 'symbol') {
                            if (prop === Symbol.toPrimitive) return (hint) => hint === 'number' ? 0 : '';
                            return Reflect.get(target, prop);
                        }
                        // 遇到特殊的方法，在浏览器的控制台打印出来
                        if (typeof prop === 'string' && prop !== 'then') {
                            console.warn(`[Nix 防火墙] 游戏尝试调用了不受支持的 PC 模块/属性: ${prop}`);
                        }
                        if (prop === 'then') return undefined;
                        if (prop === 'toString' || prop === 'valueOf') return () => '';
                        if (prop === 'toJSON') return () => ({});
                        if (prop === 'isMaximized') return false;
                        if (prop === 'argv') return [];
                        return mock;
                    },
                    apply: () => mock,       
                    construct: () => mock    
                });
                return mock;
            };
            window.nw = createNwMock();
            
            // 3. 劫持 require，同时给 fs 加上防空指针保护
            window.require = function(moduleName) {
                if (moduleName === 'fs') return { 
                    existsSync: function(){return false;}, 
                    // 核心修改：返回 "{}" 而不是 ""，如果插件强行读取，JSON.parse 不会报错产生 null！
                    readFileSync: function(){return "{}";}, 
                    writeFileSync: function(){return true;}, 
                    mkdirSync: function(){return true;}, 
                    statSync: function(){return {isDirectory: function(){return false;}};} 
                };
                if (moduleName === 'path') return { join: function(){return Array.from(arguments).join('/');}, dirname: function(){return '';}, basename: function(p){return p.split('/').pop();}, extname: function(p){var match=p.match(/\\.[^.]+$/); return match?match[0]:'';} };
                if (moduleName === 'nw.gui') return window.nw;
                return {};
            };

            // 4. 提前解锁媒体上下文，避免 iOS/移动浏览器在动画 SE 首次播放时报 NotAllowedError
            (function() {
                let unlocked = false;
                const tryUnlockMedia = function() {
                    if (unlocked) return;
                    try {
                        if (window.WebAudio && WebAudio._context && WebAudio._context.state === 'suspended') {
                            const result = WebAudio._context.resume();
                            if (result && typeof result.catch === 'function') {
                                result.catch(function() {});
                            }
                        }
                    } catch (e) {}
                    unlocked = true;
                    unlockEvents.forEach(function(type) {
                        document.removeEventListener(type, tryUnlockMedia, true);
                    });
                };
                const unlockEvents = ['pointerdown', 'touchstart', 'touchend', 'mousedown', 'keydown'];
                unlockEvents.forEach(function(type) {
                    document.addEventListener(type, tryUnlockMedia, true);
                });
            })();

        </script>
        <!-- [Nix Inject End] -->
        """
    if mock_begin in html_content and mock_end in html_content:
        html_content = re.sub(
            r'<!-- \[Nix Inject Begin\] -->.*?<!-- \[Nix Inject End\] -->',
            lambda _m: mock_script,
            html_content,
            count=1,
            flags=re.DOTALL
        )
        print("  [+] Proxy 监控防火墙已更新。")
    elif "window.require = function" not in html_content:
        # 使用正则，无视大小写寻找第一个 <script，并插在它前面
        html_content = re.sub(
            r'(<script)',
            lambda m: mock_script + '\n' + m.group(1),
            html_content,
            count=1,
            flags=re.IGNORECASE
        )
        print("  [+] Proxy 监控防火墙注入成功！")

    debug_begin = "<!-- [Nix Audio Debug Begin] -->"
    debug_end = "<!-- [Nix Audio Debug End] -->"
    debug_script = """
        <!-- [Nix Audio Debug Begin] -->
        <script type="text/javascript">
            (function() {
                const search = new URLSearchParams(window.location.search);
                const explicitDebug = search.get('audioDebug') === '1';
                try {
                    if (explicitDebug) {
                        sessionStorage.setItem('AUDIO_DEBUG', '1');
                        localStorage.removeItem('AUDIO_DEBUG');
                    } else {
                        sessionStorage.removeItem('AUDIO_DEBUG');
                        localStorage.removeItem('AUDIO_DEBUG');
                    }
                } catch (e) {}
                const debugEnabled = explicitDebug || sessionStorage.getItem('AUDIO_DEBUG') === '1';
                if (!debugEnabled) {
                    return;
                }

                try {
                    alert("audio debug injected");
                } catch (e) {}

                const MAX_LOGS = 200;
                const STORAGE_KEY = 'AUDIO_DEBUG_LOGS';
                const startTime = Date.now();
                const logs = [];
                let panel;
                let wrap;
                let booted = false;

                function safeStringify(value) {
                    try {
                        return JSON.stringify(value);
                    } catch (e) {
                        return String(value);
                    }
                }

                function nowLabel() {
                    return ((Date.now() - startTime) / 1000).toFixed(2) + 's';
                }

                function persist() {
                    try {
                        localStorage.setItem(STORAGE_KEY, JSON.stringify(logs.slice(-MAX_LOGS)));
                    } catch (e) {}
                }

                function appendLine() {
                    if (!panel) return;
                    panel.textContent = logs.join('\\n');
                    panel.scrollTop = panel.scrollHeight;
                }

                function audioDebugLog(tag, detail) {
                    const line = '[' + nowLabel() + '] ' + tag + ' ' + detail;
                    logs.push(line);
                    if (logs.length > MAX_LOGS) {
                        logs.shift();
                    }
                    console.log('[AUDIO_DEBUG]', line);
                    appendLine();
                    persist();
                }

                window.__audioDebugLog = audioDebugLog;

                function ensureVisible() {
                    if (!wrap || !document.documentElement.contains(wrap)) {
                        booted = false;
                        setTimeout(bootPanel, 100);
                        return;
                    }
                    wrap.style.zIndex = '2147483647';
                    wrap.style.display = 'block';
                }

                function bootPanel() {
                    if (booted) {
                        ensureVisible();
                        return;
                    }
                    const body = document.body || document.documentElement;
                    if (!body) {
                        setTimeout(bootPanel, 100);
                        return;
                    }

                    wrap = document.createElement('div');
                    wrap.id = 'audio-debug-wrap';
                    wrap.style.cssText = [
                        'position:fixed',
                        'left:8px',
                        'right:8px',
                        'top:8px',
                        'z-index:2147483647',
                        'background:rgba(0,0,0,0.92)',
                        'color:#7CFFB2',
                        'border:2px solid rgba(255,99,71,0.9)',
                        'border-radius:12px',
                        'font:12px/1.4 monospace',
                        'padding:8px',
                        'max-height:46vh',
                        'box-shadow:0 8px 24px rgba(0,0,0,0.45)',
                        'pointer-events:auto'
                    ].join(';');

                    const toolbar = document.createElement('div');
                    toolbar.style.cssText = 'display:flex;gap:6px;margin-bottom:6px;align-items:center;';

                    const title = document.createElement('div');
                    title.textContent = 'AUDIO DEBUG ON';
                    title.style.cssText = 'font-weight:bold;color:#ff8a7a;flex:1;font-size:13px;';
                    toolbar.appendChild(title);

                    const copyBtn = document.createElement('button');
                    copyBtn.textContent = 'Copy';
                    copyBtn.style.cssText = 'font:inherit;padding:4px 8px;';
                    copyBtn.onclick = async function() {
                        const text = logs.join('\\n');
                        try {
                            if (navigator.clipboard && navigator.clipboard.writeText) {
                                await navigator.clipboard.writeText(text);
                                audioDebugLog('ui.copy', 'clipboard ok');
                            } else {
                                audioDebugLog('ui.copy', 'clipboard unavailable');
                            }
                        } catch (e) {
                            audioDebugLog('ui.copy.error', e && e.message ? e.message : String(e));
                        }
                    };
                    toolbar.appendChild(copyBtn);

                    const clearBtn = document.createElement('button');
                    clearBtn.textContent = 'Clear';
                    clearBtn.style.cssText = 'font:inherit;padding:4px 8px;';
                    clearBtn.onclick = function() {
                        logs.length = 0;
                        persist();
                        appendLine();
                        audioDebugLog('ui.clear', 'cleared');
                    };
                    toolbar.appendChild(clearBtn);

                    const hideBtn = document.createElement('button');
                    hideBtn.textContent = 'Hide';
                    hideBtn.style.cssText = 'font:inherit;padding:4px 8px;';
                    hideBtn.onclick = function() {
                        const hidden = panel.style.display === 'none';
                        panel.style.display = hidden ? 'block' : 'none';
                        hideBtn.textContent = hidden ? 'Hide' : 'Show';
                    };
                    toolbar.appendChild(hideBtn);

                    panel = document.createElement('pre');
                    panel.id = 'audio-debug-panel';
                    panel.style.cssText = [
                        'margin:0',
                        'white-space:pre-wrap',
                        'word-break:break-word',
                        'overflow:auto',
                        'max-height:32vh'
                    ].join(';');

                    wrap.appendChild(toolbar);
                    wrap.appendChild(panel);
                    body.appendChild(wrap);
                    booted = true;

                    try {
                        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
                        if (Array.isArray(saved)) {
                            saved.forEach(function(line) { logs.push(line); });
                        }
                    } catch (e) {}
                    appendLine();
                    audioDebugLog('debug.boot', navigator.userAgent);
                    ensureVisible();
                }

                bootPanel();
                window.addEventListener('load', bootPanel);
                document.addEventListener('DOMContentLoaded', bootPanel);
                setInterval(ensureVisible, 1000);

                window.addEventListener('error', function(event) {
                    const message = event.error && event.error.stack ? event.error.stack : (event.message || 'unknown');
                    audioDebugLog('window.error', message);
                });

                document.addEventListener('visibilitychange', function() {
                    audioDebugLog('visibility', document.visibilityState);
                });

                window.addEventListener('pagehide', function() {
                    audioDebugLog('pagehide', 'fired');
                });

                window.addEventListener('pageshow', function() {
                    audioDebugLog('pageshow', 'fired');
                });

                function hookWhenReady() {
                    if (!window.AudioManager || !window.WebAudio) {
                        setTimeout(hookWhenReady, 500);
                        return;
                    }

                    try {
                        audioDebugLog('audio.ext', typeof AudioManager.audioFileExt === 'function' ? AudioManager.audioFileExt() : 'unknown');
                    } catch (e) {
                        audioDebugLog('audio.ext.error', e && e.message ? e.message : String(e));
                    }

                    try {
                        const probe = new WebAudio('audio/bgm/__debug_probe__.ogg');
                        const decoderMode = typeof probe._shouldUseDecoder === 'function' ? probe._shouldUseDecoder() : 'unknown';
                        audioDebugLog('audio.decoder', safeStringify({
                            shouldUseDecoder: decoderMode,
                            canPlayOgg: typeof Utils !== 'undefined' && typeof Utils.canPlayOgg === 'function' ? Utils.canPlayOgg() : 'unknown',
                            hasVorbisDecoder: typeof VorbisDecoder === 'function'
                        }));
                        if (typeof probe.destroy === 'function') {
                            probe.destroy();
                        }
                    } catch (e) {
                        audioDebugLog('audio.decoder.error', e && e.message ? e.message : String(e));
                    }

                    if (window.WebAudio._context && window.WebAudio._context.addEventListener) {
                        window.WebAudio._context.addEventListener('statechange', function() {
                            audioDebugLog('context.state', window.WebAudio._context.state);
                        });
                        audioDebugLog('context.init', window.WebAudio._context.state || 'unknown');
                    }

                    const originalCreateBuffer = AudioManager.createBuffer;
                    AudioManager.createBuffer = function(folder, name) {
                        const buffer = originalCreateBuffer.apply(this, arguments);
                        try {
                            audioDebugLog('createBuffer', folder + ' | ' + name + ' | ' + (buffer ? buffer._url : 'no-buffer'));
                        } catch (e) {}
                        return buffer;
                    };

                    const originalPlayBgm = AudioManager.playBgm;
                    AudioManager.playBgm = function(bgm, pos) {
                        audioDebugLog('playBgm', safeStringify({name: bgm && bgm.name, pos: pos, volume: bgm && bgm.volume, pitch: bgm && bgm.pitch}));
                        return originalPlayBgm.apply(this, arguments);
                    };

                    const originalPlayBgs = AudioManager.playBgs;
                    AudioManager.playBgs = function(bgs, pos) {
                        audioDebugLog('playBgs', safeStringify({name: bgs && bgs.name, pos: pos, volume: bgs && bgs.volume, pitch: bgs && bgs.pitch}));
                        return originalPlayBgs.apply(this, arguments);
                    };

                    const originalStopBgm = AudioManager.stopBgm;
                    AudioManager.stopBgm = function() {
                        audioDebugLog('stopBgm', this._currentBgm ? safeStringify(this._currentBgm) : 'none');
                        return originalStopBgm.apply(this, arguments);
                    };

                    const originalStopBgs = AudioManager.stopBgs;
                    AudioManager.stopBgs = function() {
                        audioDebugLog('stopBgs', this._currentBgs ? safeStringify(this._currentBgs) : 'none');
                        return originalStopBgs.apply(this, arguments);
                    };

                    const originalOnError = WebAudio.prototype._onError;
                    WebAudio.prototype._onError = function() {
                        audioDebugLog('webaudio.error', this._url || 'unknown-url');
                        return originalOnError.apply(this, arguments);
                    };

                    const originalOnDecode = WebAudio.prototype._onDecode;
                    WebAudio.prototype._onDecode = function(buffer) {
                        const duration = buffer && typeof buffer.duration === 'number' ? buffer.duration.toFixed(3) : 'n/a';
                        audioDebugLog('webaudio.decode', (this._url || 'unknown-url') + ' | duration=' + duration);
                        return originalOnDecode.apply(this, arguments);
                    };

                    const originalStartLoading = WebAudio.prototype._startLoading;
                    WebAudio.prototype._startLoading = function() {
                        audioDebugLog('webaudio.load', this._realUrl ? this._realUrl() : (this._url || 'unknown-url'));
                        return originalStartLoading.apply(this, arguments);
                    };

                    const originalPlay = WebAudio.prototype.play;
                    WebAudio.prototype.play = function(loop, offset) {
                        audioDebugLog('webaudio.play', safeStringify({url: this._url, loop: loop, offset: offset, loaded: this._isLoaded, error: this._isError}));
                        return originalPlay.apply(this, arguments);
                    };

                    audioDebugLog('debug.hook', 'audio hooks installed');
                }

                hookWhenReady();
            })();
        </script>
        <!-- [Nix Audio Debug End] -->
        """
    if debug_begin in html_content and debug_end in html_content:
        html_content = re.sub(
            r'<!-- \[Nix Audio Debug Begin\] -->.*?<!-- \[Nix Audio Debug End\] -->',
            lambda _m: debug_script,
            html_content,
            count=1,
            flags=re.DOTALL
        )
        print("  [+] 音频调试面板已更新。")
    else:
        html_content = re.sub(
            r'(<script)',
            lambda m: debug_script + '\n' + m.group(1),
            html_content,
            count=1,
            flags=re.IGNORECASE
        )
        print("  [+] 音频调试面板注入成功。")

    # 2. PWA 标签注入 (修复现代浏览器弃用警告)
    pwa_meta = '\n<meta name="mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">\n'
    if "apple-mobile-web-app-capable" not in html_content:
        # 使用正则，无视大小写寻找 </head>
        html_content = re.sub(r'(</head>)', pwa_meta + r'\1', html_content, flags=re.IGNORECASE)

    # 3. [核心修改] 从外部文件读取并注入虚拟手柄
    if 'id="v-pad"' not in html_content:
        # 删掉那个 globals() 判断，直接判断文件存不存在！
        if os.path.exists(VPAD_HTML_PATH):
            with open(VPAD_HTML_PATH, 'r', encoding='utf-8') as vpad_f:
                gamepad_code = vpad_f.read()
            html_content = html_content.replace('</body>', '\n' + gamepad_code + '\n</body>')
            print("  [+] 从 vpad.html 成功读取并注入虚拟手柄模块！")
        else:
            print(f"  [-] 未发现手柄文件，本次部署将跳过虚拟手柄注入。")
    # ==========================================
    # 💥 关键修复：将内存中修改好的 html_content 覆写回文件
    # ==========================================
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("  [+] index.html 注入内容已成功物理落盘！")
    # ==========================================
    # 阶段二：物理篡改引擎核心 (锁定 Web 异步存储模式)
    # ==========================================
    js_dir = os.path.join(WWW_DIR, "js")
    target_files = ["rmmz_managers.js", "rpg_managers.js"]
    
    patched = False
    for filename in target_files:
        file_path = os.path.join(js_dir, filename)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 避免重复追加
            if "[Nix Pipeline Inject]" not in content:
                with open(file_path, "a", encoding="utf-8") as f:
                    hard_lock_code = """\n
// ==========================================
// [Nix Pipeline Inject] 物理级强制 Web 存储锁
// 彻底覆盖原引擎的 isNwjs 和 isLocalMode 判定！
// ==========================================
if (typeof Utils !== 'undefined') {
    Utils.isNwjs = function() { return false; };
}
if (typeof StorageManager !== 'undefined') {
    StorageManager.isLocalMode = function() { return false; };
}
if (typeof AudioManager !== 'undefined') {
    AudioManager.audioFileExt = function() {
        const agent = navigator.userAgent || "";
        const isIOSDevice =
            /iPhone|iPad|iPod/i.test(agent) ||
            (navigator.platform === "MacIntel" && typeof navigator.maxTouchPoints === "number" && navigator.maxTouchPoints > 1);
        return isIOSDevice ? ".m4a" : ".ogg";
    };
}
console.log("🔒 [Nix 降维打击] 引擎已物理锁死 Web 异步存档模式，PC 路线被切断！");
"""
                    f.write(hard_lock_code)
                print(f"  [√] 成功物理篡改引擎底层文件: {filename}")
            else:
                print(f"  [-] 引擎文件 {filename} 已被锁定，跳过。")
            patched = True
            
    if not patched:
        print("  [!] 警告：未找到 managers.js 核心文件，当前可能不是标准 MV/MZ 工程！")

    core_path = os.path.join(js_dir, "rmmz_managers.js")
    if os.path.exists(core_path):
        with open(core_path, "r", encoding="utf-8") as f:
            managers_content = f.read()

        if "[Nix Pipeline Inject] iOS m4a decoder guard" not in managers_content:
            with open(core_path, "a", encoding="utf-8") as f:
                decoder_guard_code = """\n
// ==========================================
// [Nix Pipeline Inject] iOS m4a decoder guard
// m4a 必须走浏览器原生解码，不能误进 VorbisDecoder(ogg 专用)。
// ==========================================
(function() {
    if (typeof WebAudio === 'undefined') return;
    const _WebAudio_shouldUseDecoder = WebAudio.prototype._shouldUseDecoder;
    WebAudio.prototype._shouldUseDecoder = function() {
        const url = String(this._url || '').toLowerCase();
        if (url.endsWith('.m4a')) {
            return false;
        }
        return _WebAudio_shouldUseDecoder.call(this);
    };
})();
"""
                f.write(decoder_guard_code)
            print("  [√] 已注入 iOS m4a 解码保护补丁: rmmz_managers.js")
        else:
            print("  [-] rmmz_managers.js 已存在 iOS m4a 解码保护补丁，跳过。")

    sprites_path = os.path.join(js_dir, "rmmz_sprites.js")
    if os.path.exists(sprites_path):
        with open(sprites_path, "r", encoding="utf-8") as f:
            sprites_content = f.read()

        if "[Nix Pipeline Inject] Mobile animation throttle" not in sprites_content:
            with open(sprites_path, "a", encoding="utf-8") as f:
                animation_throttle_code = """\n
// ==========================================
// [Nix Pipeline Inject] Mobile animation throttle
// 限制移动端短时间内连续启动 Effekseer 动画，降低 iOS 上的随机 RangeError。
// ==========================================
(function() {
    if (typeof Sprite_Animation === "undefined") return;
    const _Sprite_Animation_canStart = Sprite_Animation.prototype.canStart;
    const throttleState = {
        lastStartAt: 0,
        minIntervalMs: 80
    };

    Sprite_Animation.prototype.canStart = function() {
        if (!_Sprite_Animation_canStart.call(this)) {
            return false;
        }
        if (!(Utils && Utils.isMobileDevice && Utils.isMobileDevice())) {
            return true;
        }
        const now = performance.now();
        if (now - throttleState.lastStartAt < throttleState.minIntervalMs) {
            this._playing = false;
            return false;
        }
        throttleState.lastStartAt = now;
        return true;
    };
})();
"""
                f.write(animation_throttle_code)
            print("  [√] 已注入移动端动画限流补丁: rmmz_sprites.js")
        else:
            print("  [-] rmmz_sprites.js 已存在动画限流补丁，跳过。")
    else:
        print("  [!] 警告：未找到 rmmz_sprites.js，跳过动画限流补丁。")
        
    print("  [√] 步骤 2 执行完毕，游戏运行环境已固化！")

def main():
    print("="*50)
    print(" RPG Maker Web 全自动部署处理流 (MV/MZ 兼容版)")
    print("="*50)
    
    prepare_www_workspace(BASE_DIR, WWW_DIR)
    clean_pc_build(WWW_DIR)
    apply_mtools_translation(BASE_DIR, WWW_DIR)
    apply_patch(PATCH_ZIP, WWW_DIR)
    step2_patch_index_html()
    key = patch_system_json(SYSTEM_JSON_PATH)
    decrypt_assets(WWW_DIR, key)
    convert_audio_to_m4a(WWW_DIR)
    sanitize_audio_filenames(WWW_DIR)
    validate_audio_consistency(WWW_DIR, SYSTEM_JSON_PATH)
    convert_video_to_mp4(WWW_DIR)
    patch_problematic_plugin_params()
    fix_resource_percent_symbols(WWW_DIR)
    
    final_project_name = get_valid_project_name(GAME_NAME)
    credentials = load_cloudflare_credentials(RUNTIME.cloudflare_credentials_path)
    deploy_to_cloudflare(final_project_name, RUNTIME, credentials)
    
    print("\n" + "="*50)
    
    print(f"\n 部署大功告成！游戏 [{GAME_NAME}] 已经在线上就绪！")
    print("="*50)

if __name__ == "__main__":
    main()
