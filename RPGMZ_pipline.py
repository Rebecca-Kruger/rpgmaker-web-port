#RZH
import os
import json
import subprocess
import zipfile
import sys
import re
import shutil
import glob

# ==========================================
# 1. 基础环境配置
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WWW_DIR = os.path.join(BASE_DIR, "www")
PATCH_ZIP = os.path.join(BASE_DIR, "patch.zip")
SYSTEM_JSON_PATH = os.path.join(WWW_DIR, "data", "System.json")
# [新增] 虚拟手柄文件的路径
VPAD_HTML_PATH = os.path.join(BASE_DIR, "vpad.html") 

# ==========================================
# 2. 动态 CI/CD 部署配置
# ==========================================
if len(sys.argv) < 2:
    print("❌ 错误：缺少游戏文件夹名称！")
    print("💡 用法: sudo python3 pipeline.py <游戏名> [--single-deploy]")
    sys.exit(1)

GAME_NAME = sys.argv[1]
SINGLE_DEPLOY = "--single-deploy" in sys.argv[2:]
SAVE_PREFIX = GAME_NAME.upper() + "_"
DEPLOY_DIR = os.path.join("/var/www/html/games", GAME_NAME)
LOBBY_HTML_PATH = "/var/www/html/index.html"

# ==========================================
# CloudFlare 部署全局变量
# ==========================================
CF_ACCOUNT_ID = "448a6555b9fa214fda6725749e292863"
CF_API_TOKEN = "T-nHUJNLbuvvX9N9dxqsWlbKd4TbULV21sWWrIfp"
CF_KV_NAMESPACE_ID = "e4f91a136fb149a0a2e52a829af77d31"

# ==========================================
# 核心流水线函数
# ==========================================

def detect_game_source_dir():
    """检测完整 PC 游戏目录，并作为 www 工作区来源。"""
    candidates = []
    non_www_candidates = []
    for entry in os.listdir(BASE_DIR):
        path = os.path.join(BASE_DIR, entry)
        if not os.path.isdir(path):
            continue
        if entry in [".git", ".wrangler", "__pycache__", "www"]:
            continue
        if os.path.exists(os.path.join(path, "index.html")) and \
           os.path.isdir(os.path.join(path, "js")) and \
           os.path.isdir(os.path.join(path, "data")):
            candidates.append(path)
            if os.path.abspath(path) != os.path.abspath(WWW_DIR):
                non_www_candidates.append(path)

    if len(non_www_candidates) == 1:
        return non_www_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    if os.path.exists(WWW_DIR):
        return WWW_DIR
    return None

def prepare_www_workspace():
    """将完整 PC 目录复制成标准 www 工作目录。"""
    source_dir = detect_game_source_dir()
    if not source_dir:
        print("  [!] 未找到可用的游戏源目录。请提供 www 或完整 PC 游戏目录。")
        sys.exit(1)

    if os.path.abspath(source_dir) == os.path.abspath(WWW_DIR):
        print(f"  [+] 使用现有 www 工作目录: {WWW_DIR}")
        return

    print(f"\n>>> 预处理: 从源目录构建 www 工作区...")
    print(f"  [+] 源目录: {source_dir}")
    if os.path.exists(WWW_DIR):
        shutil.rmtree(WWW_DIR)
    shutil.copytree(source_dir, WWW_DIR)
    print(f"  [+] 已复制到工作目录: {WWW_DIR}")

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

def step0_clean_pc_build():
    """步骤 0: 清洗 PC 版冗余文件 (剥离 NW.js 外壳)，提取纯净 Web 核心"""
    print("\n🧹 [Step 0] 开始清洗 PC 版冗余文件 (剥离 NW.js 外壳)...")
    
    dirs_to_remove = ["locales", "swiftshader", "save"]
    for d in dirs_to_remove:
        dir_path = os.path.join(WWW_DIR, d)
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"   🗑️ 已销毁目录: {d}/")
            except Exception as e:
                print(f"   ⚠️ 无法删除目录 {d}/: {e}")

    files_to_remove = ["*.exe", "*.dll", "*.pak", "*.bin", "*.dat", "package.json"]
    clean_count = 0
    for pattern in files_to_remove:
        for file_path in glob.glob(os.path.join(WWW_DIR, pattern)):
            try:
                os.remove(file_path)
                print(f"   🗑️ 已销毁文件: {os.path.basename(file_path)}")
                clean_count += 1
            except Exception as e:
                print(f"   ⚠️ 无法删除 {os.path.basename(file_path)}: {e}")
                
    if clean_count == 0:
        print("   ✨ 未发现冗余文件，当前已经是纯净 Web 环境。")
    else:
        print(f"   ✅ 清洗完毕！共清理 {clean_count} 个冗余文件。")

def step0_apply_mtools_translation():
    """外科手术式 MTools 汉化注入"""
    cn_json_path = os.path.join(BASE_DIR, "CN.json")
    if not os.path.exists(cn_json_path):
        print("\n [-] 未发现 CN.json，跳过 MTools 文本汉化注入。")
        return

    print(f"\n>>> 发现 CN.json，正在启动外科手术级底层文本注入...")
    try:
        with open(cn_json_path, 'r', encoding='utf-8') as f:
            translation_dict = json.load(f)
    except Exception as e:
        print(f"  [!] CN.json 解析失败: {e}")
        return

    def translate_node(node):
        if not isinstance(node, dict) and not isinstance(node, list):
            return node
        if isinstance(node, dict):
            new_dict = {}
            is_audio_obj = 'volume' in node and 'pitch' in node
            for k, v in node.items():
                if isinstance(v, str):
                    if is_audio_obj and k == 'name':
                        new_dict[k] = v
                    elif k in ['name', 'description', 'message1', 'message2', 'message3', 'message4', 'profile', 'nickname', 'note']:
                        new_dict[k] = translation_dict.get(v, v)
                    else:
                        new_dict[k] = v
                elif isinstance(v, list):
                    if k in ['elements', 'skillTypes', 'weaponTypes', 'armorTypes', 'equipTypes', 'basic', 'params', 'commands']:
                        new_dict[k] = [translation_dict.get(item, item) if isinstance(item, str) else translate_node(item) for item in v]
                    elif k == 'parameters' and node.get('code') in [401, 405]:
                        new_dict[k] = [translation_dict.get(item, item) if isinstance(item, str) else translate_node(item) for item in v]
                    elif k == 'parameters' and node.get('code') == 102:
                        new_params = []
                        for i, param in enumerate(v):
                            if i == 0 and isinstance(param, list):
                                new_params.append([translation_dict.get(choice, choice) if isinstance(choice, str) else choice for choice in param])
                            else:
                                new_params.append(translate_node(param))
                        new_dict[k] = new_params
                    else:
                        new_dict[k] = translate_node(v)
                elif isinstance(v, dict):
                    if k == 'messages':
                        new_dict[k] = {mk: translation_dict.get(mv, mv) if isinstance(mv, str) else translate_node(mv) for mk, mv in v.items()}
                    else:
                        new_dict[k] = translate_node(v)
                else:
                    new_dict[k] = v
            return new_dict
        elif isinstance(node, list):
            return [translate_node(item) for item in node]

    data_dir = os.path.join(WWW_DIR, "data")
    if not os.path.exists(data_dir):
        return

    modified_files = 0
    for file in os.listdir(data_dir):
        if file.endswith(".json"):
            filepath = os.path.join(data_dir, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    game_data = json.load(f)
                translated_data = translate_node(game_data)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(translated_data, f, ensure_ascii=False, separators=(',', ':'))
                modified_files += 1
            except Exception:
                pass
    print(f"  [√] 注入完成！处理了 {modified_files} 个数据文件。")

def step1_apply_patch():
    """解压汉化补丁并覆盖到 www 目录"""
    print("\n>>> 步骤 1: 检查汉化补丁...")
    if not os.path.exists(PATCH_ZIP):
        print("  [-] 未发现 patch.zip，跳过补丁覆盖。")
        return
    print(f"  [+] 发现 {PATCH_ZIP}，正在解压...")
    with zipfile.ZipFile(PATCH_ZIP, 'r') as zip_ref:
        zip_ref.extractall(WWW_DIR)
    print("  [+] 汉化补丁合并完成！")
    
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

def step3_patch_system_json():
    """解析 System.json 关闭加密，并提取密钥"""
    print("\n>>> 步骤 3: 解析 System.json 并提取密钥...")
    if not os.path.exists(SYSTEM_JSON_PATH):
        print("  [!] 找不到 System.json，请确认是否为标准的 MV/MZ 游戏。")
        return None

    with open(SYSTEM_JSON_PATH, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    key_hex = data.get("encryptionKey", "")
    modified = False
    if data.get("hasEncryptedImages"):
        data["hasEncryptedImages"] = False
        modified = True
    if data.get("hasEncryptedAudio"):
        data["hasEncryptedAudio"] = False
        modified = True
        
    if modified:
        with open(SYSTEM_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        print("  [+] 成功关闭 System.json 中的加密标志。")

    if key_hex:
        print(f"  [+] 提取到 32 位密钥: {key_hex}")
        return bytes.fromhex(key_hex)
    return None

def decrypt_single_file(file_path, key_bytes, target_ext):
    """处理单个加密文件的异或解密"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)
            if b'RPG' not in header:
                return False
            encrypted_head = f.read(16)
            actual_len = len(encrypted_head)  # 获取实际读到的字节数（防残疾文件）
            decrypted_head = bytearray(actual_len)  # 动态创建对应长度的数组
            for i in range(actual_len):  # 只循环实际拥有的长度
                decrypted_head[i] = encrypted_head[i] ^ key_bytes[i]
            rest_data = f.read()
            
        new_path = file_path.rsplit('.', 1)[0] + target_ext
        with open(new_path, 'wb') as f:
            f.write(decrypted_head)
            f.write(rest_data)
            
        os.remove(file_path)
        return True
    except Exception as e:
        print(f"  [!] 解密失败 {file_path}: {str(e)}")
        return False

def step4_decrypt_assets(key_bytes):
    """批量解密资源文件 (适配 MZ 与 MV 后缀)"""
    print("\n>>> 步骤 4: 批量全速解密资源文件 (兼容 MZ/MV)...")
    if not key_bytes:
        print("  [-] 缺少密钥，跳过解密。")
        return

    img_count = 0
    audio_count = 0

    for root, _, files in os.walk(WWW_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.png_') or file.endswith('.rpgmvp'):
                if decrypt_single_file(file_path, key_bytes, '.png'):
                    img_count += 1
            elif file.endswith('.ogg_') or file.endswith('.rpgmvo'):
                if decrypt_single_file(file_path, key_bytes, '.ogg'):
                    audio_count += 1
            elif file.endswith('.m4a_'):
                if decrypt_single_file(file_path, key_bytes, '.m4a'):
                    audio_count += 1

    print(f"  [+] 全量解密完成！共安全解密了 {img_count} 张图片，{audio_count} 个音频。")

def step5_convert_audio_to_m4a():
    """将 ogg 批量转码为 m4a"""
    print("\n>>> 步骤 5: 转换音频格式为 iOS 兼容的 m4a...")
    audio_dir = os.path.join(WWW_DIR, "audio")
    if not os.path.exists(audio_dir):
        return

    converted_count = 0
    synthesized_silence_count = 0

    def synthesize_silence_audio(target_path, lower_file):
        """为 0 byte 音频合成一段极短静音，避免 ffmpeg 因空文件直接失败。"""
        if lower_file.endswith('.ogg'):
            cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                '-t', '0.3',
                '-c:a', 'libvorbis',
                target_path,
                '-loglevel', 'error'
            ]
        elif lower_file.endswith('.wav'):
            cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                '-t', '0.3',
                '-c:a', 'pcm_s16le',
                target_path,
                '-loglevel', 'error'
            ]
        else:
            return False

        subprocess.run(cmd, check=True)
        return True

    """for root, _, files in os.walk(audio_dir):
        for file in files:
            if file.endswith('.ogg'):
                ogg_path = os.path.join(root, file)
                m4a_path = ogg_path.rsplit('.', 1)[0] + '.m4a'
                if not os.path.exists(m4a_path):
                    cmd = ['ffmpeg', '-y', '-i', ogg_path, '-c:a', 'aac', '-b:a', '128k', m4a_path, '-loglevel', 'error']
                    try:
                        subprocess.run(cmd, check=True)
                        converted_count += 1
                    except subprocess.CalledProcessError:
                        pass
    """
    for root, _, files in os.walk(audio_dir):
        for file in files:
            # 统一转为小写进行判断，防止出现 .WAV 或 .Ogg 漏网
            lower_file = file.lower()
            
            # 捕获 .ogg 和 .wav 文件
            if lower_file.endswith('.ogg') or lower_file.endswith('.wav'):
                orig_path = os.path.join(root, file)
                base_name = file.rsplit('.', 1)[0]
                m4a_path = os.path.join(root, base_name + '.m4a')

                try:
                    if os.path.getsize(orig_path) == 0:
                        print(f"  [!] 检测到 0 byte 音频，正在补静音: {file}")
                        synthesize_silence_audio(orig_path, lower_file)
                        synthesized_silence_count += 1
                except subprocess.CalledProcessError:
                    print(f"  [!] 0 byte 音频静音补写失败，流水线终止: {file}")
                    raise
                
                # 只有当同名 m4a 不存在时才执行 FFmpeg 转换，大幅节省重复部署的时间
                if not os.path.exists(m4a_path):
                    cmd = ['ffmpeg', '-y', '-i', orig_path, '-c:a', 'aac', '-b:a', '128k', m4a_path, '-loglevel', 'error']
                    try:
                        subprocess.run(cmd, check=True)
                        converted_count += 1
                    except subprocess.CalledProcessError:
                        print(f"  [!] 转码失败跳过: {file}")
                        continue  # 转码失败则跳过后续删除步骤
                
                # ====== 核心魔法：针对 WAV 的专属降维打击 ======
                if lower_file.endswith('.wav'):
                    # 1. 无情删掉原来那个可能超过 25MB 的原始无损巨型 WAV 文件
                    os.remove(orig_path)
                    
                    # 2. 狸猫换太子：把刚转好的小体积 m4a 复制一份，强行改名为原来的 WAV 名字！
                    shutil.copy2(m4a_path, orig_path)
                    print(f"  [伪装成功] 已将巨型 {file} 替换为 128k aac 内核，安全越过 25MB 红线！")
    print(f"  [+] 音频转码结束，处理了 {converted_count} 个文件，补写了 {synthesized_silence_count} 个空白音频。")

def step5_sanitize_audio_filenames():
    """将非 ASCII 音频文件名改为安全 ASCII，并同步重写数据引用。"""
    print("\n>>> 步骤 5.3: ASCII 化音频文件名并重写引用...")
    audio_dir = os.path.join(WWW_DIR, "audio")
    data_dir = os.path.join(WWW_DIR, "data")
    plugins_js_path = os.path.join(WWW_DIR, "js", "plugins.js")
    if not os.path.exists(audio_dir):
        print("  [-] 未找到 audio 目录，跳过音频文件名修复。")
        return

    def is_ascii(text):
        return all(ord(ch) < 128 for ch in text)

    def replace_audio_refs(node, mapping_by_folder):
        if isinstance(node, list):
            for item in node:
                replace_audio_refs(item, mapping_by_folder)
            return
        if not isinstance(node, dict):
            return

        if isinstance(node.get("bgm"), dict):
            old_name = node["bgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["bgm"]["name"] = mapping_by_folder["bgm"][old_name]

        if isinstance(node.get("bgs"), dict):
            old_name = node["bgs"].get("name")
            if old_name in mapping_by_folder["bgs"]:
                node["bgs"]["name"] = mapping_by_folder["bgs"][old_name]

        if "sounds" in node and isinstance(node["sounds"], list):
            for sound in node["sounds"]:
                if isinstance(sound, dict):
                    old_name = sound.get("name")
                    if old_name in mapping_by_folder["se"]:
                        sound["name"] = mapping_by_folder["se"][old_name]

        if isinstance(node.get("battleBgm"), dict):
            old_name = node["battleBgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["battleBgm"]["name"] = mapping_by_folder["bgm"][old_name]

        if isinstance(node.get("titleBgm"), dict):
            old_name = node["titleBgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["titleBgm"]["name"] = mapping_by_folder["bgm"][old_name]

        for key in ("boat", "ship", "airship"):
            if isinstance(node.get(key), dict) and isinstance(node[key].get("bgm"), dict):
                old_name = node[key]["bgm"].get("name")
                if old_name in mapping_by_folder["bgm"]:
                    node[key]["bgm"]["name"] = mapping_by_folder["bgm"][old_name]

        for key in ("victoryMe", "defeatMe", "gameoverMe"):
            if isinstance(node.get(key), dict):
                old_name = node[key].get("name")
                if old_name in mapping_by_folder["me"]:
                    node[key]["name"] = mapping_by_folder["me"][old_name]

        code = node.get("code")
        params = node.get("parameters")
        if isinstance(code, int) and isinstance(params, list) and params and isinstance(params[0], dict):
            audio = params[0]
            if code in (241, 132):
                if audio.get("name") in mapping_by_folder["bgm"]:
                    audio["name"] = mapping_by_folder["bgm"][audio["name"]]
            elif code == 245:
                if audio.get("name") in mapping_by_folder["bgs"]:
                    audio["name"] = mapping_by_folder["bgs"][audio["name"]]
            elif code == 249:
                if audio.get("name") in mapping_by_folder["me"]:
                    audio["name"] = mapping_by_folder["me"][audio["name"]]
            elif code == 250:
                if audio.get("name") in mapping_by_folder["se"]:
                    audio["name"] = mapping_by_folder["se"][audio["name"]]

        for value in node.values():
            replace_audio_refs(value, mapping_by_folder)

    mapping_by_folder = {folder: {} for folder in ["bgm", "bgs", "me", "se"]}
    total_renamed = 0

    for folder in ["bgm", "bgs", "me", "se"]:
        folder_dir = os.path.join(audio_dir, folder)
        if not os.path.exists(folder_dir):
            continue

        grouped_files = {}
        for filename in os.listdir(folder_dir):
            full_path = os.path.join(folder_dir, filename)
            if not os.path.isfile(full_path):
                continue
            base, ext = os.path.splitext(filename)
            grouped_files.setdefault(base, []).append(ext)

        counter = 1
        for base in sorted(grouped_files.keys()):
            if is_ascii(base):
                continue

            while True:
                new_base = f"{folder}_{counter:04d}"
                counter += 1
                if new_base not in grouped_files and new_base not in mapping_by_folder[folder].values():
                    break

            mapping_by_folder[folder][base] = new_base
            for ext in grouped_files[base]:
                old_path = os.path.join(folder_dir, base + ext)
                new_path = os.path.join(folder_dir, new_base + ext)
                os.rename(old_path, new_path)
            total_renamed += 1

    if total_renamed == 0:
        print("  [-] 未发现需要 ASCII 化的音频文件名。")
        return

    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(data_dir, filename)
            with open(file_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            replace_audio_refs(data, mapping_by_folder)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    if os.path.exists(plugins_js_path):
        with open(plugins_js_path, "r", encoding="utf-8") as f:
            plugins_content = f.read()
        for folder_map in mapping_by_folder.values():
            for old_name, new_name in folder_map.items():
                plugins_content = plugins_content.replace(old_name, new_name)
        with open(plugins_js_path, "w", encoding="utf-8") as f:
            f.write(plugins_content)

    rename_map_path = os.path.join(WWW_DIR, "audio_rename_map.json")
    with open(rename_map_path, "w", encoding="utf-8") as f:
        json.dump(mapping_by_folder, f, ensure_ascii=False, indent=2)

    print(f"  [+] 已 ASCII 化 {total_renamed} 个音频基名，并同步重写数据引用。")

def step5_validate_audio_consistency():
    """构建后校验音频状态，防止 System.json 与实际资源状态不一致。"""
    print("\n>>> 步骤 5.5: 校验构建后音频一致性...")
    if not os.path.exists(SYSTEM_JSON_PATH):
        print("  [!] 找不到 System.json，无法执行音频一致性校验。")
        sys.exit(1)

    audio_dir = os.path.join(WWW_DIR, "audio")
    if not os.path.exists(audio_dir):
        print("  [!] 找不到 audio 目录，无法执行音频一致性校验。")
        sys.exit(1)

    with open(SYSTEM_JSON_PATH, 'r', encoding='utf-8-sig') as f:
        system_data = json.load(f)

    has_encrypted_audio = bool(system_data.get("hasEncryptedAudio"))
    encrypted_files = []
    decrypted_ogg_files = []
    m4a_files = set()
    missing_m4a = []

    for root, _, files in os.walk(audio_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, WWW_DIR)
            lower_file = file.lower()

            if lower_file.endswith('.ogg_') or lower_file.endswith('.m4a_') or lower_file.endswith('.rpgmvo'):
                encrypted_files.append(rel_path)
            elif lower_file.endswith('.ogg'):
                decrypted_ogg_files.append(full_path)
            elif lower_file.endswith('.m4a'):
                base_without_ext = os.path.splitext(os.path.relpath(full_path, audio_dir))[0]
                m4a_files.add(base_without_ext)

    if has_encrypted_audio:
        print("  [!] System.json 仍标记为 hasEncryptedAudio=true，构建产物状态非法。")
        sys.exit(1)

    if encrypted_files:
        print(f"  [!] 发现 {len(encrypted_files)} 个残留加密音频文件，构建产物状态非法。")
        for rel_path in encrypted_files[:20]:
            print(f"      - {rel_path}")
        if len(encrypted_files) > 20:
            print(f"      ... 其余 {len(encrypted_files) - 20} 个文件未展开")
        sys.exit(1)

    if not decrypted_ogg_files:
        print("  [!] 未发现任何解密后的 .ogg 文件，构建产物状态非法。")
        sys.exit(1)

    for ogg_path in decrypted_ogg_files:
        rel_base = os.path.splitext(os.path.relpath(ogg_path, audio_dir))[0]
        if rel_base not in m4a_files:
            missing_m4a.append(os.path.relpath(ogg_path, WWW_DIR))

    if missing_m4a:
        print(f"  [!] 发现 {len(missing_m4a)} 个 .ogg 未生成对应 .m4a，构建产物状态非法。")
        for rel_path in missing_m4a[:20]:
            print(f"      - {rel_path}")
        if len(missing_m4a) > 20:
            print(f"      ... 其余 {len(missing_m4a) - 20} 个文件未展开")
        sys.exit(1)

    print(f"  [+] 音频一致性校验通过：{len(decrypted_ogg_files)} 个 .ogg，{len(m4a_files)} 个 .m4a，无残留加密音频。")

def step_convert_video_to_mp4():
    """将 movies 目录下的 .webm 转换为 .mp4"""
    print("\n>>> 步骤: 扫描并转换视频格式为 mp4...")
    movies_dir = os.path.join(WWW_DIR, "movies")
    if not os.path.exists(movies_dir):
        return

    converted_count = 0
    for root, dirs, files in os.walk(movies_dir):
        for filename in files:
            if filename.endswith(".webm"):
                old_path = os.path.join(root, filename)
                base_name = os.path.splitext(filename)[0]
                new_path = os.path.join(root, base_name + ".mp4")
                if os.path.exists(new_path): continue
                
                cmd = ['ffmpeg', '-y', '-i', old_path, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', new_path]
                try:
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if res.returncode == 0: converted_count += 1
                except Exception:
                    pass
    print(f"  [+] 视频转码完成，处理了 {converted_count} 个文件。")

def fix_resource_percent_symbols(target_dir):
    """修复资源文件名中的 % 符号"""
    print(f"\n>>> 步骤 7: 开始清理目录中的 % 符号...")
    img_dir = os.path.join(target_dir, 'img')
    data_dir = os.path.join(target_dir, 'data')
    renamed_map = {}

    if os.path.exists(img_dir):
        for root, dirs, files in os.walk(img_dir):
            for filename in files:
                if '%' in filename:
                    old_path = os.path.join(root, filename)
                    new_filename = filename.replace('%', '_')
                    new_path = os.path.join(root, new_filename)
                    os.rename(old_path, new_path)
                    
                    old_base = os.path.splitext(filename)[0]
                    new_base = os.path.splitext(new_filename)[0]
                    renamed_map[old_base] = new_base
    
    if renamed_map and os.path.exists(data_dir):
        for root, dirs, files in os.walk(data_dir):
            for filename in files:
                if filename.endswith('.json'):
                    filepath = os.path.join(root, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    modified = False
                    for old_base, new_base in renamed_map.items():
                        if old_base in content:
                            content = content.replace(old_base, new_base)
                            modified = True
                    if modified:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(content)
    print("  [+] 资源符号修复完成！")

def get_valid_project_name():
    """获取并修正为 Cloudflare 规范域名"""
    raw_name = GAME_NAME
    name = raw_name.lower()
    name = re.sub(r'[\s_]+', '-', name)
    name = re.sub(r'[^a-z0-9-]', '', name)
    name = name.strip('-')[:58].rstrip('-')
    
    if not name:
        print(f"❌ 错误：项目名 '{raw_name}' 无法转换！")
        sys.exit(1)
    return name      

def step11_deploy_to_cloudflare(project_name):
    """推送到 Cloudflare 并注入防伪网关"""
    mode_text = "一次性部署" if SINGLE_DEPLOY else "部署 (含手动 KV 绑定确认)"
    print(f"\n🚀 [Step 11] 开始执行{mode_text}: {project_name} ...")
    
    # [核心修复] 恢复防伪网关代码 (_worker.js) 的拷贝逻辑
    worker_src = os.path.join(BASE_DIR, "_worker.js")
    worker_dest = os.path.join(WWW_DIR, "_worker.js")

    try:
        shutil.copy2(worker_src, worker_dest)
        print("   _worker.js 注入完成。")
    except FileNotFoundError:
        print(f"   致命错误：找不到防伪网关文件 {worker_src}！流水线终止。")
        sys.exit(1)

    # 注入部署凭证环境变量
    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = CF_ACCOUNT_ID
    env["CLOUDFLARE_API_TOKEN"] = CF_API_TOKEN

    deploy_cmd = [
        "wrangler", "pages", "deploy", 
        WWW_DIR, 
        "--project-name", project_name,
        "--branch", "production",
    ]

    print("\n   ⏳ [阶段一] 正在推送到 Cloudflare...")
    print("   " + "-"*40)
    
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
    except subprocess.CalledProcessError:
        print("\n   首次部署失败或被取消，请检查报错。")
        return

    if SINGLE_DEPLOY:
        print("   " + "-"*40)
        print(f"\n  单次部署完成！")
        return

    print("\n" + "!"*55)
    print(" ⚠️ 关键操作：守卫需要数据库钥匙 ⚠️")
    print(f" 项目 '{project_name}' 已初步上线，但尚未连接 KV 数据库！")
    print(" 请立即前往 Cloudflare 网页端完成以下操作：")
    print(" 1. 进入 Workers & Pages -> 点击刚部署的项目")
    print(" 2. 点击顶部 Settings (设置) -> 左侧 Functions (函数)")
    print(" 3. 下拉找到 KV namespace bindings，点击 Add binding")
    print(" 4. Variable name 填入大写: AUTH_CODES")
    print(" 5. KV namespace 选择你的防伪数据库")
    print(" 6. 点击 Save (保存)")
    print("!"*55)
    
    input("\n  完成网页端绑定后，请在这里按下【回车键】进行最终部署刷新...")

    print("\n   [阶段三] 正在重新部署，使 KV 绑定正式生效...")
    print("   " + "-"*40)
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
        print("   " + "-"*40)
        print(f"\n  恭喜！大门已锁死，部署大功告成！")
    except subprocess.CalledProcessError:
        print("\n   二次部署失败。")

def main():
    print("="*50)
    print(" RPG Maker Web 全自动部署处理流 (MV/MZ 兼容版)")
    print("="*50)
    
    prepare_www_workspace()
    step0_clean_pc_build()
    step0_apply_mtools_translation()
    step1_apply_patch()
    step2_patch_index_html()
    key = step3_patch_system_json()
    step4_decrypt_assets(key)
    step5_convert_audio_to_m4a()
    step5_sanitize_audio_filenames()
    step5_validate_audio_consistency()
    step_convert_video_to_mp4()
    patch_problematic_plugin_params()
    fix_resource_percent_symbols(WWW_DIR)
    
    FINAL_PROJECT_NAME = get_valid_project_name()
    step11_deploy_to_cloudflare(FINAL_PROJECT_NAME)
    
    print("\n" + "="*50)
    
    print(f"\n 部署大功告成！游戏 [{GAME_NAME}] 已经在线上就绪！")
    print("="*50)

if __name__ == "__main__":
    main()
