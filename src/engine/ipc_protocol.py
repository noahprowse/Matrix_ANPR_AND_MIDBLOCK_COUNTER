"""IPC message types for multiprocessing Queue communication.

Defines the protocol used between worker processes and the main GUI thread.
All messages flow through a shared multiprocessing.Queue as IPCMessage instances.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MsgType(Enum):
    PROGRESS = "progress"            # stream progress update
    FRAME = "frame"                  # preview frame (JPEG bytes)
    STATUS = "status"                # status text update
    RESULT = "result"                # individual detection result
    FINISHED = "finished"            # stream completed
    ERROR = "error"                  # stream error
    HEARTBEAT = "heartbeat"          # worker alive signal
    VIDEO_STARTED = "video_started"  # new video in stream


@dataclass
class IPCMessage:
    """A single message sent from a worker process to the monitor bridge.

    Attributes:
        stream_id:  Which processing stream sent this message.
        msg_type:   The category of message (see MsgType).
        payload:    Arbitrary dict of data specific to msg_type.
        timestamp:  time.time() value when the message was created.
    """

    stream_id: int
    msg_type: MsgType
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0  # time.time() when created
