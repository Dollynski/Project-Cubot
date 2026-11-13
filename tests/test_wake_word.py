import numpy as np
import pytest

from cubo.voice.wake_word import WakeWordDetector


class FakeWakeModel:
    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.resets = 0

    def predict(self, _frame: np.ndarray) -> dict[str, float]:
        return self.scores

    def reset(self) -> None:
        self.resets += 1


FRAME = np.zeros(1280, np.float32)


@pytest.mark.parametrize("score, expected", [(0.2, False), (0.5, True), (0.9, True)])
def test_fires_at_or_above_the_threshold(score, expected, tmp_path):
    detector = WakeWordDetector(
        tmp_path / "x.onnx", 0.5, model=FakeWakeModel({"hey_jarvis": score})
    )

    assert detector.detected(FRAME) is expected


def test_no_scores_means_no_detection(tmp_path):
    assert (
        WakeWordDetector(tmp_path / "x.onnx", 0.5, model=FakeWakeModel({})).detected(FRAME) is False
    )


def test_reset_clears_the_model_state(tmp_path):
    model = FakeWakeModel({})

    WakeWordDetector(tmp_path / "x.onnx", 0.5, model=model).reset()

    assert model.resets == 1
