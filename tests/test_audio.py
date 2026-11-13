import numpy as np
import pytest

from cubo.voice.audio import (
    FRAME_SAMPLES,
    SAMPLE_RATE,
    AudioClip,
    FrameBuffer,
    StreamResampler,
    chime,
    resample,
    to_float32,
)


def tone(rate: int, seconds: float, amplitude: float = 0.5, frequency: float = 440.0):
    time = np.arange(int(rate * seconds)) / rate
    return (amplitude * np.sin(2 * np.pi * frequency * time)).astype(np.float32)


def test_int16_becomes_float_in_range():
    converted = to_float32(np.array([0, 16384, -32768], dtype=np.int16))

    assert converted.dtype == np.float32
    assert converted.tolist() == [0.0, 0.5, -1.0]


def test_float_samples_are_clipped():
    assert to_float32(np.array([2.0, -2.0, 0.25])).tolist() == [1.0, -1.0, 0.25]


def test_resampler_keeps_16khz_audio_untouched():
    block = tone(SAMPLE_RATE, 0.08)

    assert np.array_equal(StreamResampler(SAMPLE_RATE)(block), block)


def test_resampler_converts_a_stream_to_16khz():
    resampler = StreamResampler(48_000)
    block_size = int(48_000 * 0.08)
    audio = tone(48_000, 0.8)

    output = np.concatenate(
        [resampler(audio[start : start + block_size]) for start in range(0, len(audio), block_size)]
    )

    assert output.dtype == np.float32
    # O filtro do reamostrador segura cerca de 35 ms de áudio.
    assert 0.8 * SAMPLE_RATE - 800 < len(output) <= 0.8 * SAMPLE_RATE
    # Depois do início do filtro, o tom mantém a amplitude original.
    assert output[400:].max() == pytest.approx(0.5, abs=0.05)


def test_resampler_never_exceeds_full_scale():
    square = np.tile(np.array([32767, -32768], dtype=np.int16).repeat(24), 200)

    output = StreamResampler(48_000)(square)

    assert output.max() <= 1.0
    assert output.min() >= -1.0


def test_frame_buffer_regroups_blocks_in_order():
    buffer = FrameBuffer(frame_samples=4)

    assert buffer.push(np.arange(0, 3, dtype=np.float32)) == []
    frames = buffer.push(np.arange(3, 11, dtype=np.float32))

    assert [frame.tolist() for frame in frames] == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert [frame.tolist() for frame in buffer.push(np.array([11.0], np.float32))] == [
        [8, 9, 10, 11]
    ]


def test_frame_buffer_clear_drops_the_leftover():
    buffer = FrameBuffer(frame_samples=4)
    buffer.push(np.arange(3, dtype=np.float32))

    buffer.clear()

    assert buffer.push(np.arange(4, dtype=np.float32))[0].tolist() == [0, 1, 2, 3]


def test_default_frame_is_80_milliseconds():
    assert pytest.approx(0.08) == FRAME_SAMPLES / SAMPLE_RATE


def test_resample_whole_clip():
    clip = AudioClip(tone(22_050, 1.0), 22_050)

    converted = resample(clip, SAMPLE_RATE)

    assert converted.sample_rate == SAMPLE_RATE
    assert converted.samples.dtype == np.float32
    assert len(converted.samples) == pytest.approx(SAMPLE_RATE, abs=50)


def test_resample_same_rate_returns_the_same_clip():
    clip = AudioClip(tone(SAMPLE_RATE, 0.1), SAMPLE_RATE)

    assert resample(clip, SAMPLE_RATE) is clip


def test_chime_is_short_quiet_and_does_not_click():
    clip = chime()

    assert clip.sample_rate == SAMPLE_RATE
    assert len(clip.samples) == int(SAMPLE_RATE * 0.12)
    assert np.abs(clip.samples).max() <= 0.3
    assert abs(clip.samples[0]) < 0.01
    assert abs(clip.samples[-1]) < 0.05
