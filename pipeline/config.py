import json
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    base_dir: str
    www_dir: str
    patch_zip: str
    system_json_path: str
    cloudflare_credentials_path: str
    vpad_html_path: str
    game_name: str
    single_deploy: bool
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
        print("❌ 错误：缺少游戏文件夹名称！")
        print("💡 用法: sudo python3 pipeline.py <游戏名> [--single-deploy]")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    game_name = argv[0]
    single_deploy = "--single-deploy" in argv[1:]
    www_dir = os.path.join(base_dir, "www")
    return RuntimeConfig(
        base_dir=base_dir,
        www_dir=www_dir,
        patch_zip=os.path.join(base_dir, "patch.zip"),
        system_json_path=os.path.join(www_dir, "data", "System.json"),
        cloudflare_credentials_path=os.path.join(base_dir, "cloudflare_credentials.json"),
        vpad_html_path=os.path.join(base_dir, "vpad.html"),
        game_name=game_name,
        single_deploy=single_deploy,
        save_prefix=game_name.upper() + "_",
        deploy_dir=os.path.join("/var/www/html/games", game_name),
        lobby_html_path="/var/www/html/index.html",
    )


def load_cloudflare_credentials(credentials_path):
    if not os.path.exists(credentials_path):
        print(f"  [!] 缺少 Cloudflare 凭证文件: {credentials_path}")
        print("  [!] 请参考 cloudflare_credentials.json.example 创建实际配置文件。")
        sys.exit(1)

    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            credentials = json.load(f)
    except Exception as e:
        print(f"  [!] Cloudflare 凭证文件解析失败: {e}")
        sys.exit(1)

    required_fields = ["account_id", "api_token"]
    missing_fields = [field for field in required_fields if not credentials.get(field)]
    if missing_fields:
        print(f"  [!] Cloudflare 凭证缺少必要字段: {', '.join(missing_fields)}")
        sys.exit(1)

    return CloudflareCredentials(
        account_id=credentials["account_id"],
        api_token=credentials["api_token"],
        kv_namespace_id=credentials.get("kv_namespace_id", ""),
    )
