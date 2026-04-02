"""PaddleOCR-based license plate text recognition with preprocessing.

Uses the OverlayOCR singleton PaddleOCR engine to avoid loading
the model multiple times.
"""

import re
import cv2
import numpy as np

# Australian plate patterns by state (common formats)
AU_PLATE_PATTERNS = [
    r"^[A-Z]{2,3}\d{2,4}[A-Z]{0,3}$",  # NSW: ABC12D, AB1234
    r"^\d{3}[A-Z]{3}$",                  # QLD: 123ABC
    r"^[A-Z]{3}\d{3}$",                  # VIC: ABC123
    r"^\d[A-Z]{2}\d{1,2}[A-Z]{2}$",     # VIC newer: 1AB2CD
    r"^S\d{3}[A-Z]{3}$",                 # SA: S123ABC
    r"^[A-Z]{1,3}\d{1,4}$",             # General short
    r"^\d{1,4}[A-Z]{1,3}$",             # General reversed
]

MIN_PLATE_HEIGHT = 100  # Scale crops below this height


class PlateOCR:
    """Reads text from cropped license plate images.

    Shares the PaddleOCR engine singleton from OverlayOCR.
    """

    def __init__(self):
        self._ocr = None

    def _load_ocr(self):
        if self._ocr is None:
            from src.common.overlay_ocr import OverlayOCR

            self._ocr = OverlayOCR._get_ocr()

    def preprocess(self, plate_img: np.ndarray) -> np.ndarray:
        """Preprocess a cropped plate image for better OCR accuracy."""
        if plate_img.size == 0:
            return plate_img

        # Resize to minimum height for OCR
        h, w = plate_img.shape[:2]
        if h < MIN_PLATE_HEIGHT:
            scale = MIN_PLATE_HEIGHT / h
            plate_img = cv2.resize(
                plate_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

        # Convert to grayscale
        gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY) if len(plate_img.shape) == 3 else plate_img

        # CLAHE contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Bilateral filter to reduce noise while keeping edges
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)

        # Adaptive thresholding
        binary = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        return binary

    def read(self, plate_img: np.ndarray) -> tuple[str, float]:
        """Read text from a cropped plate image.

        Returns (plate_text, confidence). Returns ("", 0.0) if nothing readable.
        """
        self._load_ocr()

        if plate_img.size == 0:
            return "", 0.0

        preprocessed = self.preprocess(plate_img)

        try:
            results = self._ocr.ocr(preprocessed, cls=True)
        except Exception:
            return "", 0.0

        if not results or not results[0]:
            return "", 0.0

        # Concatenate all detected text segments
        texts = []
        confidences = []
        for line in results[0]:
            text = line[1][0]
            conf = line[1][1]
            texts.append(text)
            confidences.append(conf)

        raw_text = " ".join(texts).strip()
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Clean the text: keep only alphanumeric, remove spaces
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()

        return cleaned, avg_confidence

    def validate_plate(self, plate_text: str) -> bool:
        """Check if the text matches known Australian plate formats."""
        if not plate_text or len(plate_text) < 3 or len(plate_text) > 8:
            return False
        return any(re.match(p, plate_text) for p in AU_PLATE_PATTERNS)
