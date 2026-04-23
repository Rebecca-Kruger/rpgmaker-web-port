# Environment Requirements

这份文档说明 `RPGMZ_pipline.py` 运行前需要准备什么，以及推荐的环境配置方式。

## 当前已验证版本

- Python: `3.10.12`
- FFmpeg: `4.4.2`
- Wrangler: `4.70.0`

## 必需软件

### 1. Python 3

脚本本体使用标准库，不依赖额外 `pip` 包。

检查：

```bash
python3 --version
```

Ubuntu 安装：

```bash
sudo apt update
sudo apt install -y python3
```

### 2. FFmpeg

用于把音频转成 `m4a`，以及把 `webm` 转成 `mp4`。

当前流水线里，iPhone/iPad 会优先请求 `m4a`，所以 `ffmpeg` 不是可选项，而是构建可播放 iOS 音频的必要组件。

检查：

```bash
ffmpeg -version
```

Ubuntu 安装：

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 3. Node.js 和 Wrangler

用于部署到 Cloudflare Pages。

先检查 Node：

```bash
node --version
npm --version
```

如果没装，Ubuntu 安装：

```bash
sudo apt update
sudo apt install -y nodejs npm
```

安装 Wrangler：

```bash
sudo npm install -g wrangler
```

检查：

```bash
wrangler --version
```

## Cloudflare 配置

脚本部署依赖两个凭证：

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

现在这两个值是直接写在 [RPGMZ_pipline.py](/home/ubuntu/RPG_game/RPGMZ_pipline.py) 里的，所以当前仓库开箱即可跑。

如果后续你要把脚本做成通用版，建议改成从环境变量读取，例如：

```bash
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."
```

## Wrangler 目录权限

`wrangler` 默认会写：

- `~/.config/.wrangler`

如果运行环境对这个目录只读，部署时会报日志写入错误。这个时候需要把 `XDG_CONFIG_HOME` 指到一个可写目录。

推荐：

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
mkdir -p "$XDG_CONFIG_HOME"
```

然后再执行部署命令。

单独测试部署时可以这样写：

```bash
env XDG_CONFIG_HOME="$HOME/.codex/memories/.config" wrangler pages deploy www --project-name fgo-rpg --branch production
```

## 目录内必需文件

脚本所在目录建议至少包含：

- `RPGMZ_pipline.py`
- `_worker.js`
- `vpad.html`

可选文件：

- `patch.zip`
- `CN.json`

输入素材：

- 一个完整的 RPG Maker MV/MZ 游戏目录
- 该目录内至少要有 `index.html`、`js/`、`data/`

构建产物补充说明：

- 运行后会生成 `www/`
- 流水线会在 `www/audio_rename_map.json` 输出非 ASCII 音频文件名的重命名映射
- 如果音频解密、转码、ASCII 化或一致性校验失败，脚本会直接终止，不继续部署

## 推荐环境变量

如果你希望长期稳定运行，建议在 shell 配置里加入：

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
export PATH="$PATH:/usr/bin:/usr/local/bin"
```

如果以后把 Cloudflare 凭证移出脚本，再加上：

```bash
export CLOUDFLARE_ACCOUNT_ID="your_account_id"
export CLOUDFLARE_API_TOKEN="your_api_token"
```

## 最小自检

在运行流水线前，先过一遍：

```bash
python3 --version
ffmpeg -version | head -n 1
node --version
npm --version
wrangler --version
```

如果你主要在 iPhone/iPad 上测试，额外建议确认：

```bash
ffmpeg -codecs | rg aac
```

只要 `aac` 编码可用，流水线就能正常为 iOS 生成 `m4a`。

## 推荐执行方式

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
python3 RPGMZ_pipline.py <项目名> --single-deploy
```

默认部署分支是：

```bash
production
```
