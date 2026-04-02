"""Austroads vehicle classification mapping from YOLO COCO classes."""

# COCO class IDs for vehicles
COCO_BICYCLE = 1
COCO_CAR = 2
COCO_MOTORCYCLE = 3
COCO_BUS = 5
COCO_TRUCK = 7

# Austroads classification scheme
AUSTROADS_CLASSES = {
    "1": {"code": "SV", "name": "Short Vehicle", "description": "Cars, SUVs, utes, light vans"},
    "1M": {"code": "SV-M", "name": "Motorcycle", "description": "Motorcycles"},
    "2": {"code": "SVT", "name": "Short Vehicle Towing", "description": "Cars towing trailers, caravans"},
    "3": {"code": "TB2", "name": "Two-Axle Truck/Bus", "description": "2-axle rigid trucks, minibuses"},
    "4": {"code": "TB3", "name": "Three-Axle Truck/Bus", "description": "3-axle trucks, articulated buses, coaches"},
    "5": {"code": "T4", "name": "Four-Axle Truck", "description": "Heavy rigid trucks"},
    "6": {"code": "ART3", "name": "Three-Axle Articulated", "description": "Light semi-trailers"},
    "7": {"code": "ART4", "name": "Four-Axle Articulated", "description": "Standard semi-trailers"},
    "8": {"code": "ART5", "name": "Five-Axle Articulated", "description": "Common semi-trailer (tri-axle)"},
    "9": {"code": "ART6", "name": "Six+ Axle Articulated", "description": "Heavy semi-trailers"},
    "10": {"code": "BD", "name": "B-Double", "description": "B-double combinations"},
    "11": {"code": "DRT", "name": "Double Road Train", "description": "Double road trains"},
    "12": {"code": "TRT", "name": "Triple Road Train", "description": "Triple road trains"},
    "AT": {"code": "AT", "name": "Active Transport", "description": "Bicycles, pedestrians, e-scooters"},
}

# Simplified grouping that YOLO can reliably distinguish
# Maps COCO class_id to a simplified Austroads group
YOLO_TO_AUSTROADS_SIMPLE = {
    COCO_CAR: "1",          # Short Vehicle
    COCO_MOTORCYCLE: "1M",  # Motorcycle (sub-type of Class 1)
    COCO_BUS: "3",          # Two-Axle Truck/Bus (default)
    COCO_TRUCK: "3",        # Two-Axle Truck (default, refined by length)
    COCO_BICYCLE: "AT",     # Active Transport
}

# Length-based truck sub-classification thresholds (in pixels, relative to frame)
# These are approximate and depend on camera calibration
TRUCK_LENGTH_THRESHOLDS = {
    "3": 0.10,   # < 10% of frame width → small truck (Class 3)
    "5": 0.15,   # 10-15% → medium truck (Class 5)
    "8": 0.25,   # 15-25% → semi-trailer (Class 8)
    "10": 0.35,  # 25-35% → B-double (Class 10)
    "12": 1.0,   # > 35% → road train (Class 11/12)
}


class AustroadsClassifier:
    """Maps YOLO detections to Austroads vehicle classes.

    Uses multi-feature classification: aspect ratio, area ratio,
    and relative width for more accurate heavy vehicle classification.
    """

    def __init__(self):
        self.class_mapping = YOLO_TO_AUSTROADS_SIMPLE.copy()

    def classify(
        self, class_id: int, bbox_width: int = 0, bbox_height: int = 0,
        frame_width: int = 1, frame_height: int = 1,
    ) -> str:
        """Classify a YOLO detection into an Austroads class.

        Args:
            class_id: COCO class ID from YOLO.
            bbox_width: Width of the detection bounding box in pixels.
            bbox_height: Height of the detection bounding box in pixels.
            frame_width: Width of the video frame in pixels.
            frame_height: Height of the video frame in pixels.

        Returns:
            Austroads class key (e.g., "1", "3", "8", "AT").
        """
        base_class = self.class_mapping.get(class_id)
        if base_class is None:
            return "1"

        if class_id == COCO_TRUCK and frame_width > 0 and bbox_height > 0:
            return self._classify_truck(bbox_width, bbox_height, frame_width, frame_height)

        if class_id == COCO_BUS and frame_width > 0 and bbox_height > 0:
            return self._classify_bus(bbox_width, bbox_height, frame_width, frame_height)

        return base_class

    def _classify_truck(self, w, h, fw, fh):
        """Score-based truck sub-classification using aspect ratio, area ratio, and relative width."""
        aspect = w / max(h, 1)
        area_ratio = (w * h) / max(fw * fh, 1)
        rel_width = w / max(fw, 1)

        # Score-based: higher = larger vehicle
        score = 0.0
        score += aspect * 1.5      # Wide vehicles score higher
        score += area_ratio * 40   # Large area scores higher
        score += rel_width * 8     # Wide relative to frame scores higher

        if score >= 12.0:
            return "10"  # B-double / road train
        elif score >= 8.0:
            return "8"   # Semi-trailer (5-axle)
        elif score >= 5.5:
            return "7"   # 4-axle articulated
        elif score >= 4.0:
            return "5"   # Heavy rigid (4-axle)
        elif score >= 2.5:
            return "4"   # 3-axle truck
        else:
            return "3"   # Light truck (2-axle)

    def _classify_bus(self, w, h, fw, fh):
        """Bus sub-classification using area ratio."""
        area_ratio = (w * h) / max(fw * fh, 1)
        if area_ratio >= 0.04:
            return "4"  # Large bus / coach
        return "3"  # Minibus / 2-axle

    def get_class_name(self, austroads_key: str) -> str:
        """Get the display name for an Austroads class key."""
        info = AUSTROADS_CLASSES.get(austroads_key)
        if info:
            return f"Class {austroads_key} - {info['name']}"
        return f"Class {austroads_key}"

    def get_class_short_name(self, austroads_key: str) -> str:
        """Get the short code for an Austroads class key."""
        info = AUSTROADS_CLASSES.get(austroads_key)
        return info["code"] if info else austroads_key

    @staticmethod
    def get_all_classes() -> dict:
        """Return all Austroads classes for UI display."""
        return AUSTROADS_CLASSES
