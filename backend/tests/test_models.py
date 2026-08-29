import pytest


def test_local_models_expose_the_active_profile_without_leaking_paths(client):
    response = client.get("/models/local")

    assert response.status_code == 200
    body = response.json()
    assert body["active_id"] == "qwen3.5-9b-hauhau-aggressive-mxfp4"
    assert body["data"] == [
        {
            "id": "qwen3.5-9b-hauhau-aggressive-mxfp4",
            "name": "qwen3.5-9b-hauhau-aggressive-mxfp4",
            "source": "configured",
            "status": "active",
        }
    ]
    assert "path" not in body["data"][0]


def test_catalog_uses_the_hub_search_workflow(client):
    seen: dict[str, object] = {}

    def search_catalog(query: str, limit: int, mlx_only: bool):
        seen.update(query=query, limit=limit, mlx_only=mlx_only)
        return {
            "query": query,
            "source": "huggingface",
            "data": [
                {
                    "id": "mlx-community/Qwen3.5-9B-4bit",
                    "name": "Qwen3.5 9B 4-bit",
                    "downloads": 42,
                    "likes": 9,
                    "updated_at": "2026-08-20T00:00:00Z",
                    "pipeline_tag": "text-generation",
                    "tags": ["mlx", "text-generation"],
                }
            ],
        }

    client.app.state.models.search_catalog = search_catalog
    response = client.get("/models/catalog?q=qwen&limit=12&mlx_only=true")

    assert response.status_code == 200
    assert seen == {"query": "qwen", "limit": 12, "mlx_only": True}
    assert response.json()["data"][0]["id"] == "mlx-community/Qwen3.5-9B-4bit"


def test_local_models_include_downloaded_model_metadata(client, tmp_path):
    library = tmp_path / "models"
    model = library / "mlx-community--Qwen3.5-4B-4bit"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    (model / "kiln-model.json").write_text(
        '{"repo_id":"mlx-community/Qwen3.5-4B-4bit","revision":"abc123"}',
        encoding="utf-8",
    )
    object.__setattr__(client.app.state.models.settings, "model_library_path", str(library))

    response = client.get("/models/local")

    assert response.status_code == 200
    assert response.json()["data"][-1] == {
        "id": "mlx-community--Qwen3.5-4B-4bit",
        "name": "Qwen3.5-4B-4bit",
        "source": "huggingface",
        "status": "ready",
        "repo_id": "mlx-community/Qwen3.5-4B-4bit",
        "revision": "abc123",
    }


def test_download_workflow_queues_a_public_hub_model(client):
    seen: dict[str, object] = {}

    def queue_download(repo_id: str, revision: str | None, activate: bool):
        seen.update(repo_id=repo_id, revision=revision, activate=activate)
        return {"id": "job-123", "repo_id": repo_id, "status": "queued", "activate": activate}

    client.app.state.models.queue_download = queue_download
    response = client.post(
        "/models/download",
        json={
            "repo_id": "mlx-community/Qwen3.5-4B-4bit",
            "revision": "main",
            "activate": True,
        },
    )

    assert response.status_code == 202
    assert seen == {
        "repo_id": "mlx-community/Qwen3.5-4B-4bit",
        "revision": "main",
        "activate": True,
    }
    assert response.json()["status"] == "queued"


def test_download_workflow_rejects_a_non_repository_identifier(client):
    response = client.post("/models/download", json={"repo_id": "../private-model"})

    assert response.status_code == 400


def test_activate_switches_only_an_installed_model(client):
    seen: list[str] = []

    def activate(model_id: str):
        seen.append(model_id)
        return {"id": model_id, "status": "restarting"}

    client.app.state.models.activate = activate
    response = client.post("/models/mlx-community--Qwen3.5-4B-4bit/activate")

    assert response.status_code == 202
    assert seen == ["mlx-community--Qwen3.5-4B-4bit"]
    assert response.json() == {"id": "mlx-community--Qwen3.5-4B-4bit", "status": "restarting"}


def test_activation_refuses_unknown_or_unmanaged_models(client, tmp_path):
    manager = client.app.state.models
    object.__setattr__(manager.settings, "model_library_path", str(tmp_path / "models"))
    activation = getattr(manager, "activate", None)

    assert callable(activation)
    try:
        activation("not-installed")
    except ValueError as exc:
        assert str(exc) == "model not installed"
    else:
        raise AssertionError("unknown models must not be activated")


def test_catalog_supports_the_current_huggingface_hub_signature(client):
    from types import SimpleNamespace

    from app.services.models import ModelManager

    class HubWithoutDirection:
        def list_models(self, *, search, sort, limit, full):
            assert search == "qwen"
            assert sort == "downloads"
            assert limit == 9
            assert full is True
            return [
                SimpleNamespace(
                    id="mlx-community/Qwen3.5-4B-4bit",
                    tags=["mlx", "text-generation"],
                    downloads=42,
                    likes=2,
                    last_modified=None,
                    pipeline_tag="text-generation",
                )
            ]

    result = ModelManager(client.app.state.models.settings, hub=HubWithoutDirection()).search_catalog(
        "qwen", 3, True
    )

    assert result["data"][0]["id"] == "mlx-community/Qwen3.5-4B-4bit"


def test_catalog_marks_models_that_are_not_directly_mlx_compatible(client):
    from types import SimpleNamespace

    from app.services.models import ModelManager

    class Hub:
        def list_models(self, **_kwargs):
            return [
                SimpleNamespace(
                    id="Qwen/Qwen3.5-4B",
                    tags=["transformers", "text-generation"],
                    downloads=1,
                    likes=1,
                    last_modified=None,
                    pipeline_tag="text-generation",
                )
            ]

    result = ModelManager(client.app.state.models.settings, hub=Hub()).search_catalog("qwen", 3, False)

    assert result["data"][0]["mlx_compatible"] is False


def test_download_refuses_a_hub_model_that_is_not_mlx_ready(client):
    from types import SimpleNamespace

    from app.services.models import ModelManager

    class Hub:
        def model_info(self, repo_id: str, revision: str | None = None):
            assert repo_id == "Qwen/Qwen3.5-4B"
            assert revision is None
            return SimpleNamespace(tags=["transformers", "text-generation"])

    manager = ModelManager(client.app.state.models.settings, hub=Hub())

    with pytest.raises(ValueError, match="not MLX-ready"):
        manager.validate_hub_model("Qwen/Qwen3.5-4B")


def test_download_preflight_checks_the_requested_hub_revision(client):
    from types import SimpleNamespace

    from app.services.models import ModelManager

    seen: dict[str, object] = {}

    class Hub:
        def model_info(self, repo_id: str, revision: str | None = None):
            seen.update(repo_id=repo_id, revision=revision)
            return SimpleNamespace(
                tags=["mlx", "text-generation"],
                siblings=[
                    SimpleNamespace(rfilename="config.json"),
                    SimpleNamespace(rfilename="model.safetensors"),
                ],
            )

    manager = ModelManager(client.app.state.models.settings, hub=Hub())

    manager.validate_hub_model("mlx-community/Qwen3.5-4B-4bit", "safe-commit")

    assert seen == {
        "repo_id": "mlx-community/Qwen3.5-4B-4bit",
        "revision": "safe-commit",
    }


def test_download_preflight_rejects_an_mlx_tag_without_model_files(client):
    from types import SimpleNamespace

    from app.services.models import ModelManager

    class Hub:
        def model_info(self, _repo_id: str, revision: str | None = None):
            assert revision == "unsafe-branch"
            return SimpleNamespace(
                tags=["mlx"],
                siblings=[
                    SimpleNamespace(rfilename="config.json"),
                    SimpleNamespace(rfilename="README.md"),
                ],
            )

    manager = ModelManager(client.app.state.models.settings, hub=Hub())

    with pytest.raises(ValueError, match="MLX weight files"):
        manager.validate_hub_model("mlx-community/Qwen3.5-4B-4bit", "unsafe-branch")


def test_catalog_hub_outage_returns_a_safe_service_error(client):
    def unavailable(*_args, **_kwargs):
        raise OSError("upstream token or connection detail")

    client.app.state.models.search_catalog = unavailable

    response = client.get("/models/catalog?q=qwen")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_catalog_unavailable"
    assert "connection detail" not in response.text


def test_download_hub_outage_returns_a_safe_service_error(client):
    def unavailable(*_args, **_kwargs):
        raise OSError("upstream token or connection detail")

    client.app.state.models.queue_download = unavailable

    response = client.post(
        "/models/download", json={"repo_id": "mlx-community/Qwen3.5-4B-4bit"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_download_unavailable"
    assert "connection detail" not in response.text


def test_model_download_job_redacts_private_failure_details(client, tmp_path, monkeypatch):
    import asyncio

    from app.services import models
    from app.services.models import ModelManager

    settings = client.app.state.models.settings
    object.__setattr__(settings, "model_library_path", str(tmp_path / "models"))
    manager = ModelManager(settings)
    manager.jobs["job-private"] = {
        "id": "job-private",
        "repo_id": "mlx-community/Qwen3.5-4B-4bit",
        "revision": None,
        "status": "queued",
        "activate": False,
    }

    def broken_download(**_kwargs):
        raise OSError("/Users/example/private-models/secret is missing")

    monkeypatch.setattr(models, "snapshot_download", broken_download)
    asyncio.run(manager._download("job-private"))

    job = manager.list_jobs()["data"][0]
    assert job["status"] == "error"
    assert job["error"] == "Download failed. Check server logs and available disk space."
    assert "private-models" not in str(job)


def test_activation_error_does_not_return_a_private_model_path(client):
    def broken_activate(_model_id: str):
        raise RuntimeError("/Users/example/private-models/secret")

    client.app.state.models.activate = broken_activate

    response = client.post("/models/mlx-community--Qwen3.5-4B-4bit/activate")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "model_switch_failed"
    assert "private-models" not in response.text


def test_active_selection_is_restored_from_private_local_state(client, tmp_path):
    from app.config import Settings
    from app.services.models import ModelManager

    library = tmp_path / "models"
    model = library / "mlx-community--Qwen3.5-4B-4bit"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    selection = tmp_path / "data" / "active-model.json"
    selection.parent.mkdir()
    selection.write_text(
        '{"id":"mlx-community--Qwen3.5-4B-4bit","path":"' + str(model) + '"}',
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "chat.db"),
        model_library_path=str(library),
        model_selection_state_path=str(selection),
    )

    ModelManager.restore_active_selection(settings)

    assert settings.model_name == "mlx-community--Qwen3.5-4B-4bit"
    assert settings.model_path == str(model.resolve())


def test_download_and_use_activates_only_after_the_model_is_present(client, tmp_path, monkeypatch):
    import asyncio

    from app.services import models
    from app.services.models import ModelManager

    settings = client.app.state.models.settings
    object.__setattr__(settings, "model_library_path", str(tmp_path / "models"))
    manager = ModelManager(settings)
    manager.jobs["job-1"] = {
        "id": "job-1",
        "repo_id": "mlx-community/Qwen3.5-4B-4bit",
        "revision": None,
        "status": "queued",
        "activate": True,
    }

    def fake_download(*, local_dir, **_kwargs):
        local_dir.mkdir(parents=True)
        (local_dir / "config.json").write_text("{}", encoding="utf-8")

    activated: list[str] = []
    monkeypatch.setattr(models, "snapshot_download", fake_download)
    manager.activate = lambda model_id: activated.append(model_id) or {"status": "restarting"}

    asyncio.run(manager._download("job-1"))

    assert activated == ["mlx-community--Qwen3.5-4B-4bit"]
    assert manager.jobs["job-1"]["status"] == "restarting"
