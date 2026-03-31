from __future__ import annotations

from pathlib import Path

from trampoline import cli


def make_samples_dir(base_dir: Path) -> Path:
    samples_dir = base_dir / "samples" / "tra_demo"
    samples_dir.mkdir(parents=True)
    (samples_dir / "manifest.json").write_text('{"videos": []}\n', encoding="utf-8")
    return samples_dir


def test_doctor_success_path(tmp_path: Path, monkeypatch, capsys) -> None:
    samples_dir = make_samples_dir(tmp_path)
    artifacts_dir = tmp_path / "artifacts" / "trampoline"
    monkeypatch.setattr(cli, "dependency_available", lambda module_name: True)

    exit_code = cli.main(
        [
            "doctor",
            "--samples-dir",
            str(samples_dir),
            "--artifacts-dir",
            str(artifacts_dir),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "mediapipe" in output
    assert "samples" in output
    assert "artifacts" in output


def test_doctor_fails_when_samples_manifest_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    samples_dir = tmp_path / "samples" / "tra_demo"
    artifacts_dir = tmp_path / "artifacts" / "trampoline"
    monkeypatch.setattr(cli, "dependency_available", lambda module_name: True)

    exit_code = cli.main(
        [
            "doctor",
            "--samples-dir",
            str(samples_dir),
            "--artifacts-dir",
            str(artifacts_dir),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "samples: fail" in output
