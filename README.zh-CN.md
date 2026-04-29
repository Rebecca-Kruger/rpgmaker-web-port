# RPGMZ Web Porting Toolkit

英文文档：[README.md](README.md)

把 RPG Maker MV/MZ 的 PC 游戏包转换成更适合移动端网页运行的构建产物，并支持部署到 Cloudflare Pages、本地目录或自定义服务器。

这是一个面向 RPG Maker MV/MZ 的 PC 游戏包 Web 化流水线/工具链，重点处理桌面导出包在浏览器或 WebView 中稳定运行前需要完成的转换、修复和兼容步骤。

## 问题反馈

如果你用这个工具链部署任何 RPG Maker MV/MZ 游戏时遇到 bug，欢迎直接在 Issues 提出来。

如果方便，请附上游戏类型、运行平台和最短复现步骤。我会尽量快速跟进并修复。

## 主要能力

- 从完整 MV/MZ 游戏目录构建干净的 `www/` 工作区
- 清理 NW.js 和桌面端专用文件
- 可选合并 `patch.zip`
- 可选注入 `CN.json` 文本内容
- 关闭资源加密标记并解密图片/音频资源
- 为 iPhone/iPad 转换并强制使用 `m4a`
- 防止 `m4a` 误走 VorbisDecoder
- 将非 ASCII 音频文件名标准化为 ASCII 并重写引用
- 校验音频构建一致性
- 将 `webm` 视频转换为 `mp4`
- 注入浏览器/WebView 兼容补丁和移动端控制层
- 支持 `?audioDebug=1` 真机音频调试面板
- 支持 Cloudflare、本地目录、自定义命令或只构建不部署

## 快速开始

公开入口：

```bash
python3 rpgmaker_web_port.py <project-name> --source ./Game
```

本地构建并输出到目录：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target local --output-dir ./dist/demo-game
```

启动本地 HTTP 服务：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target local --serve-local --local-port 8080
```

只构建不部署：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target none
```

部署到 Cloudflare Pages：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target cloudflare
```

## 部署目标

- `cloudflare`：部署到 Cloudflare Pages，默认目标。
- `local`：复制最终 Web 构建产物到本地目录。
- `custom`：运行自定义部署命令，例如 `rsync`、`scp`、Docker 或外部打包器。
- `none`：只构建，不部署。

## Cloudflare 配置

只有使用 `--deploy-target cloudflare` 时才需要 `cloudflare_credentials.json`。

模板文件：

```text
cloudflare_credentials.json.example
```

真实凭证文件已被 `.gitignore` 忽略，不应提交到 GitHub。

## 可选 KV 访问验证

如果需要访问码验证页：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --enable-kv-auth
```

Cloudflare Pages 需要配置：

- `AUTH_CODES`：KV namespace binding
- `ACCESS_SECRET_KEY`：Worker 环境变量，用于签名访问 token

验证页只应表述为技术探索模拟器，不应表述为官方授权或商业发行产品。

## 自定义部署命令

`--deploy-target custom` 会提供以下环境变量：

- `RPGMZ_PROJECT_NAME`
- `RPGMZ_WWW_DIR`
- `RPGMZ_OUTPUT_DIR`
- `RPGMZ_BASE_DIR`

示例：

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target custom --custom-deploy-command 'rsync -av "$RPGMZ_WWW_DIR"/ user@host:/var/www/game/'
```

## 许可证

本项目使用 GNU General Public License v3.0。详见 [LICENSE](LICENSE)。
