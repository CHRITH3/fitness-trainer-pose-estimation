from __future__ import annotations

import shutil
from pathlib import Path

from trampoline import cli


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_ANALYSIS_DIR = PROJECT_ROOT / "artifacts" / "trampoline" / "sample01"


def test_cli_segment_generates_segmentation(tmp_path: Path, capsys) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)
    (analysis_dir / "segmentation.json").unlink(missing_ok=True)

    exit_code = cli.main(["segment", "--analysis-dir", str(analysis_dir)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "trampoline segment" in output
    assert "contact_candidates:" in output
    assert "apex_candidates:" in output
    assert (analysis_dir / "segmentation.json").is_file()


def test_cli_segment_fails_without_calibration(tmp_path: Path, capsys) -> None:
    analysis_dir = tmp_path / "sample01"
    shutil.copytree(SAMPLE_ANALYSIS_DIR, analysis_dir)
    (analysis_dir / "calibration.json").unlink()

    exit_code = cli.main(["segment", "--analysis-dir", str(analysis_dir)])

    error = capsys.readouterr().err
    assert exit_code == 1
    assert "Missing calibration artifact" in error

