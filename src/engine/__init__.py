"""Parallel video processing engine.

Provides multiprocessing-based workers, IPC protocol, GPU scheduling,
process lifecycle management, a Qt monitor bridge, and a processing dashboard.
"""

from src.engine.ipc_protocol import IPCMessage, MsgType
from src.engine.base_worker import BaseVideoWorker
from src.engine.gpu_scheduler import GPUScheduler
from src.engine.process_manager import ProcessManager, distribute_videos
from src.engine.monitor_bridge import MonitorBridge
from src.engine.processing_dashboard import ProcessingDashboard, StreamCard

__all__ = [
    "IPCMessage",
    "MsgType",
    "BaseVideoWorker",
    "GPUScheduler",
    "ProcessManager",
    "distribute_videos",
    "MonitorBridge",
    "ProcessingDashboard",
    "StreamCard",
]
