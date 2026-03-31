from __future__ import annotations

from pathlib import Path

from trampoline import cli


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_VIDEO = PROJECT_ROOT / "samples" / "tra_demo" / "sample01.mp4"


def test_cli_analyze_generates_phase1_artifacts(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "sample01"

    exit_code = cli.main(
        [
            "analyze",
            "--video",
            str(SAMPLE_VIDEO),
            "--out",
            str(output_dir),
            "--landmarks-only",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "trampoline analyze" in output
    assert (output_dir / "landmarks.jsonl").is_file()
    assert (output_dir / "frames_meta.json").is_file()
    assert (output_dir / "analysis.json").is_file()
