#RZH
import os
import json
import subprocess
import zipfile
import sys
import re
import shutil
import glob
import hashlib
import unicodedata

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
GAME_NAME = sys.argv[1] if len(sys.argv) >= 2 else None
SAVE_PREFIX = GAME_NAME.upper() + "_" if GAME_NAME else ""
DEPLOY_DIR = os.path.join("/var/www/html/games", GAME_NAME) if GAME_NAME else ""
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

SAFE_RESOURCE_RE = re.compile(r"^[A-Za-z0-9._-]+$")

def ensure_game_name():
    """确保命令行传入了游戏名。"""
    if not GAME_NAME:
        print("❌ 错误：缺少游戏文件夹名称！")
        print("💡 用法: sudo python3 RPGMZ_pipline.py <游戏名>")
        sys.exit(1)

def load_plugins_manifest():
    """读取 js/plugins.js 并返回 (路径, 前缀, 数组, 后缀)。"""
    plugins_path = os.path.join(WWW_DIR, "js", "plugins.js")
    if not os.path.exists(plugins_path):
        return None, None, None, None

    with open(plugins_path, "r", encoding="utf-8") as f:
        content = f.read()

    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("plugins.js 格式异常，未找到插件数组")

    prefix = content[:start]
    suffix = content[end + 1:]
    plugins = json.loads(content[start:end + 1])
    return plugins_path, prefix, plugins, suffix

def save_plugins_manifest(path, prefix, plugins, suffix):
    """将插件数组写回 js/plugins.js。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(prefix)
        json.dump(plugins, f, ensure_ascii=False, indent=2)
        f.write(suffix if suffix else ";\n")

def normalize_resource_stem(stem):
    """将资源主文件名收敛为适合网页部署的 ASCII 安全名字。"""
    normalized = unicodedata.normalize("NFKC", stem)
    if SAFE_RESOURCE_RE.fullmatch(normalized):
        return normalized

    ascii_hint = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_hint = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_hint)
    ascii_hint = re.sub(r"_+", "_", ascii_hint).strip("._-")
    if not ascii_hint:
        ascii_hint = "asset"
    if not ascii_hint[0].isalpha():
        ascii_hint = "res_" + ascii_hint

    digest = hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8]
    return f"{ascii_hint}_{digest}"

def apply_text_replacements(file_path, replacements):
    """对文本文件执行批量替换。"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for old, new in replacements:
        content = content.replace(old, new)

    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    return False

def normalize_resource_filenames(target_dir):
    """将高风险资源文件名标准化，并同步更新数据库/插件引用。"""
    print("\n>>> 步骤 6: 标准化高风险资源文件名并同步引用...")
    resource_roots = [
        os.path.join(target_dir, "img"),
        os.path.join(target_dir, "audio"),
        os.path.join(target_dir, "movies"),
        os.path.join(target_dir, "effects"),
        os.path.join(target_dir, "fonts"),
        os.path.join(target_dir, "icon"),
    ]

    renamed_entries = []
    stem_updates = {}
    basename_updates = {}

    for root_dir in resource_roots:
        if not os.path.exists(root_dir):
            continue
        for root, _, files in os.walk(root_dir):
            for filename in sorted(files):
                stem, ext = os.path.splitext(filename)
                safe_ext = unicodedata.normalize("NFKC", ext)
                safe_stem = normalize_resource_stem(stem)
                new_filename = safe_stem + safe_ext
                if new_filename == filename:
                    continue

                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, new_filename)
                suffix = 1
                while os.path.exists(new_path):
                    new_filename = f"{safe_stem}_{suffix}{safe_ext}"
                    new_path = os.path.join(root, new_filename)
                    suffix += 1

                os.rename(old_path, new_path)
                new_stem = os.path.splitext(new_filename)[0]
                renamed_entries.append((filename, new_filename))
                basename_updates[filename] = new_filename
                stem_updates[stem] = new_stem

    if not renamed_entries:
        print("  [-] 未发现需要标准化的资源文件名。")
        return

    replacements = []
    for old, new in {**basename_updates, **stem_updates}.items():
        replacements.append((old, new))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)

    touched_files = 0
    data_dir = os.path.join(target_dir, "data")
    if os.path.exists(data_dir):
        for root, _, files in os.walk(data_dir):
            for filename in files:
                if filename.endswith(".json"):
                    if apply_text_replacements(os.path.join(root, filename), replacements):
                        touched_files += 1

    plugins_js = os.path.join(target_dir, "js", "plugins.js")
    if os.path.exists(plugins_js) and apply_text_replacements(plugins_js, replacements):
        touched_files += 1

    print(f"  [+] 已标准化 {len(renamed_entries)} 个资源文件名，并同步更新 {touched_files} 个引用文件。")

def patch_web_compatible_plugins():
    """修正已知不适合网页部署的插件配置，并禁用异常插件文件。"""
    print("\n>>> 步骤 7: 修正网页部署下的高风险插件配置...")
    try:
        plugins_path, prefix, plugins, suffix = load_plugins_manifest()
    except Exception as e:
        print(f"  [!] 读取 plugins.js 失败，跳过插件修正: {e}")
        return

    if not plugins_path:
        print("  [-] 未发现 plugins.js，跳过插件修正。")
        return

    plugin_dir = os.path.join(WWW_DIR, "js", "plugins")
    changed = False
    disabled_plugins = []
    tuned_plugins = []

    for plugin in plugins:
        name = plugin.get("name", "")
        params = plugin.get("parameters", {})
        plugin_path = os.path.join(plugin_dir, f"{name}.js")

        if plugin.get("status"):
            if not os.path.exists(plugin_path):
                plugin["status"] = False
                changed = True
                disabled_plugins.append(f"{name} (文件缺失)")
                continue

            try:
                with open(plugin_path, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(256).lstrip().lower()
                if head.startswith("<!doctype html") or head.startswith("<html"):
                    plugin["status"] = False
                    changed = True
                    disabled_plugins.append(f"{name} (文件内容是 HTML)")
                    continue
            except Exception:
                pass

        if name == "DevToolsManage" and plugin.get("status"):
            plugin["status"] = False
            changed = True
            disabled_plugins.append(f"{name} (本地调试插件不应部署到网页)")

        if name == "LL_StandingPicture" and params.get("bootCachePictures") == "true":
            params["bootCachePictures"] = "false"
            plugin["parameters"] = params
            changed = True
            tuned_plugins.append("LL_StandingPicture.bootCachePictures=false")

    if changed:
        save_plugins_manifest(plugins_path, prefix, plugins, suffix)

    if disabled_plugins:
        print("  [+] 已禁用异常/不适合网页部署的插件:")
        for item in disabled_plugins:
            print(f"     - {item}")
    if tuned_plugins:
        print("  [+] 已调整高风险插件参数:")
        for item in tuned_plugins:
            print(f"     - {item}")
    if not changed:
        print("  [-] 未发现需要修正的插件配置。")

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
    if "window.require = function" not in html_content:
        mock_script = """
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
        </script>
        """
        # 使用正则，无视大小写寻找第一个 <script，并插在它前面
        html_content = re.sub(r'(<script)', mock_script + r'\n\1', html_content, count=1, flags=re.IGNORECASE)
        print("  [+] Proxy 监控防火墙注入成功！")

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
console.log("🔒 [Nix 降维打击] 引擎已物理锁死 Web 异步存档模式，PC 路线被切断！");
"""
                    f.write(hard_lock_code)
                print(f"  [√] 成功物理篡改引擎底层文件: {filename}")
            else:
                print(f"  [-] 引擎文件 {filename} 已被锁定，跳过。")
            patched = True
            
    if not patched:
        print("  [!] 警告：未找到 managers.js 核心文件，当前可能不是标准 MV/MZ 工程！")
        
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
    print(f"  [+] 音频转码结束，处理了 {converted_count} 个文件。")

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
    print(f"\n>>> 步骤 8: 开始清理目录中的 % 符号...")
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
    print(f"\n🚀 [Step 11] 开始执行部署 (含手动 KV 绑定确认): {project_name} ...")
    
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
    ]

    # ==========================================
    # 阶段一：首次建站部署 (交互式)
    # ==========================================
    print("\n   ⏳ [阶段一] 正在推送到 Cloudflare...")
    print("   👉 (如果是新项目，请在下方提示中输入 Y 确认创建)")
    print("   " + "-"*40)
    
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
    except subprocess.CalledProcessError:
        print("\n   首次部署失败或被取消，请检查报错。")
        return

    # ==========================================
    # 阶段二：脚本暂停，等待手动绑定
    # ==========================================
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
    
    # 阻塞脚本，直到你敲下回车键
    input("\n  完成网页端绑定后，请在这里按下【回车键】进行最终部署刷新...")

    # ==========================================
    # 阶段三：二次部署刷新边缘节点
    # ==========================================
    print("\n   [阶段三] 正在重新部署，使 KV 绑定正式生效...")
    print("   " + "-"*40)
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
        print("   " + "-"*40)
        print(f"\n  恭喜！大门已锁死，部署大功告成！")
    except subprocess.CalledProcessError:
        print("\n   二次部署失败。")

def main():
    ensure_game_name()
    print("="*50)
    print(" RPG Maker Web 全自动部署处理流 (MV/MZ 兼容版)")
    print("="*50)
    
    step0_clean_pc_build()
    step0_apply_mtools_translation()
    step1_apply_patch()
    step2_patch_index_html()
    key = step3_patch_system_json()
    step4_decrypt_assets(key)
    step5_convert_audio_to_m4a()
    step_convert_video_to_mp4()
    normalize_resource_filenames(WWW_DIR)
    patch_web_compatible_plugins()
    fix_resource_percent_symbols(WWW_DIR)
    
    FINAL_PROJECT_NAME = get_valid_project_name()
    step11_deploy_to_cloudflare(FINAL_PROJECT_NAME)
    
    print("\n" + "="*50)
    
    print(f"\n 部署大功告成！游戏 [{GAME_NAME}] 已经在线上就绪！")
    print("="*50)

if __name__ == "__main__":
    main()
