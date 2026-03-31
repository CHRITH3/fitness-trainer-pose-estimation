#!/usr/bin/env bash
set -euo pipefail

VIDEO_PATH="${1:-samples/tra_demo/sample01.mp4}"
ANALYSIS_ID="${2:-$(basename "${VIDEO_PATH%.*}")}"
ANALYSIS_DIR="artifacts/trampoline/${ANALYSIS_ID}"

if [[ ! -f "${VIDEO_PATH}" ]]; then
    echo "Missing video: ${VIDEO_PATH}" >&2
    exit 1
fi

mkdir -p "${ANALYSIS_DIR}"

echo "[1/5] Analyze landmarks"
python -m trampoline.cli analyze --video "${VIDEO_PATH}" --out "${ANALYSIS_DIR}" --landmarks-only

echo "[2/5] Save calibration"
python - <<'PY' "${ANALYSIS_DIR}"
from pathlib import Path
import sys

from trampoline.bed_calibration import create_bed_calibration, save_calibration
from trampoline.pipeline import read_json

analysis_dir = Path(sys.argv[1])
frames_meta = read_json(analysis_dir / "frames_meta.json")
width = int(frames_meta["width"])
height = int(frames_meta["height"])
inset_x = round(width * 0.18, 1)
inset_y = round(height * 0.15, 1)
calibration = create_bed_calibration(
    corners={
        "top_left": {"x": inset_x, "y": inset_y},
        "top_right": {"x": width - inset_x, "y": inset_y},
        "bottom_right": {"x": width - inset_x, "y": height - inset_y},
        "bottom_left": {"x": inset_x, "y": height - inset_y},
    },
    frame_width=width,
    frame_height=height,
)
save_calibration(calibration, analysis_dir)
print(f"saved calibration: {analysis_dir / 'calibration.json'}")
PY

echo "[3/5] Segment and label"
python -m trampoline.cli segment --analysis-dir "${ANALYSIS_DIR}"

echo "[4/5] Export bundle"
python -m trampoline.cli export --analysis-dir "${ANALYSIS_DIR}"

echo "[5/5] Verify artifacts"
python - <<'PY' "${ANALYSIS_DIR}"
from pathlib import Path
import json
import sys
import zipfile

analysis_dir = Path(sys.argv[1])
required_paths = [
    analysis_dir / "analysis.json",
    analysis_dir / "segmentation.json",
    analysis_dir / "labels.json",
    analysis_dir / "landing.json",
    analysis_dir / "summary.md",
    analysis_dir / "export" / "analysis_bundle.zip",
]
missing = [str(path) for path in required_paths if not path.exists()]
if missing:
    raise SystemExit(f"Missing required artifacts: {missing}")

landing = json.loads((analysis_dir / "landing.json").read_text(encoding="utf-8"))
if not landing["jumps"]:
    raise SystemExit("landing.json has no jump records")
required_keys = {"landing_x_norm", "landing_y_norm", "landing_source", "zone"}
for row in landing["jumps"]:
    if not required_keys.issubset(row):
        raise SystemExit(f"Landing row missing keys: {row}")

bundle_path = analysis_dir / "export" / "analysis_bundle.zip"
with zipfile.ZipFile(bundle_path) as archive:
    names = set(archive.namelist())
for expected in {"analysis.json", "summary.md", "landing.json", "overlays/landing_heatmap.json"}:
    if expected not in names:
        raise SystemExit(f"Bundle missing {expected}")

print("PASS")
print(f"analysis_dir={analysis_dir}")
for path in required_paths:
    print(path)
PY
