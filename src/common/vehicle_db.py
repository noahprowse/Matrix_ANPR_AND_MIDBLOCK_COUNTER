"""
Local SQLite database for storing plate detections, rego lookup cache,
and vehicle classification data.
"""

import logging
import os
import sqlite3
from datetime import datetime

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plate_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_text TEXT NOT NULL,
    confidence REAL,
    direction TEXT DEFAULT '',
    timestamp TEXT,
    video_file TEXT,
    valid_format INTEGER DEFAULT 0,
    claude_validated INTEGER DEFAULT 0,
    job_number TEXT DEFAULT '',
    site_id TEXT DEFAULT '',
    image_path TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plate_text ON plate_detections(plate_text);

CREATE TABLE IF NOT EXISTS rego_cache (
    plate_text TEXT PRIMARY KEY,
    state TEXT DEFAULT '',
    status TEXT DEFAULT '',
    expiry_date TEXT DEFAULT '',
    make TEXT DEFAULT '',
    model TEXT DEFAULT '',
    body_type TEXT DEFAULT '',
    raw_response TEXT DEFAULT '',
    lookup_source TEXT DEFAULT '',
    looked_up_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vehicle_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    austroads_class TEXT,
    confidence REAL,
    direction TEXT DEFAULT '',
    speed_kmh REAL DEFAULT 0,
    job_number TEXT DEFAULT '',
    site_id TEXT DEFAULT '',
    image_path TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


class VehicleDatabase:
    """Local SQLite database for plate detections and vehicle data."""

    def __init__(self, db_path: str = "vehicle_data.db"):
        """Initialize database at the given path. Creates tables if needed."""
        self.db_path = db_path
        try:
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(_SCHEMA_SQL)
            self.conn.commit()
            logger.info("VehicleDatabase initialised at %s", db_path)
        except Exception:
            logger.exception("Failed to initialise VehicleDatabase at %s", db_path)
            raise

    # ------------------------------------------------------------------
    # Plate detections
    # ------------------------------------------------------------------

    def save_plate_detection(
        self,
        plate_text: str,
        confidence: float,
        direction: str,
        timestamp: str,
        video_file: str,
        valid_format: int,
        claude_validated: int,
        job_number: str,
        site_id: str,
        image_path: str = "",
    ) -> int | None:
        """Save a plate detection. Returns the row ID."""
        try:
            cur = self.conn.execute(
                """
                INSERT INTO plate_detections
                    (plate_text, confidence, direction, timestamp, video_file,
                     valid_format, claude_validated, job_number, site_id, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plate_text,
                    confidence,
                    direction,
                    timestamp,
                    video_file,
                    valid_format,
                    claude_validated,
                    job_number,
                    site_id,
                    image_path,
                ),
            )
            self.conn.commit()
            return cur.lastrowid
        except Exception:
            logger.exception("Failed to save plate detection for %s", plate_text)
            return None

    def save_plate_image(
        self, plate_text: str, plate_img: np.ndarray, storage_dir: str
    ) -> str:
        """Save plate crop image to disk. Returns the file path.

        Directory structure: ``storage_dir/plates/YYYY-MM-DD/``
        Filename: ``{plate_text}_{HH-MM-SS}_{timestamp}.jpg``
        """
        try:
            now = datetime.now()
            date_dir = os.path.join(storage_dir, "plates", now.strftime("%Y-%m-%d"))
            os.makedirs(date_dir, exist_ok=True)

            filename = f"{plate_text}_{now.strftime('%H-%M-%S')}_{now.strftime('%f')}.jpg"
            filepath = os.path.join(date_dir, filename)

            success, buf = cv2.imencode(".jpg", plate_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                logger.error("cv2.imencode failed for plate %s", plate_text)
                return ""
            with open(filepath, "wb") as f:
                f.write(buf.tobytes())
            return filepath
        except Exception:
            logger.exception("Failed to save plate image for %s", plate_text)
            return ""

    def lookup_plate(self, plate_text: str) -> dict | None:
        """Look up a plate in the local database.

        Returns a dict with the most recent detection info merged with
        any cached rego data, or ``None`` if the plate has never been seen.
        """
        try:
            row = self.conn.execute(
                """
                SELECT * FROM plate_detections
                WHERE plate_text = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (plate_text,),
            ).fetchone()
            if row is None:
                return None

            result = dict(row)

            rego = self.get_rego_cache(plate_text)
            if rego:
                result.update(rego)
            return result
        except Exception:
            logger.exception("Failed to lookup plate %s", plate_text)
            return None

    def get_plate_history(self, plate_text: str) -> list[dict]:
        """Get all detection records for a specific plate."""
        try:
            rows = self.conn.execute(
                """
                SELECT * FROM plate_detections
                WHERE plate_text = ?
                ORDER BY created_at DESC
                """,
                (plate_text,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("Failed to get plate history for %s", plate_text)
            return []

    # ------------------------------------------------------------------
    # Rego cache
    # ------------------------------------------------------------------

    def get_rego_cache(self, plate_text: str) -> dict | None:
        """Check if we have a cached rego lookup result."""
        try:
            row = self.conn.execute(
                "SELECT * FROM rego_cache WHERE plate_text = ?",
                (plate_text,),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            logger.exception("Failed to get rego cache for %s", plate_text)
            return None

    def save_rego_result(
        self,
        plate_text: str,
        state: str,
        status: str,
        expiry_date: str,
        make: str,
        model: str,
        body_type: str,
        raw_response: str,
        source: str,
    ):
        """Cache a rego lookup result (upsert)."""
        try:
            self.conn.execute(
                """
                INSERT INTO rego_cache
                    (plate_text, state, status, expiry_date, make, model,
                     body_type, raw_response, lookup_source, looked_up_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(plate_text) DO UPDATE SET
                    state = excluded.state,
                    status = excluded.status,
                    expiry_date = excluded.expiry_date,
                    make = excluded.make,
                    model = excluded.model,
                    body_type = excluded.body_type,
                    raw_response = excluded.raw_response,
                    lookup_source = excluded.lookup_source,
                    looked_up_at = excluded.looked_up_at
                """,
                (plate_text, state, status, expiry_date, make, model, body_type, raw_response, source),
            )
            self.conn.commit()
        except Exception:
            logger.exception("Failed to save rego result for %s", plate_text)

    # ------------------------------------------------------------------
    # Vehicle classifications
    # ------------------------------------------------------------------

    def save_vehicle_classification(
        self,
        track_id: int,
        austroads_class: str,
        confidence: float,
        direction: str,
        speed_kmh: float,
        job_number: str,
        site_id: str,
        image_path: str = "",
    ) -> int | None:
        """Save a vehicle classification from the counter module."""
        try:
            cur = self.conn.execute(
                """
                INSERT INTO vehicle_classifications
                    (track_id, austroads_class, confidence, direction,
                     speed_kmh, job_number, site_id, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (track_id, austroads_class, confidence, direction, speed_kmh, job_number, site_id, image_path),
            )
            self.conn.commit()
            return cur.lastrowid
        except Exception:
            logger.exception("Failed to save vehicle classification for track %s", track_id)
            return None

    def save_vehicle_image(
        self, track_id: int, vehicle_img: np.ndarray, storage_dir: str
    ) -> str:
        """Save vehicle crop image to disk. Returns the file path."""
        try:
            now = datetime.now()
            date_dir = os.path.join(storage_dir, "vehicles", now.strftime("%Y-%m-%d"))
            os.makedirs(date_dir, exist_ok=True)

            filename = f"track_{track_id}_{now.strftime('%H-%M-%S_%f')}.jpg"
            filepath = os.path.join(date_dir, filename)

            success, buf = cv2.imencode(".jpg", vehicle_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                logger.error("cv2.imencode failed for track %s", track_id)
                return ""
            with open(filepath, "wb") as f:
                f.write(buf.tobytes())
            return filepath
        except Exception:
            logger.exception("Failed to save vehicle image for track %s", track_id)
            return ""

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return database statistics."""
        stats: dict = {}
        try:
            stats["total_plates"] = self.conn.execute(
                "SELECT COUNT(*) FROM plate_detections"
            ).fetchone()[0]
            stats["unique_plates"] = self.conn.execute(
                "SELECT COUNT(DISTINCT plate_text) FROM plate_detections"
            ).fetchone()[0]
            stats["total_vehicles"] = self.conn.execute(
                "SELECT COUNT(*) FROM vehicle_classifications"
            ).fetchone()[0]
            stats["rego_cached"] = self.conn.execute(
                "SELECT COUNT(*) FROM rego_cache"
            ).fetchone()[0]
            stats["valid_format_plates"] = self.conn.execute(
                "SELECT COUNT(*) FROM plate_detections WHERE valid_format = 1"
            ).fetchone()[0]
            stats["claude_validated_plates"] = self.conn.execute(
                "SELECT COUNT(*) FROM plate_detections WHERE claude_validated = 1"
            ).fetchone()[0]
        except Exception:
            logger.exception("Failed to get database stats")
        return stats

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close the database connection."""
        try:
            if self.conn:
                self.conn.close()
                logger.info("VehicleDatabase closed")
        except Exception:
            logger.exception("Error closing VehicleDatabase")
