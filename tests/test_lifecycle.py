from types import SimpleNamespace

from usr.plugins.openmontage import hooks


def test_repeated_install_checks_existing_runtime_without_installing_packages(tmp_path, monkeypatch):
    runtime = tmp_path / "plugin/_runtime"
    source = runtime / "OpenMontage"
    source.mkdir(parents=True)
    (source / ".a0-revision").write_text(hooks.REVISION)
    production = tmp_path / "productions/saved.mp4"
    production.parent.mkdir()
    production.write_bytes(b"preserve")
    monkeypatch.setattr(hooks, "RUNTIME", runtime)
    monkeypatch.setattr(hooks, "SOURCE_DIR", source)
    monkeypatch.setattr(hooks.shutil, "which", lambda executable: f"/usr/bin/{executable}")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(hooks.subprocess, "run", run)
    hooks.install()
    hooks.install()
    assert len(calls) == 4
    assert all(command[1] == "-c" for command in calls)
    hooks.uninstall()
    hooks.uninstall()
    assert not runtime.exists()
    assert production.read_bytes() == b"preserve"
