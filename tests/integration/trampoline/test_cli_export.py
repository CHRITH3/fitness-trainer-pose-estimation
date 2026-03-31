from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from trampoline import cli


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_cli_export_generates_bundle_and_phase4_outputs(tmp_path: Path, capsys) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)

    exit_code = cli.main(["export", "--analysis-dir", str(analysis_dir)])

    output = capsys.readouterr().out
    export_dir = analysis_dir / "export"
    assert exit_code == 0
    assert "trampoline export" in output
    assert (analysis_dir / "landing.json").is_file()
    assert (analysis_dir / "summary.md").is_file()
    assert (export_dir / "analysis.json").is_file()
    assert (export_dir / "summary.md").is_file()
    assert (export_dir / "analysis_bundle.zip").is_file()

    landing_payload = json.loads((analysis_dir / "landing.json").read_text(encoding="utf-8"))
    assert landing_payload["jumps"][0]["landing_x_norm"] is not None
    assert "zone" in landing_payload["jumps"][0]
    assert "routine_flags" in landing_payload["routine_summary"]

    with zipfile.ZipFile(export_dir / "analysis_bundle.zip") as archive:
        names = set(archive.namelist())
    assert "analysis.json" in names
    assert "summary.md" in names
    assert "landing.json" in names
    assert "overlays/preview_overlay.json" in names
    assert "overlays/landing_heatmap.json" in names
