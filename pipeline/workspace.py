import os
import re
import shutil
import sys


def detect_game_source_dir(base_dir, www_dir):
    """Detect a complete PC game directory to use as the web workspace source."""
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


def prepare_www_workspace(base_dir, www_dir, source_dir=""):
    """Copy a complete PC game directory into the web build workspace."""
    source_dir = source_dir or detect_game_source_dir(base_dir, www_dir)
    if not source_dir:
        print("  [!] No usable game source directory found. Provide --source or an existing web workspace.")
        sys.exit(1)
    if not os.path.exists(source_dir):
        print(f"  [!] Specified game source directory does not exist: {source_dir}")
        sys.exit(1)
    if not (
        os.path.exists(os.path.join(source_dir, "index.html"))
        and os.path.isdir(os.path.join(source_dir, "js"))
        and os.path.isdir(os.path.join(source_dir, "data"))
    ):
        print(f"  [!] Specified source directory is not a standard RPG Maker MV/MZ web structure: {source_dir}")
        sys.exit(1)

    if os.path.abspath(source_dir) == os.path.abspath(www_dir):
        print(f"  [+] Using existing web workspace: {www_dir}")
        return

    print("\n>>> Preprocess: building the web workspace from source...")
    print(f"  [+] Source directory: {source_dir}")
    if os.path.exists(www_dir):
        shutil.rmtree(www_dir)
    shutil.copytree(source_dir, www_dir)
    print(f"  [+] Copied to workspace: {www_dir}")


def get_valid_project_name(game_name):
    """Convert the project name into a Cloudflare-compatible slug."""
    raw_name = game_name
    name = raw_name.lower()
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"[^a-z0-9-]", "", name)
    name = name.strip("-")[:58].rstrip("-")

    if not name:
        print(f"[ERROR] Project name '{raw_name}' cannot be converted.")
        sys.exit(1)
    return name
