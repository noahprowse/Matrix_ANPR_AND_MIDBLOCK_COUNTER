"""TensorRT model export utility for YOLO models.

Exports YOLO .pt models to TensorRT .engine format for 3-4x faster inference.
Supports FP16 (recommended) and INT8 (requires calibration dataset).

Usage:
    from src.common.tensorrt_export import export_to_tensorrt
    engine_path = export_to_tensorrt("yolo11x.pt", half=True)
"""

import logging
import os

logger = logging.getLogger(__name__)


def is_tensorrt_available() -> bool:
    """Check if TensorRT is available on this system."""
    try:
        import tensorrt  # noqa: F401
        return True
    except ImportError:
        return False


def is_cuda_available() -> bool:
    """Check if CUDA GPU is available."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def get_engine_path(model_path: str, half: bool = True) -> str:
    """Get the expected TensorRT engine path for a model."""
    base = os.path.splitext(model_path)[0]
    suffix = "_fp16" if half else "_fp32"
    return f"{base}{suffix}.engine"


def export_to_tensorrt(
    model_path: str = "yolo11x.pt",
    half: bool = True,
    imgsz: int = 640,
    batch: int = 1,
    workspace: int = 4,
) -> str | None:
    """Export a YOLO model to TensorRT engine format.

    Args:
        model_path: Path to YOLO .pt model
        half: Use FP16 precision (recommended, negligible accuracy loss)
        imgsz: Input image size
        batch: Batch size
        workspace: GPU workspace in GB

    Returns:
        Path to exported .engine file, or None if export failed.
    """
    if not is_cuda_available():
        logger.warning("CUDA not available — TensorRT export requires NVIDIA GPU")
        return None

    if not is_tensorrt_available():
        logger.warning(
            "TensorRT not installed. Install with: pip install tensorrt\n"
            "Also requires NVIDIA CUDA Toolkit and cuDNN."
        )
        return None

    engine_path = get_engine_path(model_path, half)
    if os.path.isfile(engine_path):
        logger.info("TensorRT engine already exists: %s", engine_path)
        return engine_path

    try:
        from ultralytics import YOLO

        logger.info(
            "Exporting %s to TensorRT (%s, imgsz=%d)...",
            model_path, "FP16" if half else "FP32", imgsz,
        )
        model = YOLO(model_path)
        model.export(
            format="engine",
            half=half,
            imgsz=imgsz,
            batch=batch,
            workspace=workspace,
        )
        logger.info("TensorRT export complete: %s", engine_path)
        return engine_path

    except Exception as e:
        logger.error("TensorRT export failed: %s", e)
        return None


def auto_select_model(preferred: str = "yolo11x.pt", half: bool = True) -> str:
    """Auto-select the best available model format.

    Prefers TensorRT engine > original .pt model.

    Returns the model path to use.
    """
    engine_path = get_engine_path(preferred, half)

    if os.path.isfile(engine_path):
        logger.info("Using TensorRT engine: %s", engine_path)
        return engine_path

    if is_tensorrt_available() and is_cuda_available():
        logger.info("TensorRT available — consider exporting with export_to_tensorrt()")

    return preferred
