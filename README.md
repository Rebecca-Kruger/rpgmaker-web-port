# RPGMZ Web Porting Toolkit

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

Turn an RPG Maker MV/MZ PC package into a mobile-friendly web build that can be deployed to Cloudflare Pages, a local directory, or a custom server.

This project exists for a very specific pain:

- PC exports are not directly usable on the web
- iPhone/iPad audio compatibility is easy to break
- encrypted assets, non-ASCII filenames, NW.js leftovers, and plugin edge cases turn into deployment bugs
- most guides stop at “it boots in browser”, not “it actually works on mobile Safari”

This is a PC-package-to-web pipeline for RPG Maker MV/MZ projects. It focuses on the practical conversion and compatibility steps needed before a desktop export can run reliably in a browser or WebView.

## Feedback and Bug Reports

If you deploy any RPG Maker MV/MZ game with this toolkit and hit a bug, please open an Issue.

Include the game type, platform, and a short reproduction path when possible. I will review reports and try to ship fixes quickly.

## Why This Project Exists

If you have ever tried to deploy an RPG Maker MV/MZ game as a web game, you have probably run into some combination of:

- encrypted audio and image assets that still expect desktop behavior
- iOS Safari failing on some `.ogg` files but not others
- non-ASCII filenames that look fine locally and then fail in browser delivery chains
- NW.js desktop files bloating the package
- plugin behavior that works on desktop but breaks mobile browser assumptions
- no practical way to debug audio on iPhone without going half blind in remote devtools

This repository packages those fixes into one build flow.

## What It Does

Current pipeline capabilities:

- detects a full MV/MZ game folder and rebuilds a clean `www/` workspace
- strips NW.js/desktop-only files from PC exports
- optionally merges `patch.zip`
- optionally injects `CN.json` translation content
- disables RPG Maker asset encryption flags and decrypts image/audio assets
- converts audio to `m4a` for iPhone/iPad compatibility
- forces iPhone/iPad builds to request `m4a`, while other platforms keep `ogg`
- prevents `m4a` from being incorrectly routed into the `VorbisDecoder` path
- normalizes non-ASCII audio filenames to ASCII-safe names and rewrites references
- validates audio build consistency before deployment
- converts `webm` movies to `mp4`
- injects browser compatibility patches, mobile controls, and selected runtime fixes
- injects optional iPhone-side audio debugging via `?audioDebug=1`
- deploys the final build to Cloudflare Pages, a local directory, a custom command, or build-only output

## Why It Is Different From Random Scripts

Most one-off scripts can “make the title screen appear in a browser”.

This project is trying to be useful one level deeper:

- it treats iOS audio as a first-class deployment problem
- it validates the final output instead of trusting the build blindly
- it includes a real device debugging path for Safari audio failures
- it handles filename normalization and reference rewriting instead of punting that work to the user
- it keeps the final deployment step in the same toolchain

That is the real value proposition: not just browser boot, but browser delivery hardening.

## Who This Is For

This project is a good fit if you are:

- shipping an RPG Maker MV/MZ game as a browser game
- targeting iPhone/iPad as real supported devices
- deploying to Cloudflare Pages
- tired of manually patching `index.html`, audio files, and runtime JS every time

This project is probably not the right fit if:

- you want to create or manage RPG Maker plugins
- you need a polished GUI app instead of a build pipeline
- you are not deploying web builds at all

## Current Workflow

The public entrypoint is:

```bash
python3 rpgmaker_web_port.py <project-name> --source ./Game
```

Typical usage:

```bash
python3 rpgmaker_web_port.py demo-game --source ./examples/MyGame --deploy-target local --output-dir ./dist/demo-game
```

Choose a deployment target:

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target cloudflare
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target local --output-dir ./dist/demo-game
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target local --serve-local --local-port 8080
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target custom --custom-deploy-command 'rsync -av "$RPGMZ_WWW_DIR"/ user@host:/var/www/game/'
python3 rpgmaker_web_port.py demo-game --source ./Game --deploy-target none
```

Deployment targets:

- `cloudflare`: deploys to Cloudflare Pages, the default.
- `local`: copies the final web build to a local directory.
- `custom`: runs your own deployment command with build paths exposed as environment variables.
- `none`: builds only and leaves the final output in the build directory.

Enable Cloudflare KV access verification only when you need a gated demo:

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --enable-kv-auth
```

Use `--single-deploy` together with `--enable-kv-auth` only when the Cloudflare Pages project already has the `AUTH_CODES` KV binding and `ACCESS_SECRET_KEY` environment variable configured:

```bash
python3 rpgmaker_web_port.py demo-game --source ./Game --enable-kv-auth --single-deploy
```

The source directory should be a full RPG Maker MV/MZ game directory with at least:

- `index.html`
- `js/`
- `data/`

### Required Files

- `rpgmaker_web_port.py`
- `vpad.html`

### Optional Files

- `cloudflare_credentials.json` for Cloudflare deployment
- `patch.zip`
- `CN.json`
- `_worker.js` if `--enable-kv-auth` is used

## Cloudflare Credentials

Real credentials are only required for the `cloudflare` deployment target. They are read from:

- `cloudflare_credentials.json`

Template:

- `cloudflare_credentials.json.example`

The real credential file is ignored by git.

Example:

```json
{
  "account_id": "your_cloudflare_account_id",
  "api_token": "your_cloudflare_api_token",
  "kv_namespace_id": "optional_kv_namespace_id"
}
```

## Optional KV Access Verification

By default, the pipeline deploys a normal static Cloudflare Pages build.

If `--enable-kv-auth` is provided, the pipeline copies `_worker.js` into the build directory and enables a Cloudflare Pages Worker gate backed by:

- `AUTH_CODES`: KV namespace binding
- `ACCESS_SECRET_KEY`: Worker environment variable used for token signing

The verification page describes the build as a technical exploration simulator. It should not present itself as an official or licensed product.

## Custom Deployment Hooks

For `--deploy-target custom`, the command receives these environment variables:

- `RPGMZ_PROJECT_NAME`
- `RPGMZ_WWW_DIR`
- `RPGMZ_OUTPUT_DIR`
- `RPGMZ_BASE_DIR`

This is intended for custom servers, Docker images, rsync/scp publishing, or later packaging the generated web runtime into a native wrapper.

## iPhone / iPad Debugging

To debug web audio on iPhone/iPad:

```text
?audioDebug=1
```

This enables an on-screen audio debug panel inside the game page. It logs:

- `playBgm` / `playBgs`
- actual audio URLs being loaded
- `decode` / `error`
- chosen audio extension
- decoder path selection
- visibility and page lifecycle events

This exists because remote debugging Safari audio failures is much slower than just reading the log on device.

## Current Output Guarantees

Before deployment, the pipeline now checks:

- encrypted audio leftovers are gone
- decrypted `.ogg` files exist
- `.m4a` pairs exist where expected
- renamed audio references are consistent

If those checks fail, deployment stops.

## Repository Direction

This branch is the beginning of a larger cleanup.

The project is moving from:

- a monolithic personal deployment script

toward:

- a modular RPG Maker web porting toolkit

### Stage 1 Refactor Goal

Keep behavior stable while splitting responsibilities into modules:

- runtime config
- workspace preparation
- deployment
- resource processing
- audio handling
- validation

The goal of this phase is not “rewrite everything”. The goal is:

- reduce accidental regressions
- make fixes auditable
- make the tool usable by someone other than the original author

## Roadmap

Planned high-value improvements:

- split resource processing and audio handling into dedicated modules
- add sample-build regression tests
- generate structured build reports
- make debug injection easier to toggle by environment
- improve support matrix documentation for MV vs MZ and iOS vs non-iOS
- add a cleaner public-facing CLI interface

## Limitations

Current limitations are intentional and should be explicit:

- Cloudflare Pages is still the most complete deployment backend, but local and custom targets are now supported
- the codebase is mid-refactor, not a polished end-user application
- it still uses targeted runtime patch injection for some compatibility fixes
- not every RPG Maker plugin stack will behave identically on the web

## Why This Could Be a Good Open Source Project

The pitch is not “look at my deployment script”.

The pitch is:

> A practical toolkit for shipping RPG Maker MV/MZ games to the web, with real iPhone/iPad audio fixes and deployment hardening built in.

That is a much better open source story, because it is:

- narrow enough to be useful
- painful enough that people search for it
- specific enough to demonstrate value fast

## Status

This branch is the refactor track:

- branch: `refactor/stage1-pipeline`
- goal: turn the current pipeline into a maintainable toolkit without breaking working behavior

If you are evaluating this repository as an open source product, this is the right framing:

- a PC package to web build pipeline for RPG Maker MV/MZ
- a deployment and compatibility toolkit for RPG Maker web shipping
- a foundation for future desktop, server, or app-based importers

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
