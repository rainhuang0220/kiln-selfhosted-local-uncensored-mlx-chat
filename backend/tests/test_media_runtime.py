from pathlib import Path

from app.services.media_runtime import _run_image, _run_video


class _Ok:
    returncode = 0


def test_zimage_prompt_is_a_single_argv_element(tmp_settings, tmp_path, monkeypatch):
    model = tmp_path / "zimg"
    model.mkdir()
    tmp_settings.image_zimage_dir = str(model)
    tmp_settings.generations_dir = str(tmp_path / "g")
    captured: dict = {}

    def fake_which(name, path=None):
        return "/fake/mflux-generate-z-image-turbo"

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("--output") + 1]).write_bytes(b"x")
        return _Ok()

    monkeypatch.setattr("app.services.media_runtime.shutil.which", fake_which)
    monkeypatch.setattr("app.services.media_runtime._run_cancellable", fake_run)
    _run_image(
        tmp_settings,
        {
            "id": "j1",
            "kind": "image",
            "backend": "z-image-turbo",
            "prompt": "exactly three red cubes",
            "params": {"width": 512, "height": 512, "steps": 9, "seed": 42},
        },
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--prompt") + 1] == "exactly three red cubes"
    assert all(isinstance(x, str) for x in cmd)


def test_video_argv_includes_shift_and_verbatim_prompt(tmp_settings, tmp_path, monkeypatch):
    mlx_dir = tmp_path / "wan-mlx"
    mlx_dir.mkdir()
    (mlx_dir / "config.json").write_text("{}", encoding="utf-8")
    dit = tmp_path / "wan_1.3B_exp_e14.safetensors"
    dit.write_bytes(b"dit")
    tmp_settings.video_wan_mlx_dir = str(mlx_dir)
    tmp_settings.video_wan_dit = str(dit)
    tmp_settings.video_wan_aux_dir = str(tmp_path / "aux")
    tmp_settings.generations_dir = str(tmp_path / "g")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("--output-path") + 1]).write_bytes(b"mp4")
        return _Ok()

    monkeypatch.setattr("app.services.media_runtime._run_cancellable", fake_run)
    result = _run_video(
        tmp_settings,
        {
            "id": "v1",
            "kind": "video",
            "backend": "nsfw-wan-1.3b",
            "prompt": "铜窑在工坊里缓慢推进镜头",
            "params": {"preset": "standard", "seed": 3},
        },
    )
    cmd = captured["cmd"]
    assert cmd[cmd.index("--prompt") + 1] == "铜窑在工坊里缓慢推进镜头"
    assert cmd[cmd.index("--shift") + 1] == "8.0"
    assert cmd[cmd.index("--guide-scale") + 1] == "6.0"
    assert cmd[cmd.index("--steps") + 1] == "20"
    assert cmd[cmd.index("--teacache") + 1] == "0.0"
    assert result.metrics["shift"] == 8.0
