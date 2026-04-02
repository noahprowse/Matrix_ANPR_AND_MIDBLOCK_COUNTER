"""Two-stage vehicle → plate detection using YOLO.

Stage 1: Detect vehicles (car, motorcycle, bus, truck) using YOLO COCO model.
Stage 2: Extract the plate region from each vehicle detection by cropping the
         lower portion of the bounding box where plates are typically located.
"""

import numpy as np

# COCO class IDs that represent vehicles
VEHICLE_CLASS_IDS = {2, 3, 5, 7}  # car, motorcycle, bus, truck

# Plate region: crop the bottom portion of each vehicle detection
PLATE_CROP_TOP = 0.50    # start from 50% down the vehicle bbox
PLATE_CROP_BOTTOM = 1.0  # to the bottom
PLATE_CROP_LEFT = 0.10   # 10% inset from left
PLATE_CROP_RIGHT = 0.90  # 10% inset from right


class PlateDetector:
    """Detects vehicles and extracts likely plate regions."""

    def __init__(self, model_path: str = "yolo11x.pt", confidence: float = 0.4):
        self.confidence = confidence
        self._model = None
        self._model_path = model_path

    def _load_model(self):
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Detect vehicles in a frame.

        Returns list of dicts with keys: bbox, confidence, class_id.
        bbox is (x1, y1, x2, y2) in pixel coordinates.
        """
        self._load_model()
        results = self._model(
            frame,
            classes=list(VEHICLE_CLASS_IDS),
            conf=self.confidence,
            verbose=False,
        )

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                detections.append(
                    {
                        "bbox": (int(x1), int(y1), int(x2), int(y2)),
                        "confidence": float(box.conf[0]),
                        "class_id": int(box.cls[0]),
                    }
                )
        return detections

    def crop_plate(self, frame: np.ndarray, bbox: tuple) -> np.ndarray:
        """Extract the likely plate region from a vehicle detection.

        Crops the lower-center portion of the vehicle bounding box
        where license plates are typically located.
        """
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]

        # Clamp to frame bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        box_h = y2 - y1
        box_w = x2 - x1

        # Crop the bottom portion of the vehicle for the plate
        plate_y1 = y1 + int(box_h * PLATE_CROP_TOP)
        plate_y2 = y1 + int(box_h * PLATE_CROP_BOTTOM)
        plate_x1 = x1 + int(box_w * PLATE_CROP_LEFT)
        plate_x2 = x1 + int(box_w * PLATE_CROP_RIGHT)

        # Clamp again
        plate_y1 = max(0, plate_y1)
        plate_y2 = min(h, plate_y2)
        plate_x1 = max(0, plate_x1)
        plate_x2 = min(w, plate_x2)

        crop = frame[plate_y1:plate_y2, plate_x1:plate_x2]

        # If crop is too small, fall back to full bbox
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 20:
            return frame[y1:y2, x1:x2]

        return crop
