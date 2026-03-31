"""Command-line tools for the trampoline demo."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from trampoline.bounce_segmenter import segment_analysis_dir
from trampoline.exporter import export_analysis_bundle
from trampoline.pipeline import analyze_video, load_analysis_model, sync_phase3_artifacts


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLES_DIR = PROJECT_ROOT / "samples" / "tra_demo"
DEFAULT_ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "trampoline"
DEPENDENCIES = ("flask", "pydantic", "mediapipe")


@dataclass(frozen=True)
class DoctorResult:
    name: str
    ok: bool
    detail: str


def dependency_available(module_name: str) -> bool:
    """Return True when the named module can be imported."""

    return importlib.util.find_spec(module_name) is not None


def build_doctor_results(samples_dir: Path, artifacts_dir: Path) -> list[DoctorResult]:
    """Assemble doctor checks for runtime dependencies and local directories."""

    results = [
        DoctorResult("python", True, sys.version.split()[0]),
    ]

    for dependency in DEPENDENCIES:
        ok = dependency_available(dependency)
        detail = "available" if ok else "missing"
        results.append(DoctorResult(dependency, ok, detail))

    manifest_path = samples_dir / "manifest.json"
    samples_ok = samples_dir.is_dir() and manifest_path.is_file()
    results.append(
        DoctorResult(
            "samples",
            samples_ok,
            f"manifest={'present' if manifest_path.is_file() else 'missing'} path={samples_dir}",
        )
    )

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    writable = os.access(artifacts_dir, os.W_OK)
    results.append(
        DoctorResult(
            "artifacts",
            writable,
            f"path={artifacts_dir}",
        )
    )

    return results


def print_doctor_results(results: list[DoctorResult]) -> None:
    """Render doctor results in a stable plain-text format."""

    print("trampoline doctor")
    for result in results:
        state = "ok" if result.ok else "fail"
        print(f"- {result.name}: {state} ({result.detail})")


def run_doctor(samples_dir: Path, artifacts_dir: Path) -> int:
    """Execute doctor checks and print the report."""

    results = build_doctor_results(samples_dir=samples_dir, artifacts_dir=artifacts_dir)
    print_doctor_results(results)
    return 0 if all(result.ok for result in results) else 1


def run_analyze(video_path: Path, output_dir: Path, landmarks_only: bool, steps: str) -> int:
    """Execute the offline analysis entrypoint for Phase 1 through Phase 3."""

    try:
        resolved_steps = "landmarks" if landmarks_only else steps
        analysis = None

        if resolved_steps in {"landmarks", "all"} or not (output_dir / "analysis.json").is_file():
            analysis = analyze_video(
                video_path=video_path,
                output_dir=output_dir,
                landmarks_only=landmarks_only,
                analysis_id=output_dir.name,
            )
        else:
            analysis = load_analysis_model(output_dir)

        if resolved_steps in {"features", "all"}:
            if not (output_dir / "segmentation.json").is_file():
                segment_analysis_dir(output_dir)
            sync_phase3_artifacts(output_dir)
            analysis = load_analysis_model(output_dir)
    except Exception as exc:  # pragma: no cover - exercised via CLI tests
        print(f"trampoline analyze failed: {exc}", file=sys.stderr)
        return 1

    print("trampoline analyze")
    print(f"- analysis_id: {analysis.analysis_id}")
    print(f"- output_dir: {output_dir}")
    print(f"- steps: {resolved_steps}")
    print(f"- landmarks_only: {landmarks_only}")
    for artifact in analysis.artifacts:
        print(f"- artifact[{artifact.name}]: {artifact.path}")
    return 0


def run_segment(analysis_dir: Path) -> int:
    """Execute Phase 2 automatic jump segmentation for an existing analysis directory."""

    try:
        segmentation = segment_analysis_dir(analysis_dir)
    except Exception as exc:  # pragma: no cover - exercised via CLI tests
        print(f"trampoline segment failed: {exc}", file=sys.stderr)
        return 1

    print("trampoline segment")
    print(f"- analysis_dir: {analysis_dir}")
    print(f"- contact_candidates: {len(segmentation['contact_candidates'])}")
    print(f"- apex_candidates: {len(segmentation['apex_candidates'])}")
    print(f"- jump_segments: {len(segmentation['jump_segments'])}")
    print(f"- artifact[segmentation]: {analysis_dir / 'segmentation.json'}")
    return 0


def run_export(analysis_dir: Path, output_dir: Path | None) -> int:
    """Create the Phase 4 export bundle for an existing analysis directory."""

    try:
        exported = export_analysis_bundle(analysis_dir=analysis_dir, output_dir=output_dir)
    except Exception as exc:  # pragma: no cover - exercised via CLI tests
        print(f"trampoline export failed: {exc}", file=sys.stderr)
        return 1

    print("trampoline export")
    print(f"- analysis_dir: {analysis_dir}")
    print(f"- export_dir: {exported['export_dir']}")
    print(f"- artifact[analysis]: {exported['analysis_json']}")
    print(f"- artifact[summary]: {exported['summary_md']}")
    print(f"- artifact[landing]: {exported['landing_json']}")
    print(f"- artifact[bundle]: {exported['bundle_zip']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the trampoline CLI parser."""

    parser = argparse.ArgumentParser(prog="python -m trampoline.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check local demo prerequisites")
    doctor_parser.add_argument("--samples-dir", type=Path, default=DEFAULT_SAMPLES_DIR)
    doctor_parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)

    analyze_parser = subparsers.add_parser("analyze", help="run offline landmark extraction")
    analyze_parser.add_argument("--video", type=Path, required=True)
    analyze_parser.add_argument("--out", type=Path)
    analyze_parser.add_argument("--landmarks-only", action="store_true")
    analyze_parser.add_argument("--steps", choices=("landmarks", "features", "all"), default="landmarks")

    segment_parser = subparsers.add_parser("segment", help="generate jump segmentation from existing artifacts")
    segment_parser.add_argument("--analysis-dir", type=Path, required=True)

    export_parser = subparsers.add_parser("export", help="bundle Phase 4 summary and overlays for one analysis")
    export_parser.add_argument("--analysis-dir", type=Path, required=True)
    export_parser.add_argument("--out", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint used by both tests and module execution."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor(samples_dir=args.samples_dir, artifacts_dir=args.artifacts_dir)

    if args.command == "analyze":
        output_dir = args.out or (DEFAULT_ARTIFACTS_DIR / args.video.stem)
        return run_analyze(
            video_path=args.video,
            output_dir=output_dir,
            landmarks_only=args.landmarks_only,
            steps=args.steps,
        )

    if args.command == "segment":
        return run_segment(analysis_dir=args.analysis_dir)

    if args.command == "export":
        return run_export(analysis_dir=args.analysis_dir, output_dir=args.out)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
