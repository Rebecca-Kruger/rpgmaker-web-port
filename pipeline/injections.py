import json
import os
import re
import sys


def patch_problematic_plugin_params(www_dir):
    """Patch only known high-risk plugin parameters."""
    print("\n>>> Step 6: Patching known iOS-risk plugin parameters...")
    plugins_path = os.path.join(www_dir, "js", "plugins.js")
    if not os.path.exists(plugins_path):
        print("  [-] plugins.js not found. Skipping plugin parameter patch.")
        return

    with open(plugins_path, "r", encoding="utf-8") as file:
        content = file.read()

    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1 or end < start:
        print("  [!] plugins.js format is invalid. Skipping plugin parameter patch.")
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
                print("  [+] Disabled LL_StandingPicture boot-time picture preloading (bootCachePictures=false)")

    if changed:
        with open(plugins_path, "w", encoding="utf-8") as file:
            file.write(prefix)
            json.dump(plugins, file, ensure_ascii=False, indent=2)
            file.write(suffix if suffix else ";\n")
    else:
        print("  [-] No target plugin parameters needed patching.")


def patch_runtime_injections(www_dir, vpad_html_path):
    """Inject Web/iOS runtime compatibility patches into index.html and engine JS."""
    print("\n>>> Step 2: Injecting runtime compatibility patches and mobile controls...")
    index_path = os.path.join(www_dir, "index.html")

    if not os.path.exists(index_path):
        print("  [!] Fatal error: index.html not found. Stopping pipeline.")
        sys.exit(1)

    with open(index_path, "r", encoding="utf-8") as file:
        html_content = file.read()

    html_content = _inject_environment_mock(html_content)
    html_content = _inject_audio_debug_panel(html_content)
    html_content = _inject_pwa_meta(html_content)
    html_content = _inject_virtual_gamepad(html_content, vpad_html_path)

    with open(index_path, "w", encoding="utf-8") as file:
        file.write(html_content)
    print("  [+] index.html injection written to disk.")

    _patch_storage_and_audio_ext(www_dir)
    _patch_m4a_decoder_guard(www_dir)
    _patch_mobile_animation_throttle(www_dir)
    print("  [+] Step 2 complete. Runtime compatibility layer is in place.")


def _inject_environment_mock(html_content):
    mock_begin = "<!-- [RPGMZ Toolkit Inject Begin] -->"
    mock_end = "<!-- [RPGMZ Toolkit Inject End] -->"
    mock_script = """
        <!-- [RPGMZ Toolkit Inject Begin] -->
        <script type="text/javascript">
            // 1. Override environment checks before the engine boots.
            window.Utils = window.Utils || {};
            window.Utils.isNwjs = function() { return false; };
            window.Utils.isMobileDevice = function() { return true; }; // Enable mobile optimizations.

            window.process = {
                env: {},
                mainModule: { filename: 'index.html' },
                platform: 'browser',
                arch: 'x64',  // Mock a 64-bit architecture.
                versions: { node: '14.16.0', nw: '0.49.2' }, // Mock a newer NW.js runtime version for plugin compatibility.
                argv: [], // Mock empty launch arguments.
                execPath: '/Game.exe', // Mock executable path.
                cwd: function() { return '/'; }, // Mock root directory.
                chdir: function(dir) { return; }, // Ignore chdir calls.
                exit: function() {
                    console.warn('[RPGMZ Web Toolkit] Blocked game exit call');
                    // Browsers cannot close the tab directly; ignore or redirect if needed.
                    // window.location.href = '/';
                },
                on: function(event, callback) {
                    console.warn('[RPGMZ Web Toolkit] Blocked unsupported process event listener: ' + event);
                    return this; // Return this to support chained calls such as process.on().on().
                },
                uptime: function() { return performance.now() / 1000; }, // Mock uptime for plugins that expect it.
                // Mock high-resolution timing for Effekseer compatibility.
                hrtime: function(prev) {
                    var now = performance.now(); // Browser-provided high-resolution milliseconds.
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

            // 2. [Defensive mock mode] Mock NW.js APIs and log unsupported calls.
            const createNwMock = () => {
                const mock = new Proxy(function() {}, {
                    get: (target, prop) => {
                        if (typeof prop === 'symbol') {
                            if (prop === Symbol.toPrimitive) return (hint) => hint === 'number' ? 0 : '';
                            return Reflect.get(target, prop);
                        }
                        // Log unsupported calls in the browser console.
                        if (typeof prop === 'string' && prop !== 'then') {
                            console.warn(`[RPGMZ Web Toolkit] Game tried to access unsupported desktop module/property: ${prop}`);
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

            // 3. Intercept require() and provide safe fs/path stubs.
            window.require = function(moduleName) {
                if (moduleName === 'fs') return {
                    existsSync: function(){return false;},
                    // Return "{}" so JSON.parse does not fail when plugins force-read config files.
                    readFileSync: function(){return "{}";},
                    writeFileSync: function(){return true;},
                    mkdirSync: function(){return true;},
                    statSync: function(){return {isDirectory: function(){return false;}};}
                };
                if (moduleName === 'path') return { join: function(){return Array.from(arguments).join('/');}, dirname: function(){return '';}, basename: function(p){return p.split('/').pop();}, extname: function(p){var match=p.match(/\\.[^.]+$/); return match?match[0]:'';} };
                if (moduleName === 'nw.gui') return window.nw;
                return {};
            };

            // 4. Prepare media unlock hooks for iOS/mobile browsers.
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
        <!-- [RPGMZ Toolkit Inject End] -->
        """
    if mock_begin in html_content and mock_end in html_content:
        html_content = re.sub(
            r"<!-- \[RPGMZ Toolkit Inject Begin\] -->.*?<!-- \[RPGMZ Toolkit Inject End\] -->",
            lambda _match: mock_script,
            html_content,
            count=1,
            flags=re.DOTALL,
        )
        print("  [+] Web runtime compatibility shim updated.")
    elif "window.require = function" not in html_content:
        html_content = re.sub(
            r"(<script)",
            lambda match: mock_script + "\n" + match.group(1),
            html_content,
            count=1,
            flags=re.IGNORECASE,
        )
        print("  [+] Web runtime compatibility shim injected.")
    return html_content


def _inject_audio_debug_panel(html_content):
    debug_begin = "<!-- [RPGMZ Toolkit Audio Debug Begin] -->"
    debug_end = "<!-- [RPGMZ Toolkit Audio Debug End] -->"
    debug_script = """
        <!-- [RPGMZ Toolkit Audio Debug Begin] -->
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
        <!-- [RPGMZ Toolkit Audio Debug End] -->
        """
    if debug_begin in html_content and debug_end in html_content:
        html_content = re.sub(
            r"<!-- \[RPGMZ Toolkit Audio Debug Begin\] -->.*?<!-- \[RPGMZ Toolkit Audio Debug End\] -->",
            lambda _match: debug_script,
            html_content,
            count=1,
            flags=re.DOTALL,
        )
        print("  [+] Audio debug panel updated.")
    else:
        html_content = re.sub(
            r"(<script)",
            lambda match: debug_script + "\n" + match.group(1),
            html_content,
            count=1,
            flags=re.IGNORECASE,
        )
        print("  [+] Audio debug panel injected.")
    return html_content


def _inject_pwa_meta(html_content):
    pwa_meta = (
        "\n<meta name=\"mobile-web-app-capable\" content=\"yes\">\n"
        "<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n"
        "<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover\">\n"
    )
    if "apple-mobile-web-app-capable" not in html_content:
        html_content = re.sub(r"(</head>)", pwa_meta + r"\1", html_content, flags=re.IGNORECASE)
    return html_content


def _inject_virtual_gamepad(html_content, vpad_html_path):
    if 'id="v-pad"' in html_content:
        return html_content
    if os.path.exists(vpad_html_path):
        with open(vpad_html_path, "r", encoding="utf-8") as file:
            gamepad_code = file.read()
        html_content = html_content.replace("</body>", "\n" + gamepad_code + "\n</body>")
        print("  [+] Loaded and injected virtual gamepad from vpad.html.")
    else:
        print("  [-] vpad.html not found. Skipping virtual gamepad injection.")
    return html_content


def _patch_storage_and_audio_ext(www_dir):
    js_dir = os.path.join(www_dir, "js")
    target_files = ["rmmz_managers.js", "rpg_managers.js"]
    patched = False

    for filename in target_files:
        file_path = os.path.join(js_dir, filename)
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()

        if "[RPGMZ Toolkit Inject]" not in content:
            with open(file_path, "a", encoding="utf-8") as file:
                file.write("""\n
// ==========================================
// [RPGMZ Toolkit Inject] Force browser storage mode.
// Override engine isNwjs and isLocalMode checks.
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
console.log("🔒 [RPGMZ Web Toolkit] Web storage mode enforced for browser runtime.");
""")
            print(f"  [+] Engine compatibility patch appended to: {filename}")
        else:
            print(f"  [-] Engine file {filename} already patched. Skipping.")
        patched = True

    if not patched:
        print("  [!] Warning: managers.js not found. This may not be a standard MV/MZ project.")


def _patch_m4a_decoder_guard(www_dir):
    core_path = os.path.join(www_dir, "js", "rmmz_managers.js")
    if not os.path.exists(core_path):
        return

    with open(core_path, "r", encoding="utf-8") as file:
        managers_content = file.read()

    if "[RPGMZ Toolkit Inject] iOS m4a decoder guard" in managers_content:
        print("  [-] rmmz_managers.js already has the iOS m4a decoder guard. Skipping.")
        return

    with open(core_path, "a", encoding="utf-8") as file:
        file.write("""\n
// ==========================================
// [RPGMZ Toolkit Inject] iOS m4a decoder guard
// m4a must use native browser decoding, not the OGG-only VorbisDecoder path.
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
""")
    print("  [+] Injected iOS m4a decoder guard into: rmmz_managers.js")


def _patch_mobile_animation_throttle(www_dir):
    sprites_path = os.path.join(www_dir, "js", "rmmz_sprites.js")
    if not os.path.exists(sprites_path):
        print("  [!] Warning: rmmz_sprites.js not found. Skipping animation throttle patch.")
        return

    with open(sprites_path, "r", encoding="utf-8") as file:
        sprites_content = file.read()

    if "[RPGMZ Toolkit Inject] Mobile animation throttle" in sprites_content:
        print("  [-] rmmz_sprites.js already has the animation throttle patch. Skipping.")
        return

    with open(sprites_path, "a", encoding="utf-8") as file:
        file.write("""\n
// ==========================================
// [RPGMZ Toolkit Inject] Mobile animation throttle
// Throttle rapid mobile Effekseer animation starts to reduce iOS RangeError risk.
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
""")
    print("  [+] Injected mobile animation throttle into: rmmz_sprites.js")
