"""
core/host.py — Host Machine Detection

Detects the capabilities of whatever machine the SSD is plugged into.
xia adapts its behaviour based on what resources are available.

Detects:
  - CPU cores and speed
  - Available RAM
  - GPU presence (CUDA/ROCm)
  - OS version
  - Drive letter (for display)
  - Whether we're on the same machine as last time

Usage:
    from core.host import HostInfo
    host = HostInfo()
    print(host.summary())
    # → "Windows 11, 16GB RAM, 8 cores, NVIDIA GPU (CUDA)"

    # Recommended model size given available RAM
    print(host.recommended_model_size())
    # → "7b"  or  "3b"  or  "13b"
"""

import os
import platform
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class HostInfo:
    """Snapshot of the host machine's capabilities."""

    os_name:      str = ""
    os_version:   str = ""
    cpu_cores:    int = 0
    ram_gb:       float = 0.0
    has_cuda:     bool = False
    has_rocm:     bool = False
    gpu_name:     Optional[str] = None
    vram_gb:      float = 0.0
    drive_letter: str = ""
    hostname:     str = ""

    def __post_init__(self):
        self._detect()

    def _detect(self):
        """Detect host capabilities."""
        # OS
        self.os_name    = platform.system()
        self.os_version = platform.version()
        self.hostname   = platform.node()

        # CPU
        self.cpu_cores = os.cpu_count() or 1

        # RAM
        self.ram_gb = self._detect_ram()

        # GPU
        self._detect_gpu()

        # Drive letter (Windows)
        if self.os_name == "Windows":
            from core.paths import PATHS
            drive = PATHS.root.drive  # e.g. "D:"
            self.drive_letter = drive

    def _detect_ram(self) -> float:
        """Read installed RAM without requiring an optional package or deprecated WMIC."""
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 ** 3)
        except ImportError:
            pass

        if self.os_name == "Windows":
            try:
                import ctypes

                class MemoryStatus(ctypes.Structure):
                    _fields_ = [
                        ("length", ctypes.c_ulong),
                        ("memory_load", ctypes.c_ulong),
                        ("total_phys", ctypes.c_ulonglong),
                        ("avail_phys", ctypes.c_ulonglong),
                        ("total_page_file", ctypes.c_ulonglong),
                        ("avail_page_file", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong),
                        ("avail_virtual", ctypes.c_ulonglong),
                        ("avail_extended_virtual", ctypes.c_ulonglong),
                    ]

                status = MemoryStatus()
                status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return status.total_phys / (1024 ** 3)
            except Exception:
                pass

        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
        except Exception:
            return 8.0  # Conservative default

    def _detect_gpu(self):
        """Check for CUDA or ROCm GPU."""
        # CUDA
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                self.has_cuda = True
                name, memory_mb = result.stdout.strip().splitlines()[0].rsplit(",", 1)
                self.gpu_name = name.strip()
                self.vram_gb = round(float(memory_mb.strip()) / 1024, 1)
                return
        except Exception:
            pass

        # ROCm (AMD)
        try:
            import subprocess
            result = subprocess.run(
                ["rocminfo"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self.has_rocm = True
                return
        except Exception:
            pass

    def has_gpu(self) -> bool:
        return self.has_cuda or self.has_rocm

    def recommended_model_size(self) -> str:
        """
        Recommend a model size based on available RAM.
        These are conservative recommendations for good performance.
        """
        if self.has_gpu and self.ram_gb >= 16:
            return "13b"
        elif self.ram_gb >= 16:
            return "7b"
        elif self.ram_gb >= 8:
            return "7b"
        else:
            return "3b"

    def ollama_env(self) -> dict:
        """
        Return environment variables to optimise Ollama for this host.
        These are set by the launcher before starting Ollama.
        """
        env = {}

        # Tell Ollama how many CPU threads to use
        # Leave 2 cores for the OS and other processes
        threads = max(1, self.cpu_cores - 2)
        env["OLLAMA_NUM_THREADS"] = str(threads)

        # GPU layers — push as many layers to GPU as possible
        if self.has_cuda:
            env["OLLAMA_GPU_LAYERS"] = "999"  # Let Ollama decide max
        elif self.has_rocm:
            env["OLLAMA_GPU_LAYERS"] = "999"
            env["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"

        return env

    def summary(self) -> str:
        parts = [f"{self.os_name}"]
        if self.ram_gb > 0:
            parts.append(f"{self.ram_gb:.0f}GB RAM")
        if self.cpu_cores > 0:
            parts.append(f"{self.cpu_cores} cores")
        if self.has_cuda and self.gpu_name:
            parts.append(f"{self.gpu_name} (CUDA)")
        elif self.has_rocm:
            parts.append("AMD GPU (ROCm)")
        else:
            parts.append("CPU only")
        return ", ".join(parts)

    def __repr__(self) -> str:
        return f"HostInfo({self.summary()})"
