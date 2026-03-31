from __future__ import annotations

from trampoline.pipeline import build_frames_meta


def test_frames_meta_maps_frame_indexes_to_timestamps() -> None:
    frames_meta = build_frames_meta(
        source_video="samples/tra_demo/sample01.mp4",
        fps=24.0,
        frame_count=5,
        width=360,
        height=640,
    )

    assert frames_meta["fps"] == 24.0
    assert frames_meta["frame_count"] == 5
    assert frames_meta["width"] == 360
    assert frames_meta["height"] == 640
    assert frames_meta["frames"][0] == {"frame_index": 0, "timestamp_ms": 0}
    assert frames_meta["frames"][2] == {"frame_index": 2, "timestamp_ms": 83}
    assert frames_meta["frames"][-1] == {"frame_index": 4, "timestamp_ms": 167}
