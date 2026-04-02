"""Low-light video enhancement using ZeroDCE++ (Zero-Reference Deep Curve Estimation).

Preprocesses dark/night video frames to improve vehicle detection accuracy.
Uses a lightweight ONNX model (~80KB) that runs in real-time.
Falls back to CLAHE enhancement if ZeroDCE++ model is not available.
"""

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Brightness threshold — frames darker than this get enhanced
DARK_FRAME_THRESHOLD = 80  # mean pixel value (0-255)


class NightEnhancer:
    """Enhances dark/night video frames for better detection."""

    def __init__(self, model_path: str | None = None, auto_detect: bool = True):
        self.auto_detect = auto_detect
        self._model = None
        self._model_path = model_path
        self._use_clahe_fallback = True
        self._clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

        if model_path and os.path.isfile(model_path):
            self._load_model()

    def _load_model(self):
        """Load ZeroDCE++ ONNX model if available."""
        try:
            import onnxruntime as ort
            self._model = ort.InferenceSession(
                self._model_path,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self._use_clahe_fallback = False
            logger.info("ZeroDCE++ model loaded for night enhancement")
        except Exception as e:
            logger.warning("ZeroDCE++ unavailable, using CLAHE fallback: %s", e)
            self._use_clahe_fallback = True

    def is_dark_frame(self, frame: np.ndarray) -> bool:
        """Check if a frame is dark enough to need enhancement."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        return float(np.mean(gray)) < DARK_FRAME_THRESHOLD

    def enhance(self, frame: np.ndarray) -> np.ndarray:
        """Enhance a dark frame. Returns original if frame is bright enough."""
        if self.auto_detect and not self.is_dark_frame(frame):
            return frame

        if not self._use_clahe_fallback and self._model is not None:
            return self._enhance_zerodce(frame)
        return self._enhance_clahe(frame)

    def _enhance_zerodce(self, frame: np.ndarray) -> np.ndarray:
        """ZeroDCE++ enhancement."""
        try:
            h, w = frame.shape[:2]
            # Resize to model input (256x256)
            resized = cv2.resize(frame, (256, 256))
            inp = resized.astype(np.float32) / 255.0
            inp = np.transpose(inp, (2, 0, 1))[np.newaxis, ...]

            input_name = self._model.get_inputs()[0].name
            output = self._model.run(None, {input_name: inp})[0]

            enhanced = np.squeeze(output)
            enhanced = np.transpose(enhanced, (1, 2, 0))
            enhanced = np.clip(enhanced * 255, 0, 255).astype(np.uint8)
            enhanced = cv2.resize(enhanced, (w, h))
            return enhanced
        except Exception as e:
            logger.warning("ZeroDCE++ failed, using CLAHE: %s", e)
            return self._enhance_clahe(frame)

    def _enhance_clahe(self, frame: np.ndarray) -> np.ndarray:
        """CLAHE + gamma correction fallback for night enhancement."""
        # Convert to LAB and apply CLAHE to L channel
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self._clahe.apply(l)

        # Gamma correction for very dark frames
        mean_brightness = np.mean(l)
        if mean_brightness < 50:
            gamma = 0.4  # Strong brightening
        elif mean_brightness < 80:
            gamma = 0.6  # Moderate brightening
        else:
            gamma = 0.8  # Light brightening

        lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)]).astype(np.uint8)
        l = cv2.LUT(l, lut)

        lab = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # Gentle denoise to reduce noise amplified by enhancement
        enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 6, 6, 7, 21)

        return enhanced
