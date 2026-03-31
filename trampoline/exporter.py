"""Export helpers for the trampoline demo bundle."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from trampoline.pipeline import (
    ANALYSIS_FILENAME,
    FEATURES_FILENAME,
    LANDING_FILENAME,
    LABELS_FILENAME,
    SEGMENTATION_FILENAME,
    SUMMARY_FILENAME,
    load_analysis_output,
    read_json,
    sync_phase3_artifacts,
)


EXPORT_DIRNAME = "export"
BUNDLE_FILENAME = "analysis_bundle.zip"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.is_file():
        shutil.copy2(source, destination)


def export_analysis_bundle(analysis_dir: Path, output_dir: Path | None = None) -> dict[str, str]:
    """Create a deterministic export directory and bundle zip for one analysis."""

    if not (analysis_dir / SEGMENTATION_FILENAME).is_file():
        raise FileNotFoundError(f"Missing segmentation artifact: {analysis_dir / SEGMENTATION_FILENAME}")

    sync_phase3_artifacts(analysis_dir)
    result = load_analysis_output(analysis_dir)
    output_dir = output_dir or (analysis_dir / EXPORT_DIRNAME)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename in (
        ANALYSIS_FILENAME,
        SEGMENTATION_FILENAME,
        LABELS_FILENAME,
        LANDING_FILENAME,
        SUMMARY_FILENAME,
        "calibration.json",
        FEATURES_FILENAME,
        "frames_meta.json",
    ):
        _copy_if_exists(analysis_dir / filename, output_dir / filename)

    overlays_dir = output_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        overlays_dir / "preview_overlay.json",
        {
            "analysis_id": result["analysis_id"],
            "frame_size": {
                "width": result["frames_meta"]["width"],
                "height": result["frames_meta"]["height"],
            },
            "pose_connections": result["pose_connections"],
            "preview_frame": result["preview_frame"],
            "calibration": result["calibration"],
        },
    )
    _write_json(
        overlays_dir / "landing_heatmap.json",
        result["landing"]
        or {
            "analysis_id": result["analysis_id"],
            "jumps": [],
            "routine_summary": result.get("routine_summary"),
        },
    )
    _write_json(
        output_dir / "export_manifest.json",
        {
            "analysis_id": result["analysis_id"],
            "source_video": result["source_video"],
            "bundle_contents": sorted(
                str(path.relative_to(output_dir))
                for path in output_dir.rglob("*")
                if path.is_file()
            ),
        },
    )

    bundle_path = output_dir / BUNDLE_FILENAME
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file() or path == bundle_path:
                continue
            archive.write(path, arcname=str(path.relative_to(output_dir)))

    summary_path = output_dir / SUMMARY_FILENAME
    analysis_path = output_dir / ANALYSIS_FILENAME
    landing_path = output_dir / LANDING_FILENAME
    manifest = read_json(output_dir / "export_manifest.json")
    manifest["bundle_contents"] = sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
    )
    _write_json(output_dir / "export_manifest.json", manifest)

    return {
        "analysis_dir": str(analysis_dir),
        "export_dir": str(output_dir),
        "analysis_json": str(analysis_path),
        "summary_md": str(summary_path),
        "landing_json": str(landing_path),
        "bundle_zip": str(bundle_path),
    }
