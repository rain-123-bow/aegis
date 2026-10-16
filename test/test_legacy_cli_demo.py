from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def load_demo():
    spec = importlib.util.spec_from_file_location(
        "legacy_cli_demo", Path(__file__).with_name("test.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyCliDemoTests(unittest.TestCase):
    def test_no_arguments_cannot_contact_existing_threads(self) -> None:
        demo = load_demo()
        with (
            patch.object(demo, "send_prompt_to_thread", return_value="fixture output") as send,
            patch.object(sys, "argv", ["test.py"]),
            contextlib.redirect_stderr(io.StringIO()),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as stopped,
        ):
            demo.main()
        self.assertEqual(stopped.exception.code, 2)
        send.assert_not_called()

    def test_only_explicit_threads_and_prompt_are_used(self) -> None:
        demo = load_demo()
        output = io.StringIO()
        with (
            patch.object(demo, "send_prompt_to_thread", side_effect=["first output", "second output"]) as send,
            patch.object(sys, "argv", ["test.py", "--thread-a", "current-a", "--thread-b", "current-b", "--prompt", "current task"]),
            contextlib.redirect_stdout(output),
        ):
            demo.main()
        self.assertEqual(
            [call.args for call in send.call_args_list],
            [("current-a", "current task"), ("current-b", "first output")],
        )
        self.assertEqual(output.getvalue(), "second output\n")


if __name__ == "__main__":
    unittest.main()
