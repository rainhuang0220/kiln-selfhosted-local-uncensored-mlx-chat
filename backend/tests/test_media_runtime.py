from pathlib import Path

from app.services.media_runtime import _port_open, _run_image, _run_video


class _Ok:
    returncode = 0


def test_wan_teacache_module_imports():
    from app.services import wan_teacache

    assert wan_teacache.COEFFS_1_3B


def test_port_open_does_not_require_lsof(monkeypatch):
    import socket

    class FakeSock:
        def settimeout(self, _t):
            return None

        def connect_ex(self, addr):
            assert addr[1] == 8081
            return 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(socket, "socket", lambda *a, **k: FakeSock())
    assert _port_open(8081) is True


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


def test_flux1_dev_uses_mflux_generate_low_ram(tmp_settings, tmp_path, monkeypatch):
    model = tmp_path / "flux1"
    (model / "transformer").mkdir(parents=True)
    (model / "transformer" / "0.safetensors").write_bytes(b"x" * 200)
    tmp_settings.image_flux1_dev_dir = str(model)
    tmp_settings.generations_dir = str(tmp_path / "g")
    captured: dict = {}

    def fake_which(name, path=None):
        if name == "mflux-generate":
            return "/fake/mflux-generate"
        return None

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("--output") + 1]).write_bytes(b"x")
        return _Ok()

    monkeypatch.setattr("app.services.media_runtime.shutil.which", fake_which)
    monkeypatch.setattr("app.services.media_runtime._run_cancellable", fake_run)
    result = _run_image(
        tmp_settings,
        {
            "id": "j2",
            "kind": "image",
            "backend": "flux1-dev",
            "prompt": "exactly four yellow lemons on a plate",
            "params": {"width": 1024, "height": 1024, "steps": 20, "seed": 42, "guidance": 3.5},
        },
    )
    cmd = captured["cmd"]
    assert cmd[0] == "/fake/mflux-generate"
    assert cmd[cmd.index("--prompt") + 1] == "exactly four yellow lemons on a plate"
    assert cmd[cmd.index("--steps") + 1] == "20"
    assert cmd[cmd.index("--guidance") + 1] == "3.5"
    assert "--low-ram" in cmd
    assert result.metrics["backend"] == "flux1-dev"


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
