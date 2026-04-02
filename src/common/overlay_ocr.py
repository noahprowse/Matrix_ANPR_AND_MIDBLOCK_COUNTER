"""Extract burned-in text overlays (camera number, timestamp) from CCTV video frames.

Reads the bottom-left corner for camera number and the top-right corner
for timestamp/date. Uses PaddleOCR (lazy-loaded singleton) for text recognition.
"""

import logging
import re
import threading

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---- Crop region constants (proportion of frame) ----
CAM_CROP_TOP = 0.85
CAM_CROP_RIGHT = 0.30
TIME_CROP_BOTTOM = 0.12
TIME_CROP_LEFT = 0.60
MIN_CROP_HEIGHT = 60


class OverlayOCR:
    """Extracts camera number and timestamp from CCTV frame overlays.

    Uses a class-level singleton for the PaddleOCR engine so the heavy
    model load only happens once across all instances.
    """

    _ocr_instance = None
    _ocr_lock = threading.Lock()

    def __init__(self):
        pass

    @classmethod
    def _get_ocr(cls):
        """Lazy-load PaddleOCR as a thread-safe singleton."""
        if cls._ocr_instance is None:
            with cls._ocr_lock:
                if cls._ocr_instance is None:
                    logger.info("Loading PaddleOCR engine (first use)...")
                    from paddleocr import PaddleOCR

                    cls._ocr_instance = PaddleOCR(
                        use_angle_cls=True,
                        lang="en",
                        show_log=False,
                        use_gpu=False,
                    )
                    logger.info("PaddleOCR engine ready.")
        return cls._ocr_instance

    def detect_from_frame(self, frame: np.ndarray) -> dict:
        """Read camera number and timestamp from a video frame.

        Args:
            frame: BGR numpy array (first frame of video).

        Returns:
            Dict with keys: camera_number, timestamp, raw_camera_text,
            raw_time_text. Values are None if detection fails.
        """
        ocr = self._get_ocr()
        h, w = frame.shape[:2]

        result = {
            "camera_number": None,
            "timestamp": None,
            "raw_camera_text": "",
            "raw_time_text": "",
        }

        # Bottom-left region for camera number
        cam_crop = frame[int(h * CAM_CROP_TOP):h, 0:int(w * CAM_CROP_RIGHT)]
        cam_text = self._read_region(ocr, cam_crop)
        result["raw_camera_text"] = cam_text
        if cam_text:
            result["camera_number"] = self._parse_camera_number(cam_text)

        # Top-right region for timestamp
        time_crop = frame[0:int(h * TIME_CROP_BOTTOM), int(w * TIME_CROP_LEFT):w]
        time_text = self._read_region(ocr, time_crop)
        result["raw_time_text"] = time_text
        if time_text:
            result["timestamp"] = self._parse_timestamp(time_text)

        logger.info(
            "Overlay OCR: camera=%r, timestamp=%r",
            result["camera_number"],
            result["timestamp"],
        )
        return result

    @staticmethod
    def _read_region(ocr, crop: np.ndarray) -> str:
        """Run OCR on a cropped region and return combined text."""
        if crop.size == 0:
            return ""

        preprocessed = OverlayOCR._preprocess(crop)

        try:
            results = ocr.ocr(preprocessed, cls=True)
        except Exception as e:
            logger.warning("OCR failed on region: %s", e)
            return ""

        if not results or not results[0]:
            return ""

        texts = [line[1][0] for line in results[0]]
        return " ".join(texts).strip()

    @staticmethod
    def _preprocess(crop: np.ndarray) -> np.ndarray:
        """Enhance overlay text for OCR."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop

        h, w = gray.shape[:2]
        if h < MIN_CROP_HEIGHT:
            scale = MIN_CROP_HEIGHT / h
            gray = cv2.resize(
                gray,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)
        binary = cv2.adaptiveThreshold(
            filtered, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2,
        )
        return binary

    @staticmethod
    def _parse_camera_number(text: str) -> str | None:
        """Extract camera identifier from OCR text."""
        upper = text.upper().strip()
        patterns = [
            r"CAM(?:ERA)?\.?\s*[:#]?\s*(\d+)",
            r"CH\.?\s*[:#]?\s*(\d+)",
            r"CHANNEL\s*[:#]?\s*(\d+)",
            r"\b(\d{1,4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, upper)
            if match:
                return match.group(1).lstrip("0") or "0"
        return None

    @staticmethod
    def _parse_timestamp(text: str) -> str | None:
        """Extract HH:MM or HH:MM:SS timestamp from OCR text."""
        patterns = [
            r"(\d{1,2}):(\d{2}):(\d{2})",
            r"(\d{1,2}):(\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    h, m, s = int(groups[0]), int(groups[1]), int(groups[2])
                    if 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59:
                        return f"{h:02d}:{m:02d}:{s:02d}"
                else:
                    h, m = int(groups[0]), int(groups[1])
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        return f"{h:02d}:{m:02d}:00"
        return None
