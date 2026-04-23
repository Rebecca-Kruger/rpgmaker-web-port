import json
import os
import shutil
import subprocess
import sys


def convert_audio_to_m4a(www_dir):
    """将 ogg 批量转码为 m4a"""
    print("\n>>> 步骤 5: 转换音频格式为 iOS 兼容的 m4a...")
    audio_dir = os.path.join(www_dir, "audio")
    if not os.path.exists(audio_dir):
        return

    converted_count = 0
    synthesized_silence_count = 0

    def synthesize_silence_audio(target_path, lower_file):
        """为 0 byte 音频合成一段极短静音，避免 ffmpeg 因空文件直接失败。"""
        if lower_file.endswith(".ogg"):
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "0.3",
                "-c:a", "libvorbis",
                target_path,
                "-loglevel", "error",
            ]
        elif lower_file.endswith(".wav"):
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "0.3",
                "-c:a", "pcm_s16le",
                target_path,
                "-loglevel", "error",
            ]
        else:
            return False

        subprocess.run(cmd, check=True)
        return True

    for root, _, files in os.walk(audio_dir):
        for filename in files:
            lower_file = filename.lower()
            if not (lower_file.endswith(".ogg") or lower_file.endswith(".wav")):
                continue

            orig_path = os.path.join(root, filename)
            base_name = filename.rsplit(".", 1)[0]
            m4a_path = os.path.join(root, base_name + ".m4a")

            try:
                if os.path.getsize(orig_path) == 0:
                    print(f"  [!] 检测到 0 byte 音频，正在补静音: {filename}")
                    synthesize_silence_audio(orig_path, lower_file)
                    synthesized_silence_count += 1
            except subprocess.CalledProcessError:
                print(f"  [!] 0 byte 音频静音补写失败，流水线终止: {filename}")
                raise

            if not os.path.exists(m4a_path):
                cmd = [
                    "ffmpeg", "-y", "-i", orig_path,
                    "-c:a", "aac", "-b:a", "128k", m4a_path,
                    "-loglevel", "error",
                ]
                try:
                    subprocess.run(cmd, check=True)
                    converted_count += 1
                except subprocess.CalledProcessError:
                    print(f"  [!] 转码失败跳过: {filename}")
                    continue

            if lower_file.endswith(".wav"):
                os.remove(orig_path)
                shutil.copy2(m4a_path, orig_path)
                print(f"  [伪装成功] 已将巨型 {filename} 替换为 128k aac 内核，安全越过 25MB 红线！")

    print(f"  [+] 音频转码结束，处理了 {converted_count} 个文件，补写了 {synthesized_silence_count} 个空白音频。")


def sanitize_audio_filenames(www_dir):
    """将非 ASCII 音频文件名改为安全 ASCII，并同步重写数据引用。"""
    print("\n>>> 步骤 5.3: ASCII 化音频文件名并重写引用...")
    audio_dir = os.path.join(www_dir, "audio")
    data_dir = os.path.join(www_dir, "data")
    plugins_js_path = os.path.join(www_dir, "js", "plugins.js")
    if not os.path.exists(audio_dir):
        print("  [-] 未找到 audio 目录，跳过音频文件名修复。")
        return

    def is_ascii(text):
        return all(ord(ch) < 128 for ch in text)

    def replace_audio_refs(node, mapping_by_folder):
        if isinstance(node, list):
            for item in node:
                replace_audio_refs(item, mapping_by_folder)
            return
        if not isinstance(node, dict):
            return

        if isinstance(node.get("bgm"), dict):
            old_name = node["bgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["bgm"]["name"] = mapping_by_folder["bgm"][old_name]

        if isinstance(node.get("bgs"), dict):
            old_name = node["bgs"].get("name")
            if old_name in mapping_by_folder["bgs"]:
                node["bgs"]["name"] = mapping_by_folder["bgs"][old_name]

        if "sounds" in node and isinstance(node["sounds"], list):
            for sound in node["sounds"]:
                if isinstance(sound, dict):
                    old_name = sound.get("name")
                    if old_name in mapping_by_folder["se"]:
                        sound["name"] = mapping_by_folder["se"][old_name]

        if isinstance(node.get("battleBgm"), dict):
            old_name = node["battleBgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["battleBgm"]["name"] = mapping_by_folder["bgm"][old_name]

        if isinstance(node.get("titleBgm"), dict):
            old_name = node["titleBgm"].get("name")
            if old_name in mapping_by_folder["bgm"]:
                node["titleBgm"]["name"] = mapping_by_folder["bgm"][old_name]

        for key in ("boat", "ship", "airship"):
            if isinstance(node.get(key), dict) and isinstance(node[key].get("bgm"), dict):
                old_name = node[key]["bgm"].get("name")
                if old_name in mapping_by_folder["bgm"]:
                    node[key]["bgm"]["name"] = mapping_by_folder["bgm"][old_name]

        for key in ("victoryMe", "defeatMe", "gameoverMe"):
            if isinstance(node.get(key), dict):
                old_name = node[key].get("name")
                if old_name in mapping_by_folder["me"]:
                    node[key]["name"] = mapping_by_folder["me"][old_name]

        code = node.get("code")
        params = node.get("parameters")
        if isinstance(code, int) and isinstance(params, list) and params and isinstance(params[0], dict):
            audio = params[0]
            if code in (241, 132):
                if audio.get("name") in mapping_by_folder["bgm"]:
                    audio["name"] = mapping_by_folder["bgm"][audio["name"]]
            elif code == 245:
                if audio.get("name") in mapping_by_folder["bgs"]:
                    audio["name"] = mapping_by_folder["bgs"][audio["name"]]
            elif code == 249:
                if audio.get("name") in mapping_by_folder["me"]:
                    audio["name"] = mapping_by_folder["me"][audio["name"]]
            elif code == 250:
                if audio.get("name") in mapping_by_folder["se"]:
                    audio["name"] = mapping_by_folder["se"][audio["name"]]

        for value in node.values():
            replace_audio_refs(value, mapping_by_folder)

    mapping_by_folder = {folder: {} for folder in ["bgm", "bgs", "me", "se"]}
    total_renamed = 0

    for folder in ["bgm", "bgs", "me", "se"]:
        folder_dir = os.path.join(audio_dir, folder)
        if not os.path.exists(folder_dir):
            continue

        grouped_files = {}
        for filename in os.listdir(folder_dir):
            full_path = os.path.join(folder_dir, filename)
            if not os.path.isfile(full_path):
                continue
            base, ext = os.path.splitext(filename)
            grouped_files.setdefault(base, []).append(ext)

        counter = 1
        for base in sorted(grouped_files.keys()):
            if is_ascii(base):
                continue

            while True:
                new_base = f"{folder}_{counter:04d}"
                counter += 1
                if new_base not in grouped_files and new_base not in mapping_by_folder[folder].values():
                    break

            mapping_by_folder[folder][base] = new_base
            for ext in grouped_files[base]:
                old_path = os.path.join(folder_dir, base + ext)
                new_path = os.path.join(folder_dir, new_base + ext)
                os.rename(old_path, new_path)
            total_renamed += 1

    if total_renamed == 0:
        print("  [-] 未发现需要 ASCII 化的音频文件名。")
        return

    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(data_dir, filename)
            with open(file_path, "r", encoding="utf-8-sig") as file:
                data = json.load(file)
            replace_audio_refs(data, mapping_by_folder)
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, separators=(",", ":"))

    if os.path.exists(plugins_js_path):
        with open(plugins_js_path, "r", encoding="utf-8") as file:
            plugins_content = file.read()
        for folder_map in mapping_by_folder.values():
            for old_name, new_name in folder_map.items():
                plugins_content = plugins_content.replace(old_name, new_name)
        with open(plugins_js_path, "w", encoding="utf-8") as file:
            file.write(plugins_content)

    rename_map_path = os.path.join(www_dir, "audio_rename_map.json")
    with open(rename_map_path, "w", encoding="utf-8") as file:
        json.dump(mapping_by_folder, file, ensure_ascii=False, indent=2)

    print(f"  [+] 已 ASCII 化 {total_renamed} 个音频基名，并同步重写数据引用。")


def validate_audio_consistency(www_dir, system_json_path):
    """构建后校验音频状态，防止 System.json 与实际资源状态不一致。"""
    print("\n>>> 步骤 5.5: 校验构建后音频一致性...")
    if not os.path.exists(system_json_path):
        print("  [!] 找不到 System.json，无法执行音频一致性校验。")
        sys.exit(1)

    audio_dir = os.path.join(www_dir, "audio")
    if not os.path.exists(audio_dir):
        print("  [!] 找不到 audio 目录，无法执行音频一致性校验。")
        sys.exit(1)

    with open(system_json_path, "r", encoding="utf-8-sig") as file:
        system_data = json.load(file)

    has_encrypted_audio = bool(system_data.get("hasEncryptedAudio"))
    encrypted_files = []
    decrypted_ogg_files = []
    m4a_files = set()
    missing_m4a = []

    for root, _, files in os.walk(audio_dir):
        for filename in files:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, www_dir)
            lower_file = filename.lower()

            if lower_file.endswith(".ogg_") or lower_file.endswith(".m4a_") or lower_file.endswith(".rpgmvo"):
                encrypted_files.append(rel_path)
            elif lower_file.endswith(".ogg"):
                decrypted_ogg_files.append(full_path)
            elif lower_file.endswith(".m4a"):
                base_without_ext = os.path.splitext(os.path.relpath(full_path, audio_dir))[0]
                m4a_files.add(base_without_ext)

    if has_encrypted_audio:
        print("  [!] System.json 仍标记为 hasEncryptedAudio=true，构建产物状态非法。")
        sys.exit(1)

    if encrypted_files:
        print(f"  [!] 发现 {len(encrypted_files)} 个残留加密音频文件，构建产物状态非法。")
        for rel_path in encrypted_files[:20]:
            print(f"      - {rel_path}")
        if len(encrypted_files) > 20:
            print(f"      ... 其余 {len(encrypted_files) - 20} 个文件未展开")
        sys.exit(1)

    if not decrypted_ogg_files:
        print("  [!] 未发现任何解密后的 .ogg 文件，构建产物状态非法。")
        sys.exit(1)

    for ogg_path in decrypted_ogg_files:
        rel_base = os.path.splitext(os.path.relpath(ogg_path, audio_dir))[0]
        if rel_base not in m4a_files:
            missing_m4a.append(os.path.relpath(ogg_path, www_dir))

    if missing_m4a:
        print(f"  [!] 发现 {len(missing_m4a)} 个 .ogg 未生成对应 .m4a，构建产物状态非法。")
        for rel_path in missing_m4a[:20]:
            print(f"      - {rel_path}")
        if len(missing_m4a) > 20:
            print(f"      ... 其余 {len(missing_m4a) - 20} 个文件未展开")
        sys.exit(1)

    print(f"  [+] 音频一致性校验通过：{len(decrypted_ogg_files)} 个 .ogg，{len(m4a_files)} 个 .m4a，无残留加密音频。")
