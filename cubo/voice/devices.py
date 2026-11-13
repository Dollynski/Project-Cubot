"""Microfone e alto-falante, via PortAudio.

Fica separado dos demais módulos de voz porque o ``sounddevice`` exige a biblioteca
``libportaudio2`` do sistema: só quem de fato usa o áudio precisa dela.
"""

import logging
import queue
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from cubo.errors import SetupError
from cubo.voice.audio import AudioClip, FrameBuffer, StreamResampler, resample

logger = logging.getLogger(__name__)

BLOCK_SECONDS = 0.08
QUEUE_POLL_SECONDS = 0.2

DeviceId = int | str | None


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    inputs: int
    outputs: int


def list_devices() -> list[AudioDevice]:
    return [
        AudioDevice(index, info["name"], info["max_input_channels"], info["max_output_channels"])
        for index, info in enumerate(sd.query_devices())
    ]


def _device_info(device: DeviceId, kind: str) -> dict:
    label = "microfone" if kind == "input" else "alto-falante"
    try:
        return sd.query_devices(device, kind)
    except (sd.PortAudioError, ValueError) as error:
        raise SetupError(
            f"Dispositivo de {label} inválido ({device!r}): {error}. "
            "Veja as opções com `cubo audio`."
        ) from error


class Microphone:
    """Entrega o áudio do microfone em quadros de 80 ms, a 16 kHz, mono."""

    def __init__(self, device: DeviceId) -> None:
        self._rate = int(_device_info(device, "input")["default_samplerate"])
        self._blocks: queue.Queue[np.ndarray] = queue.Queue()
        self._resampler = StreamResampler(self._rate)
        self._buffer = FrameBuffer()
        try:
            self._stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=self._rate,
                dtype="float32",
                blocksize=int(self._rate * BLOCK_SECONDS),
                callback=self._on_block,
            )
        except sd.PortAudioError as error:
            raise SetupError(f"Não consegui abrir o microfone: {error}") from error

    def __enter__(self) -> "Microphone":
        try:
            self._stream.start()
        except sd.PortAudioError as error:
            raise SetupError(f"Não consegui iniciar o microfone: {error}") from error
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self._stream.close()

    def frames(self, stop: threading.Event) -> Iterator[np.ndarray]:
        while not stop.is_set():
            try:
                block = self._blocks.get(timeout=QUEUE_POLL_SECONDS)
            except queue.Empty:
                continue
            yield from self._buffer.push(self._resampler(block))

    def flush(self) -> None:
        while True:
            try:
                self._blocks.get_nowait()
            except queue.Empty:
                break
        self._buffer.clear()

    def _on_block(self, data: np.ndarray, _frames: int, _time: object, status: object) -> None:
        if status:
            logger.debug("Aviso do microfone: %s", status)
        self._blocks.put(data[:, 0].copy())


class SoundDevicePlayer:
    def __init__(self, device: DeviceId) -> None:
        info = _device_info(device, "output")
        self._device = device
        self._rate = int(info["default_samplerate"])
        # Algumas placas só abrem em estéreo: repete o canal em vez de falhar.
        self._channels = min(2, int(info["max_output_channels"]))

    def play(self, clip: AudioClip) -> None:
        if len(clip.samples) == 0:
            return
        samples = resample(clip, self._rate).samples
        sd.play(
            np.tile(samples[:, None], (1, self._channels)),
            self._rate,
            device=self._device,
            blocking=True,
        )
