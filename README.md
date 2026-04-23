# RPGMZ Pipeline

`RPGMZ_pipline.py` 用来把 RPG Maker MV/MZ 的 PC 版目录处理成可网页部署的 `www`，并直接发布到 Cloudflare Pages。

## 功能

- 自动识别当前目录下的完整游戏目录，并复制为 `www`
- 清理 PC/NW.js 冗余文件
- 可选合并 `patch.zip`
- 可选注入 `CN.json` 文本汉化
- 修改 `index.html`，注入浏览器兼容层和虚拟手柄
- 强制引擎走 Web 存档模式
- iPhone/iPad 强制走 `m4a`，其他平台继续使用 `ogg`
- 给 `rmmz_managers.js` 注入 iOS `m4a` 解码保护，避免 `m4a` 误进 `VorbisDecoder`
- 给 `rmmz_sprites.js` 注入移动端动画限流补丁
- 关闭 `System.json` 的资源加密标记并解密图片/音频
- 批量把 `ogg/wav` 转为 `m4a`
- 将非 ASCII 音频文件名统一改为 ASCII 安全名，并自动重写 `data/*.json` 与 `js/plugins.js` 引用
- 在部署前执行音频一致性校验，发现加密残留、缺失转码或状态不一致时直接终止
- 可通过 `?audioDebug=1` 打开 iPhone 端音频调试面板，用于排查播放链问题
- 把 `webm` 转为 `mp4`
- 修复部分插件参数和资源文件名问题
- 注入 `_worker.js` 并部署到 Cloudflare Pages

## 目录约定

脚本默认在自己的所在目录工作。

必需文件：

- `RPGMZ_pipline.py`
- `_worker.js`
- `vpad.html`

可选文件：

- `patch.zip`
- `CN.json`
- `cloudflare_credentials.json`

输入目录要求：

- 当前目录下存在一个完整游戏目录
- 该目录至少包含 `index.html`、`js/`、`data/`

运行时会生成：

- `www/`：处理后的网页工作目录

## 依赖

- `python3`
- `ffmpeg`
- `wrangler`

脚本内部直接使用环境变量部署：

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

但这两个值不是写死在脚本里，而是从仓库根目录下的 `cloudflare_credentials.json` 读取。

模板文件：

- `cloudflare_credentials.json.example`

实际使用文件：

- `cloudflare_credentials.json`

实际凭证文件已加入 `.gitignore`，不会被 git 追踪。

## 用法

```bash
python3 RPGMZ_pipline.py <游戏名>
```

示例：

```bash
python3 RPGMZ_pipline.py fgo-rpg
```

单次部署模式：

```bash
python3 RPGMZ_pipline.py fgo-rpg --single-deploy
```

## 部署行为

- 默认部署到 Cloudflare Pages 的 `production` 分支
- 不加 `--single-deploy` 时，脚本会先部署一次，然后等待你去 Cloudflare 后台绑定 `AUTH_CODES` KV，再执行第二次部署
- 加 `--single-deploy` 时，只做一次部署，不等待人工确认

## 实际处理流程

1. 从完整游戏目录复制出 `www/`
2. 删除 PC 壳文件和无关目录
3. 合并 `patch.zip`
4. 注入 `CN.json`
5. 修改 `index.html` 和引擎 JS
6. 关闭 `System.json` 加密标志并解密资源
7. 把音频转成 `m4a`
8. 将非 ASCII 音频文件名改成 ASCII，并重写所有引用
9. 执行构建后音频一致性校验
10. 转码视频
11. 修复插件参数与资源引用
12. 注入 `_worker.js`
13. 部署到 Cloudflare Pages

## 注意事项

- 当前目录里如果同时存在多个完整游戏目录，脚本的自动识别会变得不可靠，最好一次只放一个
- 每次执行都会优先从原始完整游戏目录重建 `www/`
- 音频转码可能耗时较长
- iOS 端现在默认请求 `m4a`，所以构建产物里必须同时存在 `ogg` 和 `m4a`
- 执行后会生成 `www/audio_rename_map.json`，用于记录音频 ASCII 化映射
- 如果在受限环境里运行，`wrangler` 可能会因为网络或配置目录权限失败
- 如果要清理空间，部署完成后可以删除 `www/` 和原始游戏目录

## 调试方法

- 在 iPhone/iPad 上追加 `?audioDebug=1` 访问部署地址，可以打开音频调试面板
- 调试面板会记录 `playBgm/playBgs`、实际请求 URL、`decode/error`、音频后缀判定和解码器判定
- 不带 `?audioDebug=1` 时，调试标记会自动清理，不会常驻

## 推荐工作流

1. 把一个完整 RPG Maker 游戏目录放到仓库根目录
2. 准备好 `_worker.js`、`vpad.html`
3. 如有需要，加入 `patch.zip` 或 `CN.json`
4. 运行：

```bash
python3 RPGMZ_pipline.py <项目名> --single-deploy
```

5. 部署完成后，按需删除 `www/` 和源游戏目录
