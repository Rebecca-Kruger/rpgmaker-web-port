import os
import shutil
import subprocess
import sys


def deploy_to_cloudflare(project_name, runtime, credentials):
    """推送到 Cloudflare 并注入防伪网关。"""
    mode_text = "一次性部署" if runtime.single_deploy else "部署 (含手动 KV 绑定确认)"
    print(f"\n🚀 [Step 11] 开始执行{mode_text}: {project_name} ...")

    worker_src = os.path.join(runtime.base_dir, "_worker.js")
    worker_dest = os.path.join(runtime.www_dir, "_worker.js")

    try:
        shutil.copy2(worker_src, worker_dest)
        print("   _worker.js 注入完成。")
    except FileNotFoundError:
        print(f"   致命错误：找不到防伪网关文件 {worker_src}！流水线终止。")
        sys.exit(1)

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

    if runtime.single_deploy:
        print("   " + "-" * 40)
        print("\n  单次部署完成！")
        return

    print("\n" + "!" * 55)
    print(" ⚠️ 关键操作：守卫需要数据库钥匙 ⚠️")
    print(f" 项目 '{project_name}' 已初步上线，但尚未连接 KV 数据库！")
    print(" 请立即前往 Cloudflare 网页端完成以下操作：")
    print(" 1. 进入 Workers & Pages -> 点击刚部署的项目")
    print(" 2. 点击顶部 Settings (设置) -> 左侧 Functions (函数)")
    print(" 3. 下拉找到 KV namespace bindings，点击 Add binding")
    print(" 4. Variable name 填入大写: AUTH_CODES")
    print(" 5. KV namespace 选择你的防伪数据库")
    print(" 6. 点击 Save (保存)")
    print("!" * 55)

    input("\n  完成网页端绑定后，请在这里按下【回车键】进行最终部署刷新...")

    print("\n   [阶段三] 正在重新部署，使 KV 绑定正式生效...")
    print("   " + "-" * 40)
    try:
        subprocess.run(deploy_cmd, env=env, check=True)
        print("   " + "-" * 40)
        print("\n  恭喜！大门已锁死，部署大功告成！")
    except subprocess.CalledProcessError:
        print("\n   二次部署失败。")
