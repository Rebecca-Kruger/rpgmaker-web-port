import json
import os
import re
import shutil
import subprocess
import sys


def convert_audio_to_m4a(www_dir):
    """Convert ogg/wav audio files to m4a."""
    print("\n>>> Step 5: Converting audio to iOS-compatible m4a...")
    audio_dir = os.path.join(www_dir, "audio")
    if not os.path.exists(audio_dir):
        return

    converted_count = 0
    synthesized_silence_count = 0

    def synthesize_silence_audio(target_path, lower_file):
        """Generate short silence for 0-byte audio files so ffmpeg can continue."""
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
                    print(f"  [!] Detected 0-byte audio. Generating silence for: {filename}")
                    synthesize_silence_audio(orig_path, lower_file)
                    synthesized_silence_count += 1
            except subprocess.CalledProcessError:
                print(f"  [!] Failed to synthesize silence for 0-byte audio. Stopping pipeline: {filename}")
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
                    print(f"  [!] Audio conversion failed, skipping: {filename}")
                    continue

            if lower_file.endswith(".wav"):
                os.remove(orig_path)
                shutil.copy2(m4a_path, orig_path)
                print(f"  [WAV shim applied] Replaced large {filename} with a 128k AAC-backed file to avoid size limits.")

    print(f"  [+] Audio conversion complete. Converted {converted_count} files and synthesized {synthesized_silence_count} silent audio files.")


def sanitize_audio_filenames(www_dir):
    """Normalize unsafe audio filenames to safe ASCII names and rewrite references."""
    print("\n>>> Step 5.3: Normalizing unsafe audio filenames and rewriting references...")
    audio_dir = os.path.join(www_dir, "audio")
    data_dir = os.path.join(www_dir, "data")
    plugins_js_path = os.path.join(www_dir, "js", "plugins.js")
    if not os.path.exists(audio_dir):
        print("  [-] audio directory not found. Skipping audio filename normalization.")
        return

    safe_basename_pattern = re.compile(r"^[A-Za-z0-9_-]+$")

    def is_safe_audio_basename(text):
        return bool(safe_basename_pattern.fullmatch(text))

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
            if is_safe_audio_basename(base):
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
        print("  [-] No unsafe audio filenames found.")
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

    print(f"  [+] Normalized {total_renamed} unsafe audio basenames and rewrote data references.")


def validate_audio_consistency(www_dir, system_json_path):
    """Validate audio build consistency after processing."""
    print("\n>>> Step 5.5: Validating audio build consistency...")
    if not os.path.exists(system_json_path):
        print("  [!] System.json not found. Cannot validate audio consistency.")
        sys.exit(1)

    audio_dir = os.path.join(www_dir, "audio")
    if not os.path.exists(audio_dir):
        print("  [!] audio directory not found. Cannot validate audio consistency.")
        sys.exit(1)

    with open(system_json_path, "r", encoding="utf-8-sig") as file:
        system_data = json.load(file)

    has_encrypted_audio = bool(system_data.get("hasEncryptedAudio"))
    encrypted_files = []
    decrypted_ogg_files = []
    m4a_files = set()
    missing_m4a = []
    missing_referenced_audio = []

    def collect_audio_refs(node, refs, source_name):
        if isinstance(node, list):
            for item in node:
                collect_audio_refs(item, refs, source_name)
            return
        if not isinstance(node, dict):
            return

        def add_ref(folder, name):
            if isinstance(name, str) and name:
                refs.add((folder, name, source_name))

        if isinstance(node.get("bgm"), dict):
            add_ref("bgm", node["bgm"].get("name"))

        if isinstance(node.get("bgs"), dict):
            add_ref("bgs", node["bgs"].get("name"))

        if "sounds" in node and isinstance(node["sounds"], list):
            for sound in node["sounds"]:
                if isinstance(sound, dict):
                    add_ref("se", sound.get("name"))

        if isinstance(node.get("battleBgm"), dict):
            add_ref("bgm", node["battleBgm"].get("name"))

        if isinstance(node.get("titleBgm"), dict):
            add_ref("bgm", node["titleBgm"].get("name"))

        for key in ("boat", "ship", "airship"):
            if isinstance(node.get(key), dict) and isinstance(node[key].get("bgm"), dict):
                add_ref("bgm", node[key]["bgm"].get("name"))

        for key in ("victoryMe", "defeatMe", "gameoverMe"):
            if isinstance(node.get(key), dict):
                add_ref("me", node[key].get("name"))

        code = node.get("code")
        params = node.get("parameters")
        if isinstance(code, int) and isinstance(params, list) and params and isinstance(params[0], dict):
            audio = params[0]
            if code in (241, 132):
                add_ref("bgm", audio.get("name"))
            elif code == 245:
                add_ref("bgs", audio.get("name"))
            elif code == 249:
                add_ref("me", audio.get("name"))
            elif code == 250:
                add_ref("se", audio.get("name"))

        for value in node.values():
            collect_audio_refs(value, refs, source_name)

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
        print("  [!] System.json still has hasEncryptedAudio=true. Build output is invalid.")
        sys.exit(1)

    if encrypted_files:
        print(f"  [!] Found {len(encrypted_files)} encrypted audio files remaining. Build output is invalid.")
        for rel_path in encrypted_files[:20]:
            print(f"      - {rel_path}")
        if len(encrypted_files) > 20:
            print(f"      ... plus {len(encrypted_files) - 20} more files not shown")
        sys.exit(1)

    if not decrypted_ogg_files:
        print("  [!] No decrypted .ogg files found. Build output is invalid.")
        sys.exit(1)

    for ogg_path in decrypted_ogg_files:
        rel_base = os.path.splitext(os.path.relpath(ogg_path, audio_dir))[0]
        if rel_base not in m4a_files:
            missing_m4a.append(os.path.relpath(ogg_path, www_dir))

    if missing_m4a:
        print(f"  [!] Found {len(missing_m4a)} .ogg files without matching .m4a files. Build output is invalid.")
        for rel_path in missing_m4a[:20]:
            print(f"      - {rel_path}")
        if len(missing_m4a) > 20:
            print(f"      ... plus {len(missing_m4a) - 20} more files not shown")
        sys.exit(1)

    data_dir = os.path.join(www_dir, "data")
    if os.path.exists(data_dir):
        referenced_audio = set()
        for filename in os.listdir(data_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(data_dir, filename)
            with open(file_path, "r", encoding="utf-8-sig") as file:
                data = json.load(file)
            collect_audio_refs(data, referenced_audio, filename)

        for folder, name, source_name in sorted(referenced_audio):
            ogg_path = os.path.join(audio_dir, folder, name + ".ogg")
            m4a_path = os.path.join(audio_dir, folder, name + ".m4a")
            if not os.path.exists(ogg_path) or not os.path.exists(m4a_path):
                missing_parts = []
                if not os.path.exists(ogg_path):
                    missing_parts.append(os.path.relpath(ogg_path, www_dir))
                if not os.path.exists(m4a_path):
                    missing_parts.append(os.path.relpath(m4a_path, www_dir))
                missing_referenced_audio.append((source_name, folder, name, missing_parts))

    if missing_referenced_audio:
        print(f"  [!] Found {len(missing_referenced_audio)} audio references without matching files. Build output is invalid.")
        for source_name, folder, name, missing_parts in missing_referenced_audio[:20]:
            print(f"      - {source_name}: {folder}/{name} missing {', '.join(missing_parts)}")
        if len(missing_referenced_audio) > 20:
            print(f"      ... plus {len(missing_referenced_audio) - 20} more references not shown")
        sys.exit(1)

    print(f"  [+] Audio consistency validation passed: {len(decrypted_ogg_files)} .ogg files, {len(m4a_files)} .m4a files, no encrypted audio remains.")
