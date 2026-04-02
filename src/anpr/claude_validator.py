"""Claude Vision API plate validator for improving ANPR accuracy.

Uses Claude's vision capabilities to validate or correct PaddleOCR readings
on license plates, especially for low-confidence detections.
"""

import base64
import json
import logging
import re

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an Australian license plate reader. You will receive:
1. An image of a cropped license plate.
2. The OCR engine's best guess for the plate text.
3. The OCR engine's confidence score (0-1).

Your job is to read the plate in the image and return the correct text.

Australian license plate formats by state/territory:
- NSW: ABC12D (3 letters, 2 digits, 1 letter) or AB12CD (2 letters, 2 digits, 2 letters)
- QLD: 123ABC (3 digits, 3 letters) or 123AB4 (3 digits, 2 letters, 1 digit)
- VIC: ABC123 (3 letters, 3 digits) or 1AB2CD (1 digit, 2 letters, 1 digit, 2 letters)
- SA: S123ABC (S + 3 digits + 3 letters)
- WA: 1ABC234 (1 digit, 3 letters, 3 digits)
- TAS: AB1234 (2 letters, 4 digits) or ABC123 (3 letters, 3 digits)
- ACT: ABC12D (3 letters, 2 digits, 1 letter) or YAA12B
- NT: AB12CD (2 letters, 2 digits, 2 letters)
- Personalised plates vary in format.

Common OCR confusions to watch for:
- 0 (zero) vs O (letter O)
- 1 (one) vs I (letter I) vs L (letter L)
- 5 (five) vs S (letter S)
- 8 (eight) vs B (letter B)
- 2 (two) vs Z (letter Z)
- 6 (six) vs G (letter G)
- D vs 0 (zero)

Respond with ONLY a JSON object (no markdown, no explanation):
{
  "plate": "<YOUR READING>",
  "confidence": <0.0-1.0>,
  "state_guess": "<STATE ABBREVIATION or UNKNOWN>"
}

If the plate is completely unreadable, respond with:
{
  "plate": "UNREADABLE",
  "confidence": 0.0,
  "state_guess": "UNKNOWN"
}
"""


class ClaudePlateValidator:
    """Validates and corrects plate readings using Claude vision API.

    Only calls the API for plates below a confidence threshold or
    that fail Australian format validation, to minimize costs.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        confidence_threshold: float = 0.7,
    ):
        self._api_key = api_key
        self._model = model
        self._confidence_threshold = confidence_threshold
        self._client = None
        self._api_calls = 0
        self._corrections = 0
        self._confirmations = 0

    def _get_client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for Claude plate validation. "
                    "Install it with: pip install anthropic"
                )
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def should_validate(self, ocr_confidence: float, is_valid_format: bool) -> bool:
        """Determine if this plate reading should be sent to Claude.

        Args:
            ocr_confidence: PaddleOCR confidence score (0-1).
            is_valid_format: Whether the OCR text matches a known AU plate format.

        Returns:
            True if Claude validation is recommended.
        """
        if ocr_confidence < self._confidence_threshold:
            return True
        if not is_valid_format:
            return True
        return False

    def _prepare_image(self, plate_img: np.ndarray) -> str:
        """Resize if needed and encode plate crop as base64 JPEG.

        If the image height is below 100px, it is scaled up using cubic
        interpolation so Claude's vision has more detail to work with.

        Args:
            plate_img: BGR numpy array of the cropped plate.

        Returns:
            Base64-encoded JPEG string.
        """
        h, w = plate_img.shape[:2]
        if h < 100:
            scale = 100.0 / h
            new_w = int(w * scale)
            new_h = 100
            plate_img = cv2.resize(
                plate_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC
            )

        success, buffer = cv2.imencode(".jpg", plate_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            raise ValueError("Failed to encode plate image as JPEG")

        return base64.b64encode(buffer).decode("utf-8")

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Extract JSON from Claude's response, handling code-block wrapping.

        Args:
            text: Raw response text from Claude.

        Returns:
            Parsed dict with keys: plate, confidence, state_guess.
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if code_block:
            cleaned = code_block.group(1).strip()

        return json.loads(cleaned)

    def validate_plate(
        self,
        plate_img: np.ndarray,
        paddle_text: str,
        paddle_confidence: float,
    ) -> dict:
        """Send plate crop + PaddleOCR result to Claude for validation.

        Args:
            plate_img: BGR numpy array of the cropped plate.
            paddle_text: PaddleOCR's reading of the plate.
            paddle_confidence: PaddleOCR's confidence (0-1).

        Returns:
            dict with keys:
                plate (str): The validated/corrected plate text.
                confidence (float): Claude's confidence in its reading.
                changed (bool): Whether Claude changed the OCR result.
                source (str): "claude" if API was called, "paddle" on fallback.
        """
        fallback = {
            "plate": paddle_text,
            "confidence": paddle_confidence,
            "changed": False,
            "source": "paddle",
        }

        try:
            image_b64 = self._prepare_image(plate_img)
        except Exception:
            logger.warning("Failed to encode plate image; falling back to PaddleOCR.")
            return fallback

        user_message = (
            f"OCR engine read this plate as: {paddle_text!r} "
            f"(confidence: {paddle_confidence:.2f}).\n"
            "Please read the plate image and confirm or correct the text."
        )

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": user_message,
                            },
                        ],
                    }
                ],
            )
            self._api_calls += 1
        except ImportError:
            raise
        except Exception as exc:
            logger.warning("Claude API call failed (%s); using PaddleOCR result.", exc)
            return fallback

        # Extract text from response
        try:
            raw_text = response.content[0].text
        except (IndexError, AttributeError):
            logger.warning("Unexpected Claude response structure; using PaddleOCR result.")
            return fallback

        # Parse the JSON response
        try:
            parsed = self._parse_response(raw_text)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse Claude response (%s): %s", exc, raw_text)
            return fallback

        claude_plate = parsed.get("plate", "").strip().upper()
        claude_confidence = float(parsed.get("confidence", 0.0))

        # Handle UNREADABLE response
        if claude_plate == "UNREADABLE":
            logger.info(
                "Claude marked plate as UNREADABLE; keeping PaddleOCR result %r.",
                paddle_text,
            )
            return fallback

        changed = claude_plate != paddle_text.strip().upper()
        if changed:
            self._corrections += 1
            logger.info(
                "Claude corrected plate: %r -> %r (confidence %.2f)",
                paddle_text,
                claude_plate,
                claude_confidence,
            )
        else:
            self._confirmations += 1
            logger.debug(
                "Claude confirmed plate: %r (confidence %.2f)",
                claude_plate,
                claude_confidence,
            )

        return {
            "plate": claude_plate,
            "confidence": claude_confidence,
            "changed": changed,
            "source": "claude",
        }

    def get_stats(self) -> dict:
        """Return validation statistics.

        Returns:
            dict with keys: api_calls, corrections, confirmations.
        """
        return {
            "api_calls": self._api_calls,
            "corrections": self._corrections,
            "confirmations": self._confirmations,
        }
