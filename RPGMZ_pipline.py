from pipeline.audio import convert_audio_to_m4a, sanitize_audio_filenames, validate_audio_consistency
from pipeline.config import load_cloudflare_credentials, load_runtime_config
from pipeline.deploy import deploy_to_cloudflare
from pipeline.injections import patch_problematic_plugin_params, patch_runtime_injections
from pipeline.resources import (
    apply_mtools_translation,
    apply_patch,
    clean_pc_build,
    convert_video_to_mp4,
    decrypt_assets,
    fix_resource_percent_symbols,
    patch_system_json,
)
from pipeline.workspace import get_valid_project_name, prepare_www_workspace


def main():
    runtime = load_runtime_config()

    print("=" * 50)
    print(" RPG Maker Web 全自动部署处理流 (MV/MZ 兼容版)")
    print("=" * 50)

    prepare_www_workspace(runtime.base_dir, runtime.www_dir)
    clean_pc_build(runtime.www_dir)
    apply_mtools_translation(runtime.base_dir, runtime.www_dir)
    apply_patch(runtime.patch_zip, runtime.www_dir)
    patch_runtime_injections(runtime.www_dir, runtime.vpad_html_path)
    key = patch_system_json(runtime.system_json_path)
    decrypt_assets(runtime.www_dir, key)
    convert_audio_to_m4a(runtime.www_dir)
    sanitize_audio_filenames(runtime.www_dir)
    validate_audio_consistency(runtime.www_dir, runtime.system_json_path)
    convert_video_to_mp4(runtime.www_dir)
    patch_problematic_plugin_params(runtime.www_dir)
    fix_resource_percent_symbols(runtime.www_dir)

    final_project_name = get_valid_project_name(runtime.game_name)
    credentials = load_cloudflare_credentials(runtime.cloudflare_credentials_path)
    deploy_to_cloudflare(final_project_name, runtime, credentials)

    print("\n" + "=" * 50)
    print(f"\n 部署大功告成！游戏 [{runtime.game_name}] 已经在线上就绪！")
    print("=" * 50)


if __name__ == "__main__":
    main()
