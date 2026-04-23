import os
import shutil
import subprocess
import sys

from pipeline.config import load_cloudflare_credentials


def deploy_build(project_name, runtime):
    """根据目标后端发布构建产物。"""
    prepare_access_worker(runtime)
    if runtime.deploy_target == "cloudflare":
        credentials = load_cloudflare_credentials(runtime.cloudflare_credentials_path)
        deploy_to_cloudflare(project_name, runtime, credentials)
    elif runtime.deploy_target == "local":
        deploy_to_local(project_name, runtime)
    elif runtime.deploy_target == "custom":
        deploy_to_custom(project_name, runtime)
    elif runtime.deploy_target == "none":
        print("\n🚀 [Step 11] 已跳过部署，仅保留构建产物。")
        print(f"  构建目录: {runtime.www_dir}")
    else:
        print(f"  [!] 未知部署目标: {runtime.deploy_target}")
        sys.exit(1)


def prepare_access_worker(runtime):
    """根据 KV 开关注入或清理 Cloudflare Pages Worker。"""
    worker_src = os.path.join(runtime.base_dir, "_worker.js")
    worker_dest = os.path.join(runtime.www_dir, "_worker.js")

    if runtime.enable_kv_auth:
        try:
            shutil.copy2(worker_src, worker_dest)
            print("   _worker.js KV 访问验证网关注入完成。")
        except FileNotFoundError:
            print(f"   致命错误：找不到 KV 访问验证网关文件 {worker_src}！流水线终止。")
            sys.exit(1)
    elif os.path.exists(worker_dest):
        os.remove(worker_dest)
        print("   已移除 www 中旧的 _worker.js，本次不启用 KV 访问验证。")


def deploy_to_cloudflare(project_name, runtime, credentials):
    """推送到 Cloudflare，可选注入 KV 访问验证网关。"""
    if runtime.enable_kv_auth:
        mode_text = "KV 访问验证部署" if not runtime.single_deploy else "KV 访问验证一次性部署"
    else:
        mode_text = "普通静态部署"
    print(f"\n🚀 [Step 11] 开始执行{mode_text}: {project_name} ...")

    env = os.environ.copy()
    env["CLOUDFLARE_ACCOUNT_ID"] = credentials.account_id
    env["CLOUDFLARE_API_TOKEN"] = credentials.api_token

    deploy_cmd = [
        "wrangler", "pages", "deploy",
        runtime.www_dir,
        "--project-name", project_name,
        "--branch", "production",
    ]

    print("\n   ⏳ [阶段一] 正在推送到 Cloudflare...")
    print("   " + "-" * 40)

    try:
        subprocess.run(deploy_cmd, env=env, check=True)
    except subprocess.CalledProcessError:
        print("\n   首次部署失败或被取消，请检查报错。")
        return

    if not runtime.enable_kv_auth:
        print("   " + "-" * 40)
        print("\n  普通静态部署完成，未启用 KV 访问验证。")
        return

    if runtime.single_deploy:
        print("   " + "-" * 40)
        print("\n  KV 访问验证单次部署完成。请确认 Cloudflare Pages 已绑定 AUTH_CODES。")
        return

    print("\n" + "!" * 55)
    print(" ⚠️ 关键操作：访问验证需要 KV 数据库绑定 ⚠️")
    print(f" 项目 '{project_name}' 已初步上线，但尚未连接 KV 数据库！")
    print(" 请立即前往 Cloudflare 网页端完成以下操作：")
    print(" 1. 进入 Workers & Pages -> 点击刚部署的项目")
    print(" 2. 点击顶部 Settings (设置) -> 左侧 Functions (函数)")
    print(" 3. 下拉找到 KV namespace bindings，点击 Add binding")
    print(" 4. Variable name 填入大写: AUTH_CODES")
    print(" 5. KV namespace 选择你的访问码数据库")
    print(" 6. 点击 Save (保存)")
    print("!" * 55)

    input("\n  完成网页端绑定后，请在这里按下【回车键】进行最终部署刷新...")

    print("\n   [阶段三] 正在重新部署，使 KV 绑定正式生效...")
    print("   " + "-" * 40)
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
        print("   " + "-" * 40)
        print("\n  KV 访问验证已启用，部署完成。")
    except subprocess.CalledProcessError:
        print("\n   二次部署失败。")


def deploy_to_local(project_name, runtime):
    """复制到本地输出目录，可选启动本地 HTTP 服务。"""
    print(f"\n🚀 [Step 11] 开始执行本地部署: {project_name} ...")
    output_dir = runtime.output_dir
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    shutil.copytree(runtime.www_dir, output_dir)
    print(f"  [+] 已复制 Web 构建产物到: {output_dir}")

    if not runtime.serve_local:
        print("  [+] 本地部署完成。可用任意静态服务器托管该目录。")
        return

    print(f"  [+] 正在启动本地 HTTP 服务: http://127.0.0.1:{runtime.local_port}")
    print("  [!] 该命令会阻塞当前终端，按 Ctrl+C 停止服务。")
    subprocess.run([
        sys.executable,
        "-m",
        "http.server",
        str(runtime.local_port),
        "--directory",
        output_dir,
    ], check=False)


def deploy_to_custom(project_name, runtime):
    """执行自定义部署命令，供 rsync、scp、Docker 或外部打包器接入。"""
    if not runtime.custom_deploy_command:
        print("  [!] --deploy-target custom 需要提供 --custom-deploy-command")
        sys.exit(1)

    print(f"\n🚀 [Step 11] 开始执行自定义部署: {project_name} ...")
    env = os.environ.copy()
    env["RPGMZ_PROJECT_NAME"] = project_name
    env["RPGMZ_WWW_DIR"] = runtime.www_dir
    env["RPGMZ_OUTPUT_DIR"] = runtime.output_dir
    env["RPGMZ_BASE_DIR"] = runtime.base_dir

    try:
        subprocess.run(runtime.custom_deploy_command, shell=True, env=env, check=True)
        print("  [+] 自定义部署命令执行完成。")
    except subprocess.CalledProcessError as exc:
        print(f"  [!] 自定义部署失败，退出码: {exc.returncode}")
        sys.exit(exc.returncode)
