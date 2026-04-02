"""Azure Blob Storage integration for ANPR training data.

Uploads plate crop images, metadata, and CLIP embeddings to Azure Blob Storage
for building a training feedback loop to improve accuracy over time.
"""

import io
import json
import logging
from datetime import datetime

import cv2
import numpy as np

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
)
from PySide6.QtCore import Signal

from src.common.theme import TEXT_MUTED, TEXT_SECONDARY, SUCCESS, ACCENT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import for optional azure-storage-blob SDK
# ---------------------------------------------------------------------------
_azure_available = False
BlobServiceClient = None

try:
    from azure.storage.blob import BlobServiceClient as _BlobServiceClient

    BlobServiceClient = _BlobServiceClient
    _azure_available = True
except ImportError:
    pass


# ===========================================================================
# Storage backend
# ===========================================================================


class ANPRBlobStorage:
    """Manages upload of ANPR plate images and metadata to Azure Blob Storage."""

    CONFIDENCE_HIGH = 85.0
    CONFIDENCE_MEDIUM = 60.0

    def __init__(
        self,
        connection_string: str | None = None,
        account_url: str | None = None,
        sas_token: str | None = None,
        container_name: str = "anpr-data",
        site_id: str = "default-site",
    ):
        """Initialize blob storage connection.

        Supports two auth methods:
        1. Connection string (for development / internal use)
        2. Account URL + SAS token (recommended for desktop apps)
        """
        if not _azure_available:
            raise ImportError(
                "azure-storage-blob is not installed. "
                "Install it with:  pip install azure-storage-blob"
            )

        self._container_name = container_name
        self._site_id = site_id

        # Stats counters
        self._uploads_total = 0
        self._uploads_failed = 0
        self._bytes_uploaded = 0

        # Create the BlobServiceClient
        if connection_string:
            self._service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
        elif account_url:
            url = account_url
            if sas_token:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{sas_token}"
            self._service_client = BlobServiceClient(account_url=url)
        else:
            raise ValueError(
                "Provide either a connection_string or account_url (+ optional sas_token)."
            )

        # Obtain a container client (the container is created lazily on first upload)
        self._container_client = self._service_client.get_container_client(
            self._container_name
        )

    # ----- helpers ----------------------------------------------------------

    def _confidence_tier(self, confidence: float) -> str:
        """Categorize confidence into tiers for storage organization."""
        if confidence >= self.CONFIDENCE_HIGH:
            return "high_confidence"
        if confidence >= self.CONFIDENCE_MEDIUM:
            return "review_pending"
        return "low_confidence"

    def _ensure_container(self) -> None:
        """Create the container if it does not already exist."""
        try:
            self._container_client.get_container_properties()
        except Exception:
            try:
                self._container_client.create_container()
                logger.info("Created blob container '%s'", self._container_name)
            except Exception:
                # Container may have been created between the two calls
                pass

    # ----- public API -------------------------------------------------------

    def upload_plate_result(
        self,
        plate_img: np.ndarray,
        plate_text: str,
        confidence: float,
        timestamp_str: str,
        video_file: str,
        direction: str = "",
        valid_format: bool = False,
        claude_validated: bool = False,
    ) -> str | None:
        """Upload a plate crop + metadata to blob storage.

        Blob path structure:
          sites/{site_id}/{YYYY-MM-DD}/{tier}/{plate}_{HH-MM-SS}_{conf}.jpg
          sites/{site_id}/{YYYY-MM-DD}/{tier}/{plate}_{HH-MM-SS}_{conf}.json

        Returns the blob path (without extension) if successful, ``None``
        otherwise.
        """
        try:
            self._ensure_container()

            tier = self._confidence_tier(confidence)
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H-%M-%S")
            safe_plate = plate_text.replace(" ", "_").replace("/", "-")
            conf_int = int(round(confidence))

            base_path = (
                f"sites/{self._site_id}/{date_str}/{tier}/"
                f"{safe_plate}_{time_str}_{conf_int}"
            )

            # --- encode image as JPEG (quality 95) -------------------------
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
            ok, buf = cv2.imencode(".jpg", plate_img, encode_params)
            if not ok:
                logger.warning("Failed to JPEG-encode plate crop for %s", plate_text)
                self._uploads_failed += 1
                return None

            jpg_bytes = buf.tobytes()
            img_blob_path = f"{base_path}.jpg"

            self._container_client.upload_blob(
                name=img_blob_path,
                data=jpg_bytes,
                overwrite=True,
                content_settings={"content_type": "image/jpeg"},
            )

            # --- metadata JSON ---------------------------------------------
            metadata = {
                "plate_text": plate_text,
                "confidence": round(confidence, 2),
                "timestamp": timestamp_str,
                "video_file": video_file,
                "direction": direction,
                "valid_format": valid_format,
                "claude_validated": claude_validated,
                "captured_at": now.isoformat(),
                "site_id": self._site_id,
                "tier": tier,
            }

            json_bytes = json.dumps(metadata, indent=2).encode("utf-8")
            json_blob_path = f"{base_path}.json"

            self._container_client.upload_blob(
                name=json_blob_path,
                data=json_bytes,
                overwrite=True,
                content_settings={"content_type": "application/json"},
            )

            self._uploads_total += 1
            self._bytes_uploaded += len(jpg_bytes) + len(json_bytes)
            logger.debug("Uploaded plate result to %s", base_path)
            return base_path

        except Exception:
            self._uploads_failed += 1
            logger.exception("Failed to upload plate result for '%s'", plate_text)
            return None

    def is_connected(self) -> bool:
        """Check if blob storage is properly configured and accessible."""
        try:
            # A lightweight call that validates credentials and connectivity
            self._container_client.get_container_properties()
            return True
        except Exception:
            # Container may not exist yet -- try listing to check auth
            try:
                self._service_client.get_account_information()
                return True
            except Exception:
                return False

    def get_upload_stats(self) -> dict:
        """Return upload statistics."""
        return {
            "total": self._uploads_total,
            "failed": self._uploads_failed,
            "bytes": self._bytes_uploaded,
        }


# ===========================================================================
# Qt widget
# ===========================================================================


class BlobStorageWidget(QGroupBox):
    """Settings panel for Azure Blob Storage uploads."""

    connection_changed = Signal(bool)  # True if connected

    def __init__(self, parent=None):
        super().__init__("Cloud Upload (Azure Blob Storage)", parent)
        self._storage: ANPRBlobStorage | None = None
        self._build_ui()

    # ----- UI construction --------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # -- enable checkbox -------------------------------------------------
        self.enable_cb = QCheckBox("Enable cloud upload")
        self.enable_cb.setChecked(False)
        self.enable_cb.toggled.connect(self._on_enable_toggled)
        layout.addWidget(self.enable_cb)

        # -- connection string / SAS token -----------------------------------
        conn_lbl = QLabel("Connection string or SAS token:")
        conn_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(conn_lbl)

        self.connection_input = QLineEdit()
        self.connection_input.setPlaceholderText(
            "DefaultEndpointsProtocol=https;AccountName=...  or  https://account.blob.core.windows.net?sv=..."
        )
        self.connection_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.connection_input)

        # -- container name --------------------------------------------------
        container_lbl = QLabel("Container name:")
        container_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(container_lbl)

        self.container_input = QLineEdit()
        self.container_input.setPlaceholderText("anpr-data")
        self.container_input.setText("anpr-data")
        layout.addWidget(self.container_input)

        # -- test button + status indicator ----------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setFixedWidth(150)
        self.test_btn.clicked.connect(self._on_test_connection)
        btn_row.addWidget(self.test_btn)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        btn_row.addWidget(self.status_label)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # -- stats label -----------------------------------------------------
        self.stats_label = QLabel("Uploads: 0  |  Failed: 0  |  Bytes: 0")
        self.stats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.stats_label)

        # -- SDK availability warning ----------------------------------------
        if not _azure_available:
            warn = QLabel(
                "azure-storage-blob is not installed. "
                "Run:  pip install azure-storage-blob"
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")
            layout.addWidget(warn)
            self.enable_cb.setEnabled(False)
            self.test_btn.setEnabled(False)

        # Start with inputs disabled (upload not enabled)
        self._set_inputs_enabled(False)

    # ----- slots ------------------------------------------------------------

    def _on_enable_toggled(self, checked: bool) -> None:
        self._set_inputs_enabled(checked)
        if not checked:
            self._storage = None
            self._update_status(False)
            self.connection_changed.emit(False)

    def _on_test_connection(self) -> None:
        storage = self._create_storage()
        if storage is None:
            return
        connected = storage.is_connected()
        if connected:
            self._storage = storage
        self._update_status(connected)
        self.connection_changed.emit(connected)

    # ----- helpers ----------------------------------------------------------

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.connection_input.setEnabled(enabled)
        self.container_input.setEnabled(enabled)
        self.test_btn.setEnabled(enabled and _azure_available)

    def _create_storage(self) -> ANPRBlobStorage | None:
        """Build an ``ANPRBlobStorage`` from the current widget inputs."""
        raw = self.connection_input.text().strip()
        container = self.container_input.text().strip() or "anpr-data"

        if not raw:
            self.status_label.setText("Please enter a connection string or SAS URL")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
            return None

        try:
            # Heuristic: if the value starts with "http" it is an account URL
            # (possibly with an inline SAS token).  Otherwise treat it as a
            # connection string.
            if raw.lower().startswith("http"):
                return ANPRBlobStorage(
                    account_url=raw,
                    container_name=container,
                )
            else:
                return ANPRBlobStorage(
                    connection_string=raw,
                    container_name=container,
                )
        except ImportError as exc:
            self.status_label.setText(str(exc))
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
            return None
        except Exception as exc:
            self.status_label.setText(f"Error: {exc}")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")
            return None

    def _update_status(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet(f"color: {ACCENT}; font-size: 12px;")

    # ----- public API -------------------------------------------------------

    def get_storage(self) -> ANPRBlobStorage | None:
        """Return configured storage instance, or ``None`` if disabled."""
        if not self.enable_cb.isChecked():
            return None
        return self._storage

    def update_stats(self, stats: dict) -> None:
        """Update the stats display.

        *stats* should contain keys ``total``, ``failed``, and ``bytes``
        (matching the dict returned by ``ANPRBlobStorage.get_upload_stats``).
        """
        total = stats.get("total", 0)
        failed = stats.get("failed", 0)
        nbytes = stats.get("bytes", 0)

        if nbytes < 1024:
            size_str = f"{nbytes} B"
        elif nbytes < 1024 * 1024:
            size_str = f"{nbytes / 1024:.1f} KB"
        else:
            size_str = f"{nbytes / (1024 * 1024):.1f} MB"

        self.stats_label.setText(
            f"Uploads: {total}  |  Failed: {failed}  |  Size: {size_str}"
        )
