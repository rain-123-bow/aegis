from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from frozen_input_watcher import FrozenInputWatcher


class FrozenInputWatcherTests(unittest.TestCase):
    def test_immediate_stop_retains_a_completed_change_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(20):
                target = root / f"event-{index:02d}.txt"
                watcher = FrozenInputWatcher(root)
                watcher.start()
                self.assertTrue(watcher.listening)
                target.write_text("changed\n", encoding="utf-8")
                events = watcher.stop()
                self.assertFalse(watcher.listening)
                self.assertTrue(
                    any(
                        event.path == target.resolve()
                        or event.action == "journal_overflow"
                        for event in events
                    ),
                    msg=f"watcher lost immediate change for {target}",
                )


if __name__ == "__main__":
    unittest.main()
