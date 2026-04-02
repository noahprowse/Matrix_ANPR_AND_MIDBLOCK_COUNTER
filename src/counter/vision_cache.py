"""CLIP embedding cache for vehicle classification.

Extracts visual embeddings from vehicle crops and caches API classification
results. When a similar vehicle is seen again, returns the cached class
without making an API call.
"""

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached vehicle classification result."""
    austroads_class: str
    confidence: float
    embedding: np.ndarray
    source: str  # "api" or "cache"
    hit_count: int = 0
    reasoning: str = ""


class VehicleVisionCache:
    """CLIP-based embedding cache for vehicle classification.

    1. Extract CLIP embedding from vehicle crop
    2. Compare to all cached embeddings via cosine similarity
    3. If best match >= threshold: return cached class (no API call)
    4. If no match: caller should query API, then add result here
    """

    def __init__(
        self,
        cache_path: str = "vehicle_cache.pkl",
        similarity_threshold: float = 0.92,
        min_confidence_to_cache: float = 0.75,
    ):
        self.cache_path = Path(cache_path)
        self.similarity_threshold = similarity_threshold
        self.min_confidence_to_cache = min_confidence_to_cache
        self.entries: list[CacheEntry] = []
        self._model = None
        self._processor = None
        self._device = None
        self._load_cache()

    def _get_model(self):
        """Lazy-load CLIP model."""
        if self._model is None:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading CLIP model on {self._device}...")
            self._model = CLIPModel.from_pretrained(
                "openai/clip-vit-base-patch32"
            ).to(self._device)
            self._processor = CLIPProcessor.from_pretrained(
                "openai/clip-vit-base-patch32"
            )
            self._model.eval()
            logger.info("CLIP model loaded.")
        return self._model, self._processor, self._device

    def extract_embedding(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Extract a normalized 512-dim CLIP embedding from a BGR crop."""
        import torch
        from PIL import Image

        model, processor, device = self._get_model()

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        inputs = processor(images=pil_image, return_tensors="pt").to(device)

        with torch.no_grad():
            features = model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)

        return features.cpu().numpy()[0]

    def find_match(self, embedding: np.ndarray) -> CacheEntry | None:
        """Find the best matching cached entry above the similarity threshold."""
        if not self.entries:
            return None

        cached_embeddings = np.stack([e.embedding for e in self.entries])
        similarities = cached_embeddings @ embedding

        best_idx = int(np.argmax(similarities))
        best_sim = float(similarities[best_idx])

        if best_sim >= self.similarity_threshold:
            entry = self.entries[best_idx]
            entry.hit_count += 1
            logger.debug(
                f"Cache HIT: class={entry.austroads_class}, "
                f"similarity={best_sim:.3f}, hits={entry.hit_count}"
            )
            return entry

        logger.debug(f"Cache MISS: best_similarity={best_sim:.3f}")
        return None

    def add_entry(
        self,
        embedding: np.ndarray,
        austroads_class: str,
        confidence: float,
        reasoning: str = "",
        source: str = "api",
    ):
        """Add a new classification result to the cache."""
        if confidence < self.min_confidence_to_cache:
            return

        entry = CacheEntry(
            austroads_class=austroads_class,
            confidence=confidence,
            embedding=embedding,
            source=source,
            reasoning=reasoning,
        )
        self.entries.append(entry)
        self._save_cache()

    def _save_cache(self):
        with open(self.cache_path, "wb") as f:
            pickle.dump(self.entries, f)

    def _load_cache(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "rb") as f:
                    self.entries = pickle.load(f)
                logger.info(f"Loaded {len(self.entries)} cached vehicle embeddings")
            except Exception as e:
                logger.warning(f"Could not load cache: {e}. Starting fresh.")
                self.entries = []

    def get_stats(self) -> dict:
        if not self.entries:
            return {"total_entries": 0, "total_hits": 0}
        total_hits = sum(e.hit_count for e in self.entries)
        class_dist = {}
        for e in self.entries:
            class_dist[e.austroads_class] = class_dist.get(e.austroads_class, 0) + 1
        return {
            "total_entries": len(self.entries),
            "total_hits": total_hits,
            "class_distribution": class_dist,
        }

    def clear(self):
        self.entries = []
        if self.cache_path.exists():
            self.cache_path.unlink()
