import json
import math
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import yaml

from helpers import files
from usr.plugins.openmontage.hooks import ROOT, SOURCE_DIR, PYTHON, REVISION

PROJECTS = Path(files.get_abs_path("usr/workdir/openmontage"))
MAX_METADATA = 2_000_000
STATES = {"completed": "Complete", "failed": "Failed", "awaiting_human": "Approval", "in_progress": "In progress"}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", value):
        raise ValueError("Invalid identifier.")
    return value


def inside(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("A relative file path is required.")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
        raise ValueError("File is outside the workspace.")
    return resolved


def read_json(path):
    if path.stat().st_size > MAX_METADATA:
        raise ValueError("Metadata exceeds 2 MB.")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        temporary = Path(target.name)
    temporary.replace(path)


def pipelines():
    root = SOURCE_DIR / "pipeline_defs"
    if not root.is_dir():
        raise RuntimeError("OpenMontage runtime is missing. Reinstall the plugin from Plugins.")
    result = []
    for path in sorted(root.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data.get("stability") == "internal" or path.stem == "framework-smoke":
            continue
        result.append({"id": path.stem, "name": path.stem.replace("-", " ").title(),
                       "description": str(data.get("description", "")).strip(),
                       "stages": [{"id": stage["name"], "name": stage["name"].replace("_", " ").title(),
                                   "approval": bool(stage.get("human_approval_default"))} for stage in data.get("stages", [])]})
    return result


def pipeline(pipeline_id):
    identifier(pipeline_id)
    for item in pipelines():
        if item["id"] == pipeline_id:
            return item
    raise ValueError("Unknown pipeline.")


def runtime():
    return {"ready": PYTHON.is_file() and (SOURCE_DIR / ".a0-revision").is_file(),
            "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
            "remotion": (SOURCE_DIR / "remotion-composer/node_modules/.bin/remotion").is_file(),
            "python": str(PYTHON), "cwd": str(SOURCE_DIR), "projects_dir": str(PROJECTS),
            "env": {"OPENMONTAGE_PROJECTS_DIR": str(PROJECTS)}, "revision": REVISION}


def upstream(operation, payload=None):
    if not runtime()["ready"]:
        raise RuntimeError("OpenMontage runtime is missing. Reinstall the plugin from Plugins.")
    programs = {
        "create": "from lib.checkpoint import init_project; result = str(init_project(**payload))",
        "preflight": "from tools.tool_registry import registry; registry.discover(); result = registry.provider_menu_summary()",
    }
    program = (
        "import json, sys, contextlib; payload=json.load(sys.stdin)\n"
        "with contextlib.redirect_stdout(sys.stderr):\n    " + programs[operation] + "\n"
        "print(json.dumps(result, default=str))"
    )
    completed = subprocess.run([str(PYTHON), "-c", program], input=json.dumps(payload or {}),
                               cwd=SOURCE_DIR, env={**os.environ, "OPENMONTAGE_PROJECTS_DIR": str(PROJECTS)},
                               text=True, capture_output=True, timeout=120)
    if completed.returncode:
        raise RuntimeError("OpenMontage could not complete the operation. Check its runtime installation and provider configuration.")
    return json.loads(completed.stdout)


def resource(path):
    allowed = ("skills/", "pipeline_defs/", "schemas/", "styles/", ".agents/skills/", "tools/", "docs/")
    if not isinstance(path, str) or (path not in {"AGENT_GUIDE.md", "PROJECT_CONTEXT.md"} and not path.startswith(allowed)):
        raise ValueError("Choose an OpenMontage guide, pipeline, skill, schema, style, tool, or documentation file.")
    target = inside(SOURCE_DIR, path)
    if target.is_dir():
        return {"files": [str(child.relative_to(SOURCE_DIR)) for child in sorted(target.iterdir()) if not child.is_symlink()]}
    if target.suffix.lower() not in {".md", ".yaml", ".json", ".py"} or not target.is_file() or target.stat().st_size > 300_000:
        raise ValueError("Resource is missing, unsupported, or exceeds 300 KB.")
    return {"path": str(target), "content": target.read_text(encoding="utf-8")}


def get_project(project_id):
    folder = inside(PROJECTS, identifier(project_id))
    marker = inside(folder, "project.json")
    if not marker.is_file():
        raise ValueError("Production not found.")
    project = read_json(marker)
    project["id"] = project_id
    project["path"] = str(folder)
    project["stages"] = pipeline(project["pipeline_type"])["stages"]
    project["status"] = "Draft"
    project["spent"] = None
    project["updated_at"] = project.get("created_at", "")
    for stage in project["stages"]:
        checkpoint = inside(folder, f"checkpoint_{identifier(stage['id'])}.json")
        stage.update(status="pending", label="Pending", timestamp="")
        if checkpoint.is_file():
            data = read_json(checkpoint)
            state = data.get("status", "pending")
            if data.get("human_approval_required") and not data.get("human_approved") and state == "completed":
                state = "awaiting_human"
            stage.update(status=state, label=STATES.get(state, "Unknown"), timestamp=data.get("timestamp", ""))
            if stage["timestamp"] >= project["updated_at"]:
                project["updated_at"] = stage["timestamp"]
                project["status"] = stage["label"]
                project["spent"] = (data.get("cost_snapshot") or {}).get("total_spent_usd")
    project["renders"] = []
    renders = inside(folder, "renders")
    if renders.is_dir():
        for target in sorted(renders.iterdir()):
            if not target.is_symlink() and target.is_file() and target.suffix.lower() in {".mp4", ".webm", ".mov"}:
                project["renders"].append({"name": target.name, "bytes": target.stat().st_size})
    brief_file = inside(folder, "a0-brief.json")
    if brief_file.is_file():
        project["brief"] = read_json(brief_file)
    return project


def list_projects():
    if not PROJECTS.is_dir():
        return []
    result = []
    for folder in PROJECTS.iterdir():
        if folder.is_dir() and not folder.is_symlink() and (folder / "project.json").is_file():
            try:
                result.append(get_project(folder.name))
            except (ValueError, OSError, KeyError):
                continue
    return sorted(result, key=lambda item: item.get("updated_at", ""), reverse=True)


def create_project(title, brief, pipeline_id="animated-explainer", budget=2):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
        raise ValueError("Title must contain 1–100 characters.")
    if not isinstance(brief, str) or not 1 <= len(brief.strip()) <= 12000:
        raise ValueError("Brief must contain 1–12,000 characters.")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or not 0 <= budget <= 1000:
        raise ValueError("Budget must be between 0 and 1,000 USD.")
    pipeline(pipeline_id)
    project_id = uuid.uuid4().hex[:16]
    upstream("create", {"project_id": project_id, "title": title.strip(), "pipeline_type": pipeline_id})
    write_json(inside(inside(PROJECTS, project_id), "a0-brief.json"), {"text": brief.strip(), "budget_usd": budget, "source_revision": REVISION})
    return get_project(project_id)


def handoff(project_id):
    project = get_project(project_id)
    brief = project.get("brief", {})
    return (
        f"Use OpenMontage for production {project_id}: {project['title']}.\n{brief.get('text', '')}\n"
        f"Requested media budget: ${brief.get('budget_usd', 0):.2f}. Use free/local tools when zero. "
        "This is a requested limit, not permission to spend; obtain explicit approval for paid generation.\n"
        "Call openmontage action=runtime and action=preflight. Read AGENT_GUIDE.md and "
        f"pipeline_defs/{project['pipeline_type']}.yaml with action=read, then each stage's director skill. "
        "Run upstream Python from the returned cwd with the returned absolute Python and OPENMONTAGE_PROJECTS_DIR. "
        f"Continue the existing project at {project['path']}; do not create a second project. "
        "Use upstream checkpoint writers, artifact validation, cost tracking and approval gates. "
        "Keep creative approvals in this chat; never invent approval or bypass checkpoint validation. "
        "Remotion and optional GPU/provider tools are available only if preflight confirms them; "
        "use an available renderer and agree it before producing assets. Do not install optional tools without approval. "
        "Write final videos to the project's renders directory. Inspect video frames and audio before delivery. "
        "The native OpenMontage panel reads actual checkpoints and renders on Refresh."
    )


def dispatch(action="status", **args):
    if action == "status":
        return {**runtime(), "projects": list_projects()}
    if action == "runtime":
        details = runtime()
        details["command_prefix"] = f"cd {shlex.quote(str(SOURCE_DIR))} && OPENMONTAGE_PROJECTS_DIR={shlex.quote(str(PROJECTS))} {shlex.quote(str(PYTHON))}"
        return details
    if action == "pipelines":
        return {"items": pipelines()}
    if action == "read":
        return resource(args.get("path", "AGENT_GUIDE.md"))
    if action == "preflight":
        return {"capabilities": upstream("preflight")}
    if action == "create":
        return {"project": create_project(args.get("title", ""), args.get("brief", ""), args.get("pipeline", "animated-explainer"), args.get("budget", 2))}
    if action == "project":
        return {"project": get_project(args.get("project_id", ""))}
    if action == "handoff":
        from agent import AgentContext
        project = get_project(args.get("project_id", ""))
        context_id = project.get("brief", {}).get("context_id", "")
        return {"message": handoff(project["id"]), "context_id": context_id if context_id and AgentContext.get(context_id) else ""}
    if action == "attach_chat":
        from agent import AgentContext
        context_id = args.get("context_id", "")
        if not isinstance(context_id, str) or not AgentContext.get(context_id):
            raise ValueError("Chat not found.")
        project = get_project(args.get("project_id", ""))
        brief = project.get("brief", {})
        brief["context_id"] = context_id
        write_json(inside(inside(PROJECTS, project["id"]), "a0-brief.json"), brief)
        return {"project": get_project(project["id"])}
    raise ValueError("Unknown OpenMontage action.")
