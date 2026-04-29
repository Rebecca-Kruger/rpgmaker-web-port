# Environment Requirements

This document describes the runtime and tooling requirements for `rpgmaker_web_port.py`, plus recommended setup for stable builds and deployments.

## Verified Versions

- Python: `3.10.12`
- FFmpeg: `4.4.2`
- Wrangler: `4.70.0`

## Required Software

### 1. Python 3

The pipeline itself uses Python standard library modules and does not require extra `pip` packages.

Check:

```bash
python3 --version
```

Ubuntu install:

```bash
sudo apt update
sudo apt install -y python3
```

### 2. FFmpeg

Used for audio conversion (`ogg/wav -> m4a`) and video conversion (`webm -> mp4`).

In this pipeline, iPhone/iPad targets request `m4a`, so `ffmpeg` is required for iOS-compatible audio output.

Check:

```bash
ffmpeg -version
```

Ubuntu install:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 3. Node.js and Wrangler

Required for Cloudflare Pages deployment.

Check Node:

```bash
node --version
npm --version
```

Ubuntu install:

```bash
sudo apt update
sudo apt install -y nodejs npm
```

Install Wrangler:

```bash
sudo npm install -g wrangler
```

Check:

```bash
wrangler --version
```

## Cloudflare Credentials

Cloudflare credentials are only required when using `--deploy-target cloudflare`.

Template file:

- `cloudflare_credentials.json.example`

Recommended setup:

1. Copy the template.
2. Create `cloudflare_credentials.json`.
3. Fill in real `account_id` and `api_token` values.

```bash
cp cloudflare_credentials.json.example cloudflare_credentials.json
```

Example:

```json
{
  "account_id": "your_cloudflare_account_id",
  "api_token": "your_cloudflare_api_token",
  "kv_namespace_id": "optional_kv_namespace_id"
}
```

`cloudflare_credentials.json` is intentionally ignored by git.

## Wrangler Config Directory Permission

Wrangler writes under:

- `~/.config/.wrangler`

If your runtime environment makes that path read-only, deployment can fail during log/config writes. Point `XDG_CONFIG_HOME` to a writable directory.

Recommended:

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
mkdir -p "$XDG_CONFIG_HOME"
```

Test deploy command:

```bash
env XDG_CONFIG_HOME="$HOME/.codex/memories/.config" wrangler pages deploy www --project-name demo-game --branch production
```

## Required Repository Files

At minimum, keep these files in the project root:

- `rpgmaker_web_port.py`
- `_worker.js`
- `vpad.html`

Optional inputs:

- `patch.zip`
- `CN.json`

Input game requirements:

- A complete RPG Maker MV/MZ game directory
- The game directory must contain at least `index.html`, `js/`, and `data/`

Build output notes:

- The pipeline creates `www/`
- The pipeline writes filename mapping to `www/audio_rename_map.json`
- Build stops immediately if audio decryption/transcoding/normalization/validation fails

## Recommended Environment Variables

For stable long-term operation:

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
export PATH="$PATH:/usr/bin:/usr/local/bin"
```

Cloudflare account environment variables are not required by default; the pipeline reads `cloudflare_credentials.json` when needed.

## Minimal Preflight Check

Before running the pipeline:

```bash
python3 --version
ffmpeg -version | head -n 1
node --version
npm --version
wrangler --version
```

If you test mainly on iPhone/iPad, also confirm AAC availability:

```bash
ffmpeg -codecs | rg aac
```

## Recommended Execution

```bash
export XDG_CONFIG_HOME="$HOME/.codex/memories/.config"
python3 rpgmaker_web_port.py <project-name> --source ./Game
```

Default behavior is static deployment without KV auth.

Supported deployment targets:

```bash
python3 rpgmaker_web_port.py <project-name> --source ./Game --deploy-target cloudflare
python3 rpgmaker_web_port.py <project-name> --source ./Game --deploy-target local --output-dir ./dist/<project-name>
python3 rpgmaker_web_port.py <project-name> --source ./Game --deploy-target local --serve-local --local-port 8080
python3 rpgmaker_web_port.py <project-name> --source ./Game --deploy-target custom --custom-deploy-command 'rsync -av "$RPGMZ_WWW_DIR"/ user@host:/var/www/game/'
python3 rpgmaker_web_port.py <project-name> --source ./Game --deploy-target none
```

`custom` deploy receives:

- `RPGMZ_PROJECT_NAME`
- `RPGMZ_WWW_DIR`
- `RPGMZ_OUTPUT_DIR`
- `RPGMZ_BASE_DIR`

Enable KV auth page:

```bash
python3 rpgmaker_web_port.py <project-name> --source ./Game --enable-kv-auth
```

If the Cloudflare Pages project already binds `AUTH_CODES` and `ACCESS_SECRET_KEY`, you can use:

```bash
python3 rpgmaker_web_port.py <project-name> --source ./Game --enable-kv-auth --single-deploy
```

The access page should be presented as a technical exploration simulator, not as an official or commercial release.

Do not commit commercial game assets, private game packages, real Cloudflare credentials, auth-code databases, or generated build artifacts.

Default deploy branch:

```bash
production
```
