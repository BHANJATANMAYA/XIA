"""Local microphone capture and speech-to-text for the xia CLI.

The audio never leaves the computer.  faster-whisper downloads the configured
model on first use, then transcribes subsequent requests locally.
"""

from __future__ import annotations

import queue
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class VoiceError(RuntimeError):
    """Raised when recording or transcription cannot be completed."""


@dataclass(frozen=True)
class VoiceResult:
    text: str
    duration_seconds: float


def normalize_voice_command(text: str) -> str:
    """Turn a few unambiguous spoken controls into their CLI equivalents."""
    normalized = " ".join(text.lower().strip().split())
    commands = {
        "exit": "/exit",
        "exit xia": "/exit",
        "quit": "/quit",
        "quit xia": "/quit",
        "clear": "/clear",
        "clear conversation": "/clear",
        "help": "/help",
        "show help": "/help",
        "stop listening": "/voice off",
        "voice off": "/voice off",
    }
    return commands.get(normalized, text.strip())


class VoiceInput:
    """Record one utterance and transcribe it with a local Whisper model."""

    def __init__(self, config, models_dir: Path):
        self.config = config
        self.models_dir = models_dir
        self._model = None

    def listen(self) -> VoiceResult:
        sounddevice, numpy = self._audio_dependencies()
        chunks, duration = self._record(sounddevice, numpy)
        if not chunks:
            raise VoiceError("No audio was captured. Check that a microphone is connected.")

        audio = numpy.concatenate(chunks, axis=0).reshape(-1)
        if not numpy.any(numpy.abs(audio) >= self.config.silence_threshold):
            raise VoiceError("I could not hear any speech. Try speaking closer to the microphone.")

        segments, _ = self._get_model().transcribe(
            audio,
            language=self.config.language or None,
            vad_filter=True,
            beam_size=5,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            raise VoiceError("I could not understand that. Please try again.")
        return VoiceResult(text=normalize_voice_command(text), duration_seconds=duration)

    def prepare(self) -> None:
        """Load the model before recording so the user is never kept waiting after speaking."""
        self._get_model()

    @staticmethod
    def input_devices() -> list[str]:
        """Return input-capable microphone names without opening a recording stream."""
        try:
            import sounddevice
            devices = sounddevice.query_devices()
        except ImportError as exc:
            raise VoiceError("Voice support is not installed. Re-run xia to install it.") from exc
        except Exception as exc:
            raise VoiceError(f"Could not list microphones: {exc}") from exc

        return [
            f"{index}: {device['name']}"
            for index, device in enumerate(devices)
            if device["max_input_channels"] > 0
        ]

    def _audio_dependencies(self):
        try:
            import numpy
            import sounddevice
        except ImportError as exc:
            raise VoiceError(
                "Voice support is not installed. Re-run xia so the launcher can install "
                "the new optional voice dependencies."
            ) from exc
        return sounddevice, numpy

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise VoiceError(
                "Voice support is not installed. Re-run xia so the launcher can install "
                "the new optional voice dependencies."
            ) from exc

        model_dir = self.models_dir / "whisper"
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = WhisperModel(
                self.config.model,
                device="cpu",
                compute_type="int8",
                download_root=str(model_dir),
            )
        except Exception as exc:
            raise VoiceError(
                f"Could not load the voice model '{self.config.model}': {exc}"
            ) from exc
        return self._model

    def _record(self, sounddevice, numpy):
        audio_queue: queue.Queue = queue.Queue()
        sample_rate = self.config.sample_rate
        block_size = 1024
        chunks = []
        heard_speech = False
        silence_started: Optional[float] = None
        started = time.monotonic()

        def callback(indata, frames, time_info, status):
            if status:
                # The caller receives a useful result or error after recording; a
                # transient overflow should not crash the audio callback thread.
                pass
            audio_queue.put(indata.copy())

        try:
            with sounddevice.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=block_size,
                device=self.config.device or None,
                callback=callback,
            ):
                while time.monotonic() - started < self.config.max_record_seconds:
                    try:
                        chunk = audio_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    chunks.append(chunk)
                    level = float(numpy.sqrt(numpy.mean(numpy.square(chunk))))
                    if level >= self.config.silence_threshold:
                        heard_speech = True
                        silence_started = None
                    elif heard_speech:
                        silence_started = silence_started or time.monotonic()
                        if time.monotonic() - silence_started >= self.config.silence_seconds:
                            break
        except Exception as exc:
            raise VoiceError(f"Could not use the microphone: {exc}") from exc

        return chunks, time.monotonic() - started


class SpeechOutput:
    """Optional local text-to-speech using the operating system's speech engine."""

    def __init__(self, rate: int = 180):
        self.rate = rate
        self._engine = None

    def speak(self, text: str) -> None:
        try:
            import pyttsx3
        except ImportError as exc:
            raise VoiceError("Text-to-speech is not installed. Re-run xia to install it.") from exc

        try:
            if self._engine is None:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", self.rate)
            self._engine.say(self._plain_text(text))
            self._engine.runAndWait()
        except Exception as exc:
            raise VoiceError(f"Could not speak the response: {exc}") from exc

    @staticmethod
    def _plain_text(text: str) -> str:
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[`*_#>]", "", text)
        return " ".join(text.split())
