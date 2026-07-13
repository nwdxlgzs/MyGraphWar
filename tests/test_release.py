import json

from Release import export_project


def test_release_project_contains_source_but_not_local_artifacts(tmp_path):
    target=export_project(tmp_path)
    assert (target/"server"/"main.py").is_file()
    assert (target/"web"/"src"/"main.tsx").is_file()
    assert (target/"tests"/"test_simulation.py").is_file()
    assert not (target/".venv").exists()
    assert not (target/"web"/"node_modules").exists()
    assert not (target/"web"/"dist").exists()
    assert not list(target.rglob("*.db"))
    manifest=json.loads((target/"RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["kind"]=="source-project"
    assert manifest["file_count"]==len(manifest["files"])
