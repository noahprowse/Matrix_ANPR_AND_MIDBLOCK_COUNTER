"""ML feedback and correction store for ANPR plate reading improvement.

Tracks character-level substitution frequencies from user corrections,
and applies the most common corrections to future OCR readings. This
creates a simple learning loop: user corrections → JSON store → improved
post-OCR correction in future runs.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class MLFeedbackStore:
    """Stores and applies OCR correction feedback.

    Data is persisted as a JSON file at the specified path, typically
    ``{job_folder}/anpr_corrections.json``.
    """

    # Minimum number of observations before a substitution is trusted
    _MIN_FREQUENCY = 3

    def __init__(self, path: str = ""):
        self._path = path
        self._data: dict = self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load corrections from JSON file, or return empty structure."""
        if not self._path:
            return self._empty()
        try:
            p = Path(self._path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("Loaded ML feedback from %s", self._path)
                return data
        except Exception as e:
            logger.warning("Failed to load ML feedback from %s: %s", self._path, e)
        return self._empty()

    @staticmethod
    def _empty() -> dict:
        return {
            "substitutions": {},      # char -> {replacement: count}
            "plate_overrides": {},    # wrong_plate -> correct_plate
            "total_corrections": 0,
        }

    def save(self) -> None:
        """Write current corrections to disk."""
        if not self._path:
            return
        try:
            p = Path(self._path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            logger.info("Saved ML feedback to %s", self._path)
        except Exception as e:
            logger.warning("Failed to save ML feedback: %s", e)

    # ── Recording corrections ───────────────────────────────────────

    def record_correction(self, original: str, corrected: str) -> None:
        """Record a user correction by diffing character-by-character.

        For each position where the characters differ, increment the
        substitution frequency for that character pair.

        Args:
            original:  The OCR-produced plate text.
            corrected: The user-corrected plate text.
        """
        if original == corrected:
            return

        self._data["total_corrections"] = self._data.get("total_corrections", 0) + 1

        # Record full plate override
        self._data.setdefault("plate_overrides", {})[original] = corrected

        # Character-level diff (only when same length)
        subs = self._data.setdefault("substitutions", {})
        if len(original) == len(corrected):
            for orig_ch, corr_ch in zip(original, corrected):
                if orig_ch != corr_ch:
                    char_map = subs.setdefault(orig_ch, {})
                    char_map[corr_ch] = char_map.get(corr_ch, 0) + 1

        logger.info(
            "Recorded correction: %r -> %r (total: %d)",
            original, corrected, self._data["total_corrections"],
        )

    # ── Applying corrections ────────────────────────────────────────

    def get_substitutions(self) -> dict[str, str]:
        """Return the most frequent substitution for each character.

        Only returns substitutions observed at least ``_MIN_FREQUENCY``
        times, to avoid applying noise from one-off corrections.
        """
        result = {}
        for orig_char, replacements in self._data.get("substitutions", {}).items():
            if not replacements:
                continue
            best_char = max(replacements, key=replacements.get)
            count = replacements[best_char]
            if count >= self._MIN_FREQUENCY:
                result[orig_char] = best_char
        return result

    def apply_corrections(self, plate_text: str, confidence: float) -> str:
        """Apply learned corrections to an OCR reading.

        Only applies corrections when OCR confidence is below 80%,
        to avoid "fixing" readings that are already confident.

        Args:
            plate_text:  Raw OCR plate text.
            confidence:  OCR confidence (0-100).

        Returns:
            Corrected plate text (may be unchanged).
        """
        if confidence >= 80.0:
            return plate_text

        # Check for exact plate override first
        overrides = self._data.get("plate_overrides", {})
        if plate_text in overrides:
            corrected = overrides[plate_text]
            logger.debug("Applied plate override: %r -> %r", plate_text, corrected)
            return corrected

        # Apply character substitutions
        subs = self.get_substitutions()
        if not subs:
            return plate_text

        corrected_chars = []
        changed = False
        for ch in plate_text:
            if ch in subs:
                corrected_chars.append(subs[ch])
                changed = True
            else:
                corrected_chars.append(ch)

        if changed:
            corrected = "".join(corrected_chars)
            logger.debug("Applied char substitutions: %r -> %r", plate_text, corrected)
            return corrected

        return plate_text

    @property
    def total_corrections(self) -> int:
        return self._data.get("total_corrections", 0)

    @property
    def substitution_count(self) -> int:
        return len(self.get_substitutions())
