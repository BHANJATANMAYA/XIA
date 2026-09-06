import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from interface.voice import SpeechOutput, normalize_voice_command


class VoiceCommandTests(unittest.TestCase):
    def test_normalizes_explicit_spoken_controls(self):
        self.assertEqual(normalize_voice_command("  Exit   Xia "), "/exit")
        self.assertEqual(normalize_voice_command("stop listening"), "/voice off")

    def test_keeps_regular_requests_unchanged(self):
        request = "Summarize my project plan"
        self.assertEqual(normalize_voice_command(request), request)

    def test_speech_output_removes_markdown_before_speaking(self):
        self.assertEqual(
            SpeechOutput._plain_text("Read [the guide](https://example.com) and `continue`."),
            "Read the guide and continue.",
        )


if __name__ == "__main__":
    unittest.main()
