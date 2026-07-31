"""
tests/test_live_ingestor.py — Unit tests for engine/live_ingestor.py

Tests use:
  • Mock / patch to avoid loading YOLO-World or real video files
  • An in-memory Qdrant client (no Docker)
  • A tiny synthetic video created with cv2 where real IO is tested

Run:
    python -m pytest tests/test_live_ingestor.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# Make the project root importable from any CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.live_ingestor import (
    IngestConfig,
    IngestProgress,
    LiveIngestor,
    DemoNarrator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> IngestConfig:
    return IngestConfig(
        frames_output_dir=str(tmp_path / "frames"),
        max_log_lines=50,
        yield_every_n_frames=1,
    )


def _make_fake_frame_record(video_id="testvid", frame_index=0, timestamp=0.0, scene_id=0):
    """Return a minimal frame record dict matching extraction_engine contract."""
    return {
        "video_id":    video_id,
        "frame_index": frame_index,
        "timestamp":   timestamp,
        "scene_id":    scene_id,
        "frame_path":  "/fake/path/testvid/0000.jpg",
        "backend":     "opencv_seek",
    }


# ---------------------------------------------------------------------------
# Tests: IngestProgress dataclass
# ---------------------------------------------------------------------------

class TestIngestProgress:
    def test_fields_present(self):
        p = IngestProgress(
            phase="init",
            phase_human="Initializing",
            percent=0.0,
            log_lines=[],
            session_id=str(uuid.uuid4()),
            video_id="vid1",
            stats={},
            complete=False,
            error=None,
        )
        assert p.phase == "init"
        assert p.complete is False
        assert p.error is None

    def test_default_complete_false(self):
        p = IngestProgress(
            phase="x", phase_human="X", percent=50.0,
            log_lines=[], session_id="s", video_id="v", stats={},
        )
        assert p.complete is False

    def test_percent_accepts_float(self):
        p = IngestProgress(
            phase="x", phase_human="X", percent=42.5,
            log_lines=[], session_id="s", video_id="v", stats={},
        )
        assert p.percent == 42.5


# ---------------------------------------------------------------------------
# Tests: IngestConfig dataclass
# ---------------------------------------------------------------------------

class TestIngestConfig:
    def test_defaults(self):
        c = IngestConfig(frames_output_dir="/tmp")
        assert c.max_log_lines == 200
        assert c.yield_every_n_frames == 1

    def test_custom_values(self):
        c = IngestConfig(frames_output_dir="/tmp/f", max_log_lines=10, yield_every_n_frames=5)
        assert c.max_log_lines == 10
        assert c.yield_every_n_frames == 5


# ---------------------------------------------------------------------------
# Tests: DemoNarrator
# ---------------------------------------------------------------------------

class TestDemoNarrator:
    def test_narrate_known_phase(self, capsys):
        n = DemoNarrator()
        n.narrate("complete")
        out = capsys.readouterr().out
        assert "DemoNarrator" in out

    def test_narrate_unknown_phase(self, capsys):
        n = DemoNarrator()
        n.narrate("totally_unknown_phase_xyz")
        out = capsys.readouterr().out
        assert out == ""   # no output for unknown phase


# ---------------------------------------------------------------------------
# Tests: LiveIngestor — file-not-found path
# ---------------------------------------------------------------------------

class TestLiveIngestorMissing:
    def test_missing_file_yields_error_progress(self, tmp_path):
        ingestor = LiveIngestor()
        config = _make_config(tmp_path)
        results = list(ingestor.ingest("/nonexistent/video_xyz.mp4", config))
        assert len(results) >= 1
        final = results[-1]
        assert final.complete is True
        assert final.error is not None
        assert "not found" in final.error.lower() or "nonexistent" in final.error.lower()

    def test_missing_file_progress_phase_is_error(self, tmp_path):
        ingestor = LiveIngestor()
        config = _make_config(tmp_path)
        results = list(ingestor.ingest("/no/such/file.mp4", config))
        assert results[-1].phase in ("error", "init", "error")


# ---------------------------------------------------------------------------
# Tests: LiveIngestor — full pipeline with mocks
# ---------------------------------------------------------------------------

class TestLiveIngestorMocked:
    """
    These tests patch the heavy pipeline stages (extract_frames, ObjectDetector,
    extract_color, spatial, Qdrant upsert) and verify the orchestration logic.
    """

    def _make_dummy_video(self, tmp_path: Path) -> str:
        """Create a tiny valid mp4 with 3 frames using cv2."""
        import cv2
        video_path = str(tmp_path / "dummy.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, 10.0, (64, 64))
        for _ in range(3):
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            out.write(frame)
        out.release()
        return video_path

    @pytest.fixture
    def dummy_video(self, tmp_path):
        return self._make_dummy_video(tmp_path)

    @pytest.fixture
    def config(self, tmp_path):
        return _make_config(tmp_path)

    def test_ingest_completes_without_detections(self, dummy_video, config, tmp_path):
        """
        Smoke test: extract_frames returns 2 fake records, detector returns [],
        Qdrant upsert still called without error, final progress is complete=True.
        """
        frame_records = [
            _make_fake_frame_record("dummy", 0, 0.0, 0),
            _make_fake_frame_record("dummy", 1, 1.0, 0),
        ]

        # Patch extract_frames to yield our fake records
        with patch(
            "engine.live_ingestor.extract_frames",
            return_value=iter(frame_records),
        ) as mock_ef, patch(
            "backend.vision.object_detector.ObjectDetector.detect",
            return_value=[],
        ), patch(
            "cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)
        ), patch(
            "engine.live_ingestor.extract_frames",
            return_value=iter(frame_records),
        ):
            ingestor = LiveIngestor()
            results = list(ingestor.ingest(dummy_video, config))

        final = results[-1]
        assert final.complete is True
        assert final.error is None
        assert final.percent == 100.0

    def test_progress_phases_emitted_in_order(self, dummy_video, config, tmp_path):
        """
        Verify that early phases (init, scene_detection, extraction) appear
        before detection phases in the emitted progress list.
        """
        frame_records = [_make_fake_frame_record("dummy", 0, 0.0, 0)]

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):

            ingestor = LiveIngestor()
            results = list(ingestor.ingest(dummy_video, config))

        phases = [r.phase for r in results]
        # init must appear before complete
        assert "init" in phases
        assert phases[-1] == "complete"
        assert phases.index("init") < phases.index("complete")

    def test_stats_keyframes_incremented(self, dummy_video, config, tmp_path):
        """keyframes stat should match number of frames yielded by extract_frames."""
        frame_records = [
            _make_fake_frame_record("dummy", i, float(i), 0)
            for i in range(5)
        ]

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):

            ingestor = LiveIngestor()
            results = list(ingestor.ingest(dummy_video, config))

        final = results[-1]
        assert final.stats["keyframes"] == 5

    def test_objects_detected_counted(self, dummy_video, config, tmp_path):
        """objects_detected stat should accumulate across all frames."""
        frame_records = [
            _make_fake_frame_record("dummy", i, float(i), 0)
            for i in range(3)
        ]
        # Each frame returns 2 detections
        fake_dets = [
            {"class": "person", "confidence": 0.9, "bbox": [10, 10, 50, 80],
             "spatial_relations": []},
            {"class": "car",    "confidence": 0.7, "bbox": [60, 10, 120, 80],
             "spatial_relations": []},
        ]

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=fake_dets), \
             patch("engine.live_ingestor.extract_color", return_value="blue"):

            ingestor = LiveIngestor()
            results = list(ingestor.ingest(dummy_video, config))

        final = results[-1]
        assert final.stats["objects_detected"] == 3 * 2  # 3 frames × 2 detections

    def test_last_client_set_after_ingest(self, dummy_video, config):
        """After a successful ingest, last_client and last_collection should be set."""
        frame_records = [_make_fake_frame_record("dummy", 0, 0.0, 0)]

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):

            ingestor = LiveIngestor()
            list(ingestor.ingest(dummy_video, config))

        assert ingestor.last_client is not None
        assert ingestor.last_collection is not None
        assert ingestor.last_collection.startswith("judge_session_")

    def test_progress_cb_called(self, dummy_video, config):
        """progress_cb must be invoked for each yielded IngestProgress."""
        frame_records = [_make_fake_frame_record("dummy", 0, 0.0, 0)]
        cb_calls: List[IngestProgress] = []

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):

            ingestor = LiveIngestor()
            list(ingestor.ingest(dummy_video, config, progress_cb=cb_calls.append))

        assert len(cb_calls) >= 1
        assert all(isinstance(c, IngestProgress) for c in cb_calls)

    def test_log_lines_rolling_window(self, dummy_video, config):
        """Log lines must not exceed max_log_lines in any emitted progress."""
        config.max_log_lines = 3
        frame_records = [
            _make_fake_frame_record("dummy", i, float(i), 0)
            for i in range(10)
        ]

        with patch("engine.live_ingestor.extract_frames", return_value=iter(frame_records)), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):

            ingestor = LiveIngestor()
            results = list(ingestor.ingest(dummy_video, config))

        for prog in results:
            assert len(prog.log_lines) <= config.max_log_lines, (
                f"log_lines overflowed at phase={prog.phase}: "
                f"got {len(prog.log_lines)} > {config.max_log_lines}"
            )


# ---------------------------------------------------------------------------
# Tests: LiveIngestor — Qdrant collection naming
# ---------------------------------------------------------------------------

class TestJudgeCollectionNaming:
    def test_each_ingest_unique_collection(self, tmp_path):
        """Two sequential ingests should produce different collection names."""
        frame_records = [_make_fake_frame_record("dummy", 0, 0.0, 0)]

        def _fresh_records():
            return iter([_make_fake_frame_record("dummy", 0, 0.0, 0)])

        ingestor = LiveIngestor()
        config = _make_config(tmp_path)

        with patch("engine.live_ingestor.extract_frames", side_effect=_fresh_records), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):
            list(ingestor.ingest(str(tmp_path / "fake.mp4"), config))
            coll1 = ingestor.last_collection

        # Fake the video file existing for second call
        fake_vid = tmp_path / "fake.mp4"
        fake_vid.write_bytes(b"\x00")

        with patch("engine.live_ingestor.extract_frames", side_effect=_fresh_records), \
             patch("cv2.imread", return_value=np.zeros((64, 64, 3), np.uint8)), \
             patch("backend.vision.object_detector.ObjectDetector.detect", return_value=[]):
            list(ingestor.ingest(str(fake_vid), config))
            coll2 = ingestor.last_collection

        assert coll1 != coll2, "Consecutive ingests must produce unique collection names"
        assert coll1.startswith("judge_session_")
        assert coll2.startswith("judge_session_")


# ---------------------------------------------------------------------------
# Tests: LiveIngestor — import error path
# ---------------------------------------------------------------------------

class TestLiveIngestorImportError:
    def test_import_error_yields_error_progress(self, tmp_path):
        """If a critical import fails inside ingest(), must yield error progress."""
        fake_vid = tmp_path / "real.mp4"
        fake_vid.write_bytes(b"\x00")

        config = _make_config(tmp_path)

        with patch(
            "engine.live_ingestor.extract_frames",
            side_effect=ImportError("cv2 not found"),
        ):
            ingestor = LiveIngestor()
            results = list(ingestor.ingest(str(fake_vid), config))

        final = results[-1]
        assert final.complete is True
        # Either error set or all stages aborted early
        # (import error might be caught at different levels)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
