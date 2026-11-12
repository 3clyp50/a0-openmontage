import json
from pathlib import Path

import pytest
from flask import Flask

from usr.plugins.openmontage.helpers import production
from usr.plugins.openmontage.api.render import Render


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "pipeline_defs").mkdir(parents=True)
    (source / "pipeline_defs/animated-explainer.yaml").write_text(
        "name: animated-explainer\nstages:\n  - name: script\n    human_approval_default: true\n  - name: compose\n"
    )
    (source / "AGENT_GUIDE.md").write_text("# Production guide")
    monkeypatch.setattr(production, "SOURCE_DIR", source)
    monkeypatch.setattr(production, "PROJECTS", tmp_path / "projects")
    return tmp_path


def make_project():
    folder = production.PROJECTS / "sample"
    folder.mkdir(parents=True)
    production.write_json(folder / "project.json", {"project_id": "sample", "title": "Sample", "pipeline_type": "animated-explainer", "created_at": "2026-01-01T00:00:00Z"})
    production.write_json(folder / "a0-brief.json", {"text": "Create a video", "budget_usd": 0})
    return folder


def test_actual_checkpoint_states_and_cost(workspace):
    folder = make_project()
    assert production.get_project("sample")["status"] == "Draft"
    production.write_json(folder / "checkpoint_script.json", {"status": "awaiting_human", "timestamp": "2026-01-02T00:00:00Z", "cost_snapshot": {"total_spent_usd": 0.25}})
    project = production.get_project("sample")
    assert project["stages"][0]["status"] == "awaiting_human"
    assert project["stages"][1]["status"] == "pending"
    assert project["status"] == "Approval" and project["spent"] == 0.25
    assert "explicit approval" in production.handoff("sample")


def test_unapproved_checkpoint_never_shows_complete(workspace):
    folder = make_project()
    production.write_json(folder / "checkpoint_script.json", {"status": "completed", "human_approval_required": True, "human_approved": False, "timestamp": "2026-01-02T00:00:00Z"})
    assert production.get_project("sample")["stages"][0]["status"] == "awaiting_human"


@pytest.mark.parametrize("project_id", ["../outside", "/etc/passwd", "a/b", "", None])
def test_path_traversal_rejected(workspace, project_id):
    with pytest.raises(ValueError):
        production.get_project(project_id)


@pytest.mark.parametrize("budget", [-1, 1001, float("nan"), float("inf"), True, "20"])
def test_invalid_budget_never_initializes_project(workspace, monkeypatch, budget):
    monkeypatch.setattr(production, "upstream", lambda *args: pytest.fail("Must validate before invoking upstream"))
    with pytest.raises(ValueError):
        production.create_project("Title", "Brief", budget=budget)


def test_source_read_rejects_secrets_and_escape(workspace):
    assert "Production guide" in production.resource("AGENT_GUIDE.md")["content"]
    for path in (".env", "../secrets.md", "skills/../../../secrets.md"):
        with pytest.raises(ValueError):
            production.resource(path)


def test_create_uses_upstream_initializer(workspace, monkeypatch):
    calls = []
    def initialize(operation, payload):
        calls.append((operation, payload))
        production.write_json(production.PROJECTS / payload["project_id"] / "project.json", {**payload, "created_at": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(production, "upstream", initialize)
    project = production.create_project("Film", "Brief", budget=0)
    assert calls[0][0] == "create"
    assert project["brief"]["budget_usd"] == 0


@pytest.mark.asyncio
async def test_video_range_requests_and_symlink_rejection(workspace, monkeypatch):
    from usr.plugins.openmontage.api import render
    monkeypatch.setattr(render, "PROJECTS", production.PROJECTS)
    folder = make_project()
    (folder / "renders").mkdir()
    (folder / "renders/clip.mp4").write_bytes(b"0123456789")
    private = workspace / "secret.mp4"
    private.write_bytes(b"secret")
    (folder / "renders/leak.mp4").symlink_to(private)
    assert [item["name"] for item in production.get_project("sample")["renders"]] == ["clip.mp4"]
    app = Flask(__name__)
    handler = Render(app, None)
    assert handler.requires_auth()
    with app.test_request_context("/?id=sample&file=clip.mp4", headers={"Range": "bytes=0-3"}):
        from flask import request
        response = await handler.process({}, request)
        assert response.status_code == 206
        response.close()
    with app.test_request_context("/?id=sample&file=leak.mp4"):
        assert (await handler.process({}, request)).status_code == 404
