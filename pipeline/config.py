import json
import os
import shlex
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    base_dir: str
    source_dir: str
    www_dir: str
    patch_zip: str
    system_json_path: str
    cloudflare_credentials_path: str
    vpad_html_path: str
    game_name: str
    deploy_target: str
    output_dir: str
    custom_deploy_command: str
    serve_local: bool
    local_port: int
    single_deploy: bool
    enable_kv_auth: bool
    save_prefix: str
    deploy_dir: str
    lobby_html_path: str


@dataclass(frozen=True)
class CloudflareCredentials:
    account_id: str
    api_token: str
    kv_namespace_id: str = ""


def load_runtime_config(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("[ERROR] Missing project name.")
        print("Usage: python3 rpgmaker_web_port.py <project-name> [--source ./Game] [--deploy-target cloudflare|local|custom|none]")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    game_name = argv[0]
    options = _parse_options(argv[1:])
    deploy_target = options.get("deploy_target", "cloudflare")
    if deploy_target not in {"cloudflare", "local", "custom", "none"}:
        print(f"[ERROR] Unknown deploy target {deploy_target}")
        print("Allowed values: cloudflare, local, custom, none")
        sys.exit(1)
    if deploy_target != "cloudflare" and options.get("enable_kv_auth", False):
        print("[ERROR] --enable-kv-auth is currently supported only for Cloudflare Pages deployments.")
        sys.exit(1)

    local_port = int(options.get("local_port", "8080"))
    source_dir = options.get("source_dir", "")
    if source_dir:
        source_dir = os.path.abspath(source_dir)
    www_dir = os.path.abspath(options.get("build_dir") or os.path.join(base_dir, "www"))
    output_dir = options.get("output_dir")
    if output_dir:
        output_dir = os.path.abspath(output_dir)
    else:
        output_dir = os.path.join(base_dir, "dist", game_name)
    return RuntimeConfig(
        base_dir=base_dir,
        source_dir=source_dir,
        www_dir=www_dir,
        patch_zip=os.path.join(base_dir, "patch.zip"),
        system_json_path=os.path.join(www_dir, "data", "System.json"),
        cloudflare_credentials_path=os.path.join(base_dir, "cloudflare_credentials.json"),
        vpad_html_path=os.path.join(base_dir, "vpad.html"),
        game_name=game_name,
        deploy_target=deploy_target,
        output_dir=output_dir,
        custom_deploy_command=options.get("custom_deploy_command", ""),
        serve_local=options.get("serve_local", False),
        local_port=local_port,
        single_deploy=options.get("single_deploy", False),
        enable_kv_auth=options.get("enable_kv_auth", False),
        save_prefix=game_name.upper() + "_",
        deploy_dir=os.path.join("/var/www/html/games", game_name),
        lobby_html_path="/var/www/html/index.html",
    )


def _parse_options(args):
    options = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--single-deploy":
            options["single_deploy"] = True
        elif arg == "--enable-kv-auth":
            options["enable_kv_auth"] = True
        elif arg == "--serve-local":
            options["serve_local"] = True
        elif arg in {"--source", "--build-dir", "--deploy-target", "--output-dir", "--custom-deploy-command", "--local-port"}:
            if index + 1 >= len(args):
                print(f"[ERROR] {arg} requires a value")
                sys.exit(1)
            value = args[index + 1]
            if arg == "--source":
                options["source_dir"] = value
            elif arg == "--build-dir":
                options["build_dir"] = value
            elif arg == "--deploy-target":
                options["deploy_target"] = value
            elif arg == "--output-dir":
                options["output_dir"] = value
            elif arg == "--custom-deploy-command":
                options["custom_deploy_command"] = value
            elif arg == "--local-port":
                options["local_port"] = value
            index += 1
        else:
            print(f"[ERROR] Unknown argument {shlex.quote(arg)}")
            sys.exit(1)
        index += 1
    return options


def load_cloudflare_credentials(credentials_path):
    if not os.path.exists(credentials_path):
        print(f"  [!] Missing Cloudflare credentials file: {credentials_path}")
        print("  [!] Create a real config file from cloudflare_credentials.json.example.")
        sys.exit(1)

    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            credentials = json.load(f)
    except Exception as e:
        print(f"  [!] Failed to parse Cloudflare credentials file: {e}")
        sys.exit(1)

    required_fields = ["account_id", "api_token"]
    missing_fields = [field for field in required_fields if not credentials.get(field)]
    if missing_fields:
        print(f"  [!] Cloudflare credentials missing required fields: {', '.join(missing_fields)}")
        sys.exit(1)

    return CloudflareCredentials(
        account_id=credentials["account_id"],
        api_token=credentials["api_token"],
        kv_namespace_id=credentials.get("kv_namespace_id", ""),
    )
