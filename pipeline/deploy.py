import os
import shutil
import subprocess
import sys

from pipeline.config import load_cloudflare_credentials


def deploy_build(project_name, runtime):
    """Publish the build through the selected backend."""
    prepare_access_worker(runtime)
    if runtime.deploy_target == "cloudflare":
        credentials = load_cloudflare_credentials(runtime.cloudflare_credentials_path)
        deploy_to_cloudflare(project_name, runtime, credentials)
    elif runtime.deploy_target == "local":
        deploy_to_local(project_name, runtime)
    elif runtime.deploy_target == "custom":
        deploy_to_custom(project_name, runtime)
    elif runtime.deploy_target == "none":
        print("\n[Step 11] Deployment skipped. Build output is kept locally.")
        print(f"  Build directory: {runtime.www_dir}")
    else:
        print(f"  [!] Unknown deploy target: {runtime.deploy_target}")
        sys.exit(1)


def prepare_access_worker(runtime):
    """Inject or remove the Cloudflare Pages Worker based on KV auth settings."""
    worker_src = os.path.join(runtime.base_dir, "_worker.js")
    worker_dest = os.path.join(runtime.www_dir, "_worker.js")

    if runtime.enable_kv_auth:
        try:
            shutil.copy2(worker_src, worker_dest)
            print("   _worker.js KV access gate injected.")
        except FileNotFoundError:
            print(f"   Fatal error: missing KV access gate file {worker_src}!Pipeline stopped.")
            sys.exit(1)
    elif os.path.exists(worker_dest):
        os.remove(worker_dest)
        print("   Removed stale www/_worker.js because KV access auth is disabled.")


def deploy_to_cloudflare(project_name, runtime, credentials):
    """Deploy to Cloudflare with optional KV access verification."""
    if runtime.enable_kv_auth:
        mode_text = "Cloudflare deployment with KV access auth" if not runtime.single_deploy else "single-pass Cloudflare deployment with KV access auth"
    else:
        mode_text = "static Cloudflare deployment"
    print(f"\n[Step 11] Starting {mode_text}: {project_name} ...")

    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = credentials.account_id
    env["CLOUDFLARE_API_TOKEN"] = credentials.api_token

    deploy_cmd = [
        "wrangler", "pages", "deploy",
        runtime.www_dir,
        "--project-name", project_name,
        "--branch", "production",
    ]

    print("\n   [Phase 1] Deploying to Cloudflare...")
    print("   " + "-" * 40)

    try:
        subprocess.run(deploy_cmd, env=env, check=True)
    except subprocess.CalledProcessError:
        print("\n   Initial deployment failed or was cancelled. Check the error above.")
        return

    if not runtime.enable_kv_auth:
        print("   " + "-" * 40)
        print("\n  Static Cloudflare deployment complete. KV access auth is disabled.")
        return

    if runtime.single_deploy:
        print("   " + "-" * 40)
        print("\n  Single-pass KV auth deployment complete. Confirm AUTH_CODES is bound in Cloudflare Pages.")
        return

    print("\n" + "!" * 55)
    print(" Action required: access verification needs a KV binding")
    print(f" Project '{project_name}' has been deployed once but is not connected to KV yet.")
    print(" Complete these steps in the Cloudflare dashboard:")
    print(" 1. Open Workers & Pages and select the deployed project")
    print(" 2. Open Settings, then Functions")
    print(" 3. Find KV namespace bindings and click Add binding")
    print(" 4. Set Variable name to AUTH_CODES")
    print(" 5. Select the KV namespace for access codes")
    print(" 6. Add ACCESS_SECRET_KEY under Environment variables")
    print(" 7. Click Save")
    print("!" * 55)

    input("\n  After binding KV in the dashboard, press Enter here to redeploy...")

    print("\n   [Phase 3] Redeploying so the KV binding takes effect...")
    print("   " + "-" * 40)
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
        print("   " + "-" * 40)
        print("\n  KV access auth is enabled. Deployment complete.")
    except subprocess.CalledProcessError:
        print("\n   Second deployment failed.")


def deploy_to_local(project_name, runtime):
    """Copy the build to a local output directory and optionally start an HTTP server."""
    print(f"\n[Step 11] Starting local deployment: {project_name} ...")
    output_dir = runtime.output_dir
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    shutil.copytree(runtime.www_dir, output_dir)
    print(f"  [+] Copied web build to: {output_dir}")

    if not runtime.serve_local:
        print("  [+] Local deployment complete. Serve this directory with any static server.")
        return

    print(f"  [+] Starting local HTTP server: http://127.0.0.1:{runtime.local_port}")
    print("  [!] This command blocks the terminal. Press Ctrl+C to stop the server.")
    subprocess.run([
        sys.executable,
        "-m",
        "http.server",
        str(runtime.local_port),
        "--directory",
        output_dir,
    ], check=False)


def deploy_to_custom(project_name, runtime):
    """Run a custom deployment command for rsync, scp, Docker, or external packagers."""
    if not runtime.custom_deploy_command:
        print("  [!] --deploy-target custom requires --custom-deploy-command")
        sys.exit(1)

    print(f"\n[Step 11] Starting custom deployment: {project_name} ...")
    env = os.environ.copy()
    env["RPGMZ_PROJECT_NAME"] = project_name
    env["RPGMZ_WWW_DIR"] = runtime.www_dir
    env["RPGMZ_OUTPUT_DIR"] = runtime.output_dir
    env["RPGMZ_BASE_DIR"] = runtime.base_dir

    try:
        subprocess.run(runtime.custom_deploy_command, shell=True, env=env, check=True)
        print("  [+] Custom deployment command completed.")
    except subprocess.CalledProcessError as exc:
        print(f"  [!] Custom deployment failed with exit code: {exc.returncode}")
        sys.exit(exc.returncode)
