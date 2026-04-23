import os
import re
import shutil
import sys


def detect_game_source_dir(base_dir, www_dir):
    """检测完整 PC 游戏目录，并作为 www 工作区来源。"""
    candidates = []
    non_www_candidates = []
    for entry in os.listdir(base_dir):
        path = os.path.join(base_dir, entry)
        if not os.path.isdir(path):
            continue
        if entry in [".git", ".wrangler", "__pycache__", "www", "pipeline"]:
            continue
        if os.path.exists(os.path.join(path, "index.html")) and \
           os.path.isdir(os.path.join(path, "js")) and \
           os.path.isdir(os.path.join(path, "data")):
            candidates.append(path)
            if os.path.abspath(path) != os.path.abspath(www_dir):
                non_www_candidates.append(path)

    if len(non_www_candidates) == 1:
        return non_www_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    if os.path.exists(www_dir):
        return www_dir
    return None


def prepare_www_workspace(base_dir, www_dir):
    """将完整 PC 目录复制成标准 www 工作目录。"""
    source_dir = detect_game_source_dir(base_dir, www_dir)
    if not source_dir:
        print("  [!] 未找到可用的游戏源目录。请提供 www 或完整 PC 游戏目录。")
        sys.exit(1)

    if os.path.abspath(source_dir) == os.path.abspath(www_dir):
        print(f"  [+] 使用现有 www 工作目录: {www_dir}")
        return

    print(f"\n>>> 预处理: 从源目录构建 www 工作区...")
    print(f"  [+] 源目录: {source_dir}")
    if os.path.exists(www_dir):
        shutil.rmtree(www_dir)
    shutil.copytree(source_dir, www_dir)
    print(f"  [+] 已复制到工作目录: {www_dir}")


def get_valid_project_name(game_name):
    """获取并修正为 Cloudflare 规范域名。"""
    raw_name = game_name
    name = raw_name.lower()
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"[^a-z0-9-]", "", name)
    name = name.strip("-")[:58].rstrip("-")

    if not name:
        print(f"❌ 错误：项目名 '{raw_name}' 无法转换！")
        sys.exit(1)
    return name
