"""Vision AI-powered Austroads vehicle classifier with CLIP cache.

Supports Claude, OpenAI, and Gemini vision APIs. Caches results using
CLIP embeddings so similar vehicles are classified locally without
repeated API calls.
"""

import base64
import json
import logging
from enum import Enum

import cv2
import numpy as np

from src.counter.vision_cache import VehicleVisionCache
from src.counter.vehicle_classifier import AustroadsClassifier

logger = logging.getLogger(__name__)


class VisionProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    GEMINI = "gemini"


AUSTROADS_SYSTEM_PROMPT = """You are an Austroads vehicle classifier for Australian traffic.
Analyse the vehicle image and classify it into exactly one of these Austroads classes:

"1"  = Short Vehicle (car, SUV, ute, light van <6m)
"1M" = Motorcycle (any 2-wheel powered vehicle)
"2"  = Short Vehicle Towing (car/ute towing a trailer or caravan)
"3"  = Two-Axle Truck/Bus (rigid truck, minibus, 2 axles)
"4"  = Three-Axle Truck/Bus (large bus, coach, 3 axles)
"5"  = Four-Axle Rigid Truck (heavy rigid, 4 axles)
"6"  = Three-Axle Articulated (semi-trailer with 3 total axles)
"7"  = Four-Axle Articulated (semi-trailer with 4 total axles)
"8"  = Five-Axle Articulated (semi + tri-axle trailer, most common semi)
"9"  = Six+ Axle Articulated (heavy semi, 6+ axles)
"10" = B-Double (prime mover + two trailers)
"11" = Double Road Train (two full trailers)
"12" = Triple Road Train (three trailers)
"AT" = Active Transport (bicycle, e-scooter, pedestrian)

Focus on: vehicle length, number of visible axles, trailer presence, body style.
Respond with ONLY this exact JSON (no markdown):
{"austroads_class": "X", "confidence": 0.85, "reasoning": "brief one-line reason"}"""


class VisionAustroadsClassifier:
    """Classifies vehicles using vision AI APIs with a local CLIP cache.

    For trucks and buses (the ambiguous cases), crops the vehicle image,
    checks the embedding cache, and only calls the API on cache misses.
    Cars, motorcycles, and bicycles use the fast YOLO-based classifier.
    """

    def __init__(
        self,
        provider: VisionProvider = VisionProvider.CLAUDE,
        api_key: str = "",
        model: str = "",
        cache_path: str = "vehicle_cache.pkl",
        similarity_threshold: float = 0.92,
        use_cache: bool = True,
    ):
        self.provider = provider
        self.api_key = api_key
        self.use_cache = use_cache
        self.fallback = AustroadsClassifier()
        self.api_calls = 0
        self.cache_hits = 0
        self.errors = 0

        default_models = {
            VisionProvider.CLAUDE: "claude-haiku-4-5-20251001",
            VisionProvider.OPENAI: "gpt-4o-mini",
            VisionProvider.GEMINI: "gemini-2.0-flash-lite",
        }
        self.model = model or default_models[provider]

        if use_cache:
            self.cache = VehicleVisionCache(
                cache_path=cache_path,
                similarity_threshold=similarity_threshold,
            )
        else:
            self.cache = None

    def classify_crop(self, crop_bgr: np.ndarray) -> dict:
        """Classify a vehicle crop into an Austroads class.

        Returns dict with: austroads_class, confidence, source ("cache"/"api"/"fallback").
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return {"austroads_class": "1", "confidence": 0.5, "source": "fallback"}

        crop_bgr = self._resize_crop(crop_bgr, max_size=400)

        try:
            # Check cache first
            if self.cache is not None:
                embedding = self.cache.extract_embedding(crop_bgr)
                cached = self.cache.find_match(embedding)
                if cached:
                    self.cache_hits += 1
                    return {
                        "austroads_class": cached.austroads_class,
                        "confidence": cached.confidence,
                        "source": "cache",
                    }
            else:
                embedding = None

            # Call vision API
            if not self.api_key:
                # No API key — fall back to YOLO-based classification
                return {"austroads_class": "3", "confidence": 0.5, "source": "fallback"}

            self.api_calls += 1
            result = self._call_api(crop_bgr)

            # Cache the result
            if self.cache is not None and embedding is not None:
                self.cache.add_entry(
                    embedding=embedding,
                    austroads_class=result["austroads_class"],
                    confidence=result.get("confidence", 0.8),
                    reasoning=result.get("reasoning", ""),
                    source="api",
                )

            result["source"] = "api"
            return result

        except Exception as e:
            self.errors += 1
            logger.error(f"Vision classification failed: {e}")
            return {"austroads_class": "3", "confidence": 0.3, "source": "error"}

    def _call_api(self, crop_bgr: np.ndarray) -> dict:
        if self.provider == VisionProvider.CLAUDE:
            return self._call_claude(crop_bgr)
        elif self.provider == VisionProvider.OPENAI:
            return self._call_openai(crop_bgr)
        elif self.provider == VisionProvider.GEMINI:
            return self._call_gemini(crop_bgr)

    def _encode_jpeg(self, crop_bgr: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.standard_b64encode(buf.tobytes()).decode("utf-8")

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from API response, handling markdown wrapping."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    def _call_claude(self, crop_bgr: np.ndarray) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        b64 = self._encode_jpeg(crop_bgr)

        response = client.messages.create(
            model=self.model,
            max_tokens=150,
            system=AUSTROADS_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": "Classify this vehicle."},
                ],
            }],
        )
        return self._parse_json_response(response.content[0].text)

    def _call_openai(self, crop_bgr: np.ndarray) -> dict:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        b64 = self._encode_jpeg(crop_bgr)

        response = client.chat.completions.create(
            model=self.model,
            max_tokens=150,
            messages=[
                {"role": "system", "content": AUSTROADS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": "Classify this vehicle."},
                    ],
                },
            ],
        )
        return self._parse_json_response(response.choices[0].message.content)

    def _call_gemini(self, crop_bgr: np.ndarray) -> dict:
        from google import genai
        from PIL import Image

        client = genai.Client(api_key=self.api_key)
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        response = client.models.generate_content(
            model=self.model,
            contents=[AUSTROADS_SYSTEM_PROMPT + "\n\nClassify this vehicle:", pil_img],
        )
        return self._parse_json_response(response.text)

    @staticmethod
    def _resize_crop(crop_bgr: np.ndarray, max_size: int = 400) -> np.ndarray:
        h, w = crop_bgr.shape[:2]
        if max(h, w) <= max_size:
            return crop_bgr
        scale = max_size / max(h, w)
        return cv2.resize(
            crop_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA
        )

    def get_stats(self) -> dict:
        total = self.api_calls + self.cache_hits
        hit_rate = self.cache_hits / total if total > 0 else 0.0
        stats = {
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "hit_rate": f"{hit_rate:.1%}",
        }
        if self.cache is not None:
            stats.update(self.cache.get_stats())
        return stats
