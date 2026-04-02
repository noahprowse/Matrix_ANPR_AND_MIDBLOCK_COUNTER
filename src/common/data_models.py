"""Core data models for the Matrix Traffic Data Extraction application.

Dataclasses that flow through the entire pipeline — from the job details
form, through folder scanning, into the processing engine, and out to
the reporting layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Austroads vehicle classification definitions ──

AUSTROADS_CLASSES: dict[str, dict] = {
    "PED":  {"code": "PED",  "name": "Pedestrian",             "group": "Active Transport",  "description": "Pedestrians, wheelchair users, mobility aids"},
    "CYC":  {"code": "CYC",  "name": "Cyclist",                "group": "Active Transport",  "description": "Bicycles, e-bikes, e-scooters"},
    "1":    {"code": "1",    "name": "Short Vehicle",           "group": "Light",             "description": "Car, sedan, wagon, SUV, ute, light van (<5.5m)"},
    "1M":   {"code": "1M",   "name": "Motorcycle",             "group": "Light",             "description": "Motorcycle, moped"},
    "2":    {"code": "2",    "name": "Short Towing",            "group": "Light",             "description": "Car/van towing trailer, caravan, or boat"},
    "3":    {"code": "3",    "name": "Two-Axle Truck/Bus",     "group": "Rigid",             "description": "2-axle rigid truck or bus (>5.5m)"},
    "4":    {"code": "4",    "name": "Three-Axle Truck/Bus",   "group": "Rigid",             "description": "3-axle rigid truck or bus"},
    "5":    {"code": "5",    "name": "Four-Axle Truck",        "group": "Rigid",             "description": "4-axle rigid truck"},
    "6":    {"code": "6",    "name": "Three-Axle Articulated", "group": "Articulated",       "description": "3-axle articulated vehicle"},
    "7":    {"code": "7",    "name": "Four-Axle Articulated",  "group": "Articulated",       "description": "4-axle articulated vehicle"},
    "8":    {"code": "8",    "name": "Five-Axle Articulated",  "group": "Articulated",       "description": "5-axle articulated (semi-trailer)"},
    "9":    {"code": "9",    "name": "Six-Axle Articulated",   "group": "Articulated",       "description": "6+ axle articulated vehicle"},
    "10":   {"code": "10",   "name": "B-Double",               "group": "Multi-Combination", "description": "B-Double / heavy truck and trailer"},
    "11":   {"code": "11",   "name": "Double Road Train",      "group": "Multi-Combination", "description": "Double road train"},
    "12":   {"code": "12",   "name": "Triple Road Train",      "group": "Multi-Combination", "description": "Triple road train"},
}

# ── Classification presets ──

CLASSIFICATION_PRESETS: dict[str, list[str]] = {
    "Simple 3-Class": ["1", "3", "CYC"],
    "Lights & Heavies + Active": ["1", "1M", "3", "CYC", "PED"],
    "Standard 7-Class": ["1", "1M", "3", "5", "8", "10", "CYC", "PED"],
    "Full 13-Bin": ["1", "1M", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
    "Full 13-Bin + Active": ["PED", "CYC", "1", "1M", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
}

# Mapping from simple group names to Austroads codes (used for simple presets)
SIMPLE_GROUP_MAP = {
    "Lights":  ["1", "1M", "2"],
    "Heavies": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
    "Active":  ["PED", "CYC"],
}

# ── COCO class → Austroads mapping for YOLO detections ──

COCO_TO_AUSTROADS: dict[int, str] = {
    0: "PED",     # person
    1: "CYC",     # bicycle
    2: "1",       # car
    3: "1M",      # motorcycle
    5: "3",       # bus (default 2-axle, refined by size)
    7: "3",       # truck (default 2-axle, refined by size)
}


@dataclass
class ClassificationConfig:
    """Defines which Austroads bins are active for a job."""

    preset_name: str = "Lights & Heavies + Active"
    active_bins: list[str] = field(default_factory=lambda: ["1", "1M", "3", "CYC", "PED"])
    include_pedestrians: bool = True
    include_cyclists: bool = True

    @classmethod
    def from_preset(cls, preset_name: str) -> ClassificationConfig:
        """Create from a named preset."""
        bins = CLASSIFICATION_PRESETS.get(preset_name, CLASSIFICATION_PRESETS["Lights & Heavies + Active"])
        return cls(
            preset_name=preset_name,
            active_bins=list(bins),
            include_pedestrians="PED" in bins,
            include_cyclists="CYC" in bins,
        )

    def is_class_active(self, austroads_code: str) -> bool:
        """Check if a given Austroads class is active in this config."""
        return austroads_code in self.active_bins

    def get_active_class_names(self) -> list[str]:
        """Return human-readable names for active classes."""
        return [
            AUSTROADS_CLASSES[code]["name"]
            for code in self.active_bins
            if code in AUSTROADS_CLASSES
        ]


@dataclass
class SiteConfig:
    """Per-site configuration within a job."""

    site_number: str = ""
    site_name: str = ""
    direction: str = ""
    date_folders: list[str] = field(default_factory=list)
    video_paths: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Human-readable site label."""
        parts = []
        if self.site_number:
            parts.append(self.site_number)
        if self.site_name:
            parts.append(self.site_name)
        if self.direction:
            parts.append(self.direction)
        return " ".join(parts) if parts else "Unnamed Site"

    @property
    def total_videos(self) -> int:
        return len(self.video_paths)


@dataclass
class JobConfig:
    """Complete job configuration passed through the wizard.

    Created in Step 1 (Job Details), enriched in Step 2 (Folder Upload),
    consumed in Step 3 (Processing).
    """

    # Identity
    job_number: str = ""
    job_name: str = ""
    module_type: str = ""  # "anpr" | "midblock" | "intersection"

    # Survey period
    survey_start_date: str = ""  # ISO format: YYYY-MM-DD
    survey_end_date: str = ""    # ISO format or same as start for single day
    survey_start_time: str = ""  # HH:MM
    survey_end_time: str = ""    # HH:MM
    survey_time_periods: list[tuple[str, str]] = field(default_factory=list)  # [(HH:MM, HH:MM), ...]

    # Classification
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)

    # Sites (populated by folder scanner)
    sites: list[SiteConfig] = field(default_factory=list)

    # Processing settings
    concurrency: int = 4
    gpu_limit: int = 4

    # Job folder path
    job_folder_path: str = ""

    @property
    def display_title(self) -> str:
        """Job display label for reports and UI headers."""
        if self.job_number and self.job_name:
            return f"{self.job_number} - {self.job_name}"
        return self.job_number or self.job_name or "Untitled Job"

    @property
    def total_videos(self) -> int:
        return sum(site.total_videos for site in self.sites)

    @property
    def all_video_paths(self) -> list[str]:
        """Flat list of all video paths across all sites."""
        paths = []
        for site in self.sites:
            paths.extend(site.video_paths)
        return paths

    @property
    def is_date_range(self) -> bool:
        return bool(self.survey_end_date) and self.survey_end_date != self.survey_start_date

    @property
    def date_display(self) -> str:
        if self.is_date_range:
            return f"{self.survey_start_date} to {self.survey_end_date}"
        return self.survey_start_date

    @property
    def time_display(self) -> str:
        if self.survey_start_time and self.survey_end_time:
            return f"{self.survey_start_time} - {self.survey_end_time}"
        return ""


@dataclass
class NamedZone:
    """A polygon zone with a name and type (for intersection counting)."""

    name: str = ""
    zone_type: str = "entry"  # "entry" | "exit" | "approach"
    polygon: list[tuple[int, int]] = field(default_factory=list)
    color_bgr: tuple[int, int, int] = (0, 255, 0)  # Default green
    approach: str = ""  # Compass direction: "N", "S", "E", "W", etc.


@dataclass
class VehicleReading:
    """A single OCR reading of a plate for one track-frame."""

    plate_text: str = ""
    confidence: float = 0.0       # 0-100
    is_valid_format: bool = False
    frame_num: int = 0
    real_time: str = ""           # from overlay OCR, e.g. "14:32:07"
    video_file: str = ""
    plate_crop_path: str = ""     # path to saved plate JPEG
    source: str = "paddle"        # "paddle" | "claude" | "user"


@dataclass
class VehicleRecord:
    """One unique vehicle (grouped by track_id within a video)."""

    vehicle_id: str = ""          # globally unique e.g. "v001"
    track_id: int = 0             # ByteTrack ID (per-video)
    video_file: str = ""
    direction: str = ""
    vehicle_crop_path: str = ""   # path to best vehicle crop JPEG
    readings: list[VehicleReading] = field(default_factory=list)
    best_reading_idx: int = 0
    user_corrected_plate: Optional[str] = None
    flagged_for_review: bool = False

    @property
    def best_reading(self) -> VehicleReading:
        if self.readings:
            return self.readings[self.best_reading_idx]
        return VehicleReading()

    @property
    def plate_text(self) -> str:
        if self.user_corrected_plate:
            return self.user_corrected_plate
        return self.best_reading.plate_text

    @property
    def confidence(self) -> float:
        return self.best_reading.confidence


@dataclass
class ProcessingResult:
    """Container for results from a single video stream."""

    stream_id: int = 0
    site_name: str = ""
    video_path: str = ""
    total_frames: int = 0
    processed_frames: int = 0
    detections: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class VideoChunk:
    """A frame-range slice of a single video file.

    Used to split one long video across multiple workers.  Each chunk
    shares the same file path but covers a different frame range.
    ``overlap_frames`` is the number of extra frames at the *start* of
    this chunk that overlap with the previous chunk (used for dedup).
    """

    video_path: str = ""
    start_frame: int = 0
    end_frame: int = 0          # exclusive — 0 means "to end of file"
    overlap_frames: int = 0     # frames of overlap from previous chunk
    chunk_index: int = 0        # 0-based index within the split
    total_chunks: int = 1       # how many chunks this video was split into


@dataclass
class VideoAssignment:
    """Assignment of video files to a processing stream."""

    stream_id: int = 0
    site: Optional[SiteConfig] = None
    video_paths: list[str] = field(default_factory=list)
    use_gpu: bool = False
    preview_enabled: bool = False
    chunks: list[VideoChunk] = field(default_factory=list)
