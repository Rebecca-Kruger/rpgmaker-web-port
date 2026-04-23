import glob
import json
import os
import shutil
import subprocess
import zipfile


def clean_pc_build(www_dir):
    """Step 0: remove desktop-only NW.js files from a PC export."""
    print("\n[Step 0] Cleaning desktop-only NW.js files from the PC export...")

    dirs_to_remove = ["locales", "swiftshader", "save"]
    for directory in dirs_to_remove:
        dir_path = os.path.join(www_dir, directory)
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"   Removed directory: {directory}/")
            except Exception as exc:
                print(f"   Failed to remove directory {directory}/: {exc}")

    files_to_remove = ["*.exe", "*.dll", "*.pak", "*.bin", "*.dat", "package.json"]
    clean_count = 0
    for pattern in files_to_remove:
        for file_path in glob.glob(os.path.join(www_dir, pattern)):
            try:
                os.remove(file_path)
                print(f"   Removed file: {os.path.basename(file_path)}")
                clean_count += 1
            except Exception as exc:
                print(f"   Failed to remove {os.path.basename(file_path)}: {exc}")

    if clean_count == 0:
        print("   No desktop-only files found. The workspace already looks web-ready.")
    else:
        print(f"   Cleanup complete. Removed {clean_count} desktop-only files.")


def apply_mtools_translation(base_dir, www_dir):
    """Apply MTools translation data without touching audio references."""
    cn_json_path = os.path.join(base_dir, "CN.json")
    if not os.path.exists(cn_json_path):
        print("\n [-] CN.json not found. Skipping MTools translation injection.")
        return

    print("\n>>> CN.json found. Injecting translated text into data files...")
    try:
        with open(cn_json_path, "r", encoding="utf-8") as file:
            translation_dict = json.load(file)
    except Exception as exc:
        print(f"  [!] Failed to parse CN.json: {exc}")
        return

    def translate_node(node):
        if not isinstance(node, (dict, list)):
            return node
        if isinstance(node, dict):
            new_dict = {}
            is_audio_obj = "volume" in node and "pitch" in node
            for key, value in node.items():
                if isinstance(value, str):
                    if is_audio_obj and key == "name":
                        new_dict[key] = value
                    elif key in [
                        "name", "description", "message1", "message2",
                        "message3", "message4", "profile", "nickname", "note",
                    ]:
                        new_dict[key] = translation_dict.get(value, value)
                    else:
                        new_dict[key] = value
                elif isinstance(value, list):
                    if key in [
                        "elements", "skillTypes", "weaponTypes", "armorTypes",
                        "equipTypes", "basic", "params", "commands",
                    ]:
                        new_dict[key] = [
                            translation_dict.get(item, item) if isinstance(item, str) else translate_node(item)
                            for item in value
                        ]
                    elif key == "parameters" and node.get("code") in [401, 405]:
                        new_dict[key] = [
                            translation_dict.get(item, item) if isinstance(item, str) else translate_node(item)
                            for item in value
                        ]
                    elif key == "parameters" and node.get("code") == 102:
                        new_params = []
                        for index, param in enumerate(value):
                            if index == 0 and isinstance(param, list):
                                new_params.append([
                                    translation_dict.get(choice, choice) if isinstance(choice, str) else choice
                                    for choice in param
                                ])
                            else:
                                new_params.append(translate_node(param))
                        new_dict[key] = new_params
                    else:
                        new_dict[key] = translate_node(value)
                elif isinstance(value, dict):
                    if key == "messages":
                        new_dict[key] = {
                            inner_key: translation_dict.get(inner_value, inner_value) if isinstance(inner_value, str) else translate_node(inner_value)
                            for inner_key, inner_value in value.items()
                        }
                    else:
                        new_dict[key] = translate_node(value)
                else:
                    new_dict[key] = value
            return new_dict
        return [translate_node(item) for item in node]

    data_dir = os.path.join(www_dir, "data")
    if not os.path.exists(data_dir):
        return

    modified_files = 0
    for filename in os.listdir(data_dir):
        if not filename.endswith(".json"):
            continue
        file_path = os.path.join(data_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                game_data = json.load(file)
            translated_data = translate_node(game_data)
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(translated_data, file, ensure_ascii=False, separators=(",", ":"))
            modified_files += 1
        except Exception:
            pass
    print(f"  [+] Translation injection complete. Processed {modified_files} data files.")


def apply_patch(patch_zip, www_dir):
    """Extract patch.zip into the web workspace."""
    print("\n>>> Step 1: Checking optional patch.zip...")
    if not os.path.exists(patch_zip):
        print("  [-] patch.zip not found. Skipping patch merge.")
        return
    print(f"  [+] Found {patch_zip}, extracting...")
    with zipfile.ZipFile(patch_zip, "r") as zip_ref:
        zip_ref.extractall(www_dir)
    print("  [+] Patch merge complete.")


def patch_system_json(system_json_path):
    """Disable encryption flags in System.json and extract the encryption key."""
    print("\n>>> Step 3: Parsing System.json and extracting the encryption key...")
    if not os.path.exists(system_json_path):
        print("  [!] System.json not found. Confirm this is a standard MV/MZ project.")
        return None

    with open(system_json_path, "r", encoding="utf-8-sig") as file:
        data = json.load(file)

    key_hex = data.get("encryptionKey", "")
    modified = False
    if data.get("hasEncryptedImages"):
        data["hasEncryptedImages"] = False
        modified = True
    if data.get("hasEncryptedAudio"):
        data["hasEncryptedAudio"] = False
        modified = True

    if modified:
        with open(system_json_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
        print("  [+] Encryption flags disabled in System.json.")

    if key_hex:
        print(f"  [+] Extracted 32-character encryption key: {key_hex}")
        return bytes.fromhex(key_hex)
    return None


def _decrypt_single_file(file_path, key_bytes, target_ext):
    """Decrypt one encrypted RPG Maker asset."""
    try:
        with open(file_path, "rb") as file:
            header = file.read(16)
            if b"RPG" not in header:
                return False
            encrypted_head = file.read(16)
            actual_len = len(encrypted_head)
            decrypted_head = bytearray(actual_len)
            for index in range(actual_len):
                decrypted_head[index] = encrypted_head[index] ^ key_bytes[index]
            rest_data = file.read()

        new_path = file_path.rsplit(".", 1)[0] + target_ext
        with open(new_path, "wb") as file:
            file.write(decrypted_head)
            file.write(rest_data)

        os.remove(file_path)
        return True
    except Exception as exc:
        print(f"  [!] Failed to decrypt {file_path}: {str(exc)}")
        return False


def decrypt_assets(www_dir, key_bytes):
    """Batch-decrypt asset files for MV/MZ suffixes."""
    print("\n>>> Step 4: Decrypting asset files for MV/MZ...")
    if not key_bytes:
        print("  [-] Encryption key missing. Skipping decryption.")
        return

    img_count = 0
    audio_count = 0

    for root, _, files in os.walk(www_dir):
        for filename in files:
            file_path = os.path.join(root, filename)
            if filename.endswith(".png_") or filename.endswith(".rpgmvp"):
                if _decrypt_single_file(file_path, key_bytes, ".png"):
                    img_count += 1
            elif filename.endswith(".ogg_") or filename.endswith(".rpgmvo"):
                if _decrypt_single_file(file_path, key_bytes, ".ogg"):
                    audio_count += 1
            elif filename.endswith(".m4a_"):
                if _decrypt_single_file(file_path, key_bytes, ".m4a"):
                    audio_count += 1

    print(f"  [+] Decryption complete. Decrypted {img_count} images and {audio_count} audio files.")


def convert_video_to_mp4(www_dir):
    """Convert .webm movies to .mp4."""
    print("\n>>> Scanning and converting movies to mp4...")
    movies_dir = os.path.join(www_dir, "movies")
    if not os.path.exists(movies_dir):
        return

    converted_count = 0
    for root, _, files in os.walk(movies_dir):
        for filename in files:
            if not filename.endswith(".webm"):
                continue
            old_path = os.path.join(root, filename)
            base_name = os.path.splitext(filename)[0]
            new_path = os.path.join(root, base_name + ".mp4")
            if os.path.exists(new_path):
                continue

            cmd = [
                "ffmpeg", "-y", "-i", old_path,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", new_path,
            ]
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0:
                    converted_count += 1
            except Exception:
                pass
    print(f"  [+] Video conversion complete. Converted {converted_count} files.")


def fix_resource_percent_symbols(target_dir):
    """Replace percent symbols in resource filenames."""
    print("\n>>> Step 7: Replacing percent symbols in resource filenames...")
    img_dir = os.path.join(target_dir, "img")
    data_dir = os.path.join(target_dir, "data")
    renamed_map = {}

    if os.path.exists(img_dir):
        for root, _, files in os.walk(img_dir):
            for filename in files:
                if "%" not in filename:
                    continue
                old_path = os.path.join(root, filename)
                new_filename = filename.replace("%", "_")
                new_path = os.path.join(root, new_filename)
                os.rename(old_path, new_path)

                old_base = os.path.splitext(filename)[0]
                new_base = os.path.splitext(new_filename)[0]
                renamed_map[old_base] = new_base

    if renamed_map and os.path.exists(data_dir):
        for root, _, files in os.walk(data_dir):
            for filename in files:
                if not filename.endswith(".json"):
                    continue
                file_path = os.path.join(root, filename)
                with open(file_path, "r", encoding="utf-8") as file:
                    content = file.read()
                modified = False
                for old_base, new_base in renamed_map.items():
                    if old_base in content:
                        content = content.replace(old_base, new_base)
                        modified = True
                if modified:
                    with open(file_path, "w", encoding="utf-8") as file:
                        file.write(content)
    print("  [+] Resource filename cleanup complete.")
