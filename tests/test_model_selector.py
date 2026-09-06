import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from core.model_selector import HardwareAwareModelSelector


class FakeLLM:
    def __init__(self, models):
        self.models = models

    def list_model_details(self):
        return self.models


def model(name, size_gb, parameter_size):
    return {
        "name": name,
        "size": size_gb * 1024 ** 3,
        "details": {"parameter_size": parameter_size},
    }


class ModelSelectorTests(unittest.TestCase):
    def test_selects_largest_model_that_fits(self):
        host = SimpleNamespace(ram_gb=8.0, vram_gb=0.0, has_gpu=lambda: False)
        selector = HardwareAwareModelSelector(
            FakeLLM([model("tiny:1b", 1.0, "1B"), model("fast:4b", 3.0, "4B"), model("large:9b", 7.0, "9B")]),
            host,
        )
        selection = selector.select()
        self.assertEqual(selection.model, "fast:4b")
        self.assertEqual(selection.allowed_models, ("tiny:1b", "fast:4b"))

    def test_excludes_embedding_models(self):
        host = SimpleNamespace(ram_gb=16.0, vram_gb=0.0, has_gpu=lambda: False)
        selector = HardwareAwareModelSelector(
            FakeLLM([model("nomic-embed-text", 0.3, "137M"), model("chat:7b", 4.5, "7B")]),
            host,
        )
        self.assertEqual(selector.select().model, "chat:7b")


if __name__ == "__main__":
    unittest.main()
