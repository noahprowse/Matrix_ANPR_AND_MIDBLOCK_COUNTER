"""Thread-safe GPU slot allocator.

Manages a fixed pool of GPU inference slots so that multiple worker
processes do not oversubscribe VRAM.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def _cuda_available() -> bool:
    """Check whether CUDA is available via PyTorch."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        logger.warning("PyTorch not installed — GPU scheduling disabled")
        return False


class GPUScheduler:
    """Thread-safe allocator for a limited number of GPU inference slots.

    Parameters:
        max_instances: Maximum number of concurrent GPU workers allowed.
                       Defaults to 4.
    """

    def __init__(self, max_instances: int = 4) -> None:
        self._max = max_instances
        self._in_use = 0
        self._lock = threading.Lock()
        self._has_cuda = _cuda_available()

        if self._has_cuda:
            logger.info("GPUScheduler: CUDA available, max %d slots", self._max)
        else:
            logger.info("GPUScheduler: CUDA not available, all workers will use CPU")

    # ── Public API ────────────────────────────────────────────────────

    def request_gpu(self) -> bool:
        """Try to acquire a GPU slot.

        Returns True if a slot was successfully reserved (caller should use
        GPU and later call release_gpu()). Returns False if no slots are
        available or CUDA is not present.
        """
        if not self._has_cuda:
            return False

        with self._lock:
            if self._in_use < self._max:
                self._in_use += 1
                logger.debug(
                    "GPU slot acquired (%d/%d in use)", self._in_use, self._max
                )
                return True
            return False

    def release_gpu(self) -> None:
        """Release a previously acquired GPU slot."""
        with self._lock:
            if self._in_use > 0:
                self._in_use -= 1
                logger.debug(
                    "GPU slot released (%d/%d in use)", self._in_use, self._max
                )

    # ── Properties ────────────────────────────────────────────────────

    @property
    def available(self) -> int:
        """Number of GPU slots currently free."""
        with self._lock:
            if not self._has_cuda:
                return 0
            return self._max - self._in_use

    @property
    def has_cuda(self) -> bool:
        """Whether CUDA was detected at construction time."""
        return self._has_cuda

    @property
    def max_instances(self) -> int:
        """Configured maximum GPU slots."""
        return self._max

    @property
    def in_use(self) -> int:
        """Number of GPU slots currently occupied."""
        with self._lock:
            return self._in_use
