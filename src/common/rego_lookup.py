"""Australian vehicle registration lookup via CarRegistrationAPI.com.au.

Checks the local VehicleDatabase cache first, then falls back to the API.
Results are cached locally to avoid redundant lookups.
"""

from __future__ import annotations

import json
import logging
import threading
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from src.common.vehicle_db import VehicleDatabase

logger = logging.getLogger(__name__)

# Australian states accepted by the API
AU_STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]

# Default timeout for HTTP requests (seconds)
_DEFAULT_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------

class RegoLookupResult:
    """Structured result from a registration lookup."""

    def __init__(
        self,
        plate: str,
        state: str = "",
        status: str = "",
        expiry_date: str = "",
        make: str = "",
        model: str = "",
        body_type: str = "",
        source: str = "",
        raw: dict | None = None,
    ):
        self.plate = plate
        self.state = state
        self.status = status        # registered | expired | cancelled | not_found | error
        self.expiry_date = expiry_date
        self.make = make
        self.model = model
        self.body_type = body_type
        self.source = source        # cache | api | mock | not_found
        self.raw = raw or {}

    # Convenience helpers ------------------------------------------------

    def is_registered(self) -> bool:
        """Return True when the vehicle appears to be currently registered."""
        return self.status.lower() in ("registered", "current", "active")

    def to_dict(self) -> dict:
        return {
            "plate": self.plate,
            "state": self.state,
            "status": self.status,
            "expiry_date": self.expiry_date,
            "make": self.make,
            "model": self.model,
            "body_type": self.body_type,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return (
            f"RegoLookupResult(plate={self.plate!r}, state={self.state!r}, "
            f"status={self.status!r}, make={self.make!r}, model={self.model!r}, "
            f"source={self.source!r})"
        )


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class CarRegistrationAPI:
    """HTTP client for CarRegistrationAPI.com.au.

    The exact endpoint format is not fully documented, so this client
    attempts multiple request styles in order:

    1. REST-style POST (JSON body)
    2. REST-style POST (form-encoded body)
    3. SOAP/ASMX XML POST

    The first style that returns a parseable response wins and is remembered
    for subsequent calls (sticky style).
    """

    BASE_URL = "https://www.carregistrationapi.com.au"
    _REST_PATH = "/api/reg.asmx/CheckRegistration"
    _SOAP_PATH = "/api/reg.asmx"

    # SOAP envelope template
    _SOAP_ENVELOPE = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        "<soap:Body>"
        '<CheckRegistration xmlns="https://www.carregistrationapi.com.au/">'
        "<username>{username}</username>"
        "<password>{password}</password>"
        "<plateNumber>{plate}</plateNumber>"
        "<state>{state}</state>"
        "</CheckRegistration>"
        "</soap:Body>"
        "</soap:Envelope>"
    )

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        test_mode: bool = False,
    ):
        self._username = username
        self._password = password
        self._base_url = (base_url or self.BASE_URL).rstrip("/")
        self._timeout = timeout
        self._test_mode = test_mode
        self._session = requests.Session()
        self._api_calls = 0
        self._preferred_style: str | None = None  # "json" | "form" | "soap"
        self._lock = threading.Lock()

    # Public interface ---------------------------------------------------

    def lookup(self, plate: str, state: str = "") -> RegoLookupResult:
        """Look up a plate via the API.

        If *state* is not provided every state in :data:`AU_STATES` is tried
        until a match is found (each attempt costs an API call).
        """
        plate = plate.strip().upper()

        if self._test_mode:
            return self._mock_lookup(plate, state)

        states_to_try = [state.upper()] if state else list(AU_STATES)

        for st in states_to_try:
            try:
                data = self._call_api(plate, st)
            except Exception as exc:
                logger.debug(
                    "API call failed for plate=%s state=%s: %s", plate, st, exc
                )
                continue

            result = self._parse_response(data, plate, st)
            if result.status and result.status != "not_found":
                return result

        # Nothing found in any state
        return RegoLookupResult(plate=plate, state=state, status="not_found", source="api")

    def test_connection(self) -> bool:
        """Verify that the API endpoint is reachable and credentials are
        accepted.  Returns *True* on success."""
        try:
            # Use a known-format test plate
            data = self._call_api("TEST000", "NSW")
            # Any parseable response (even "not found") means the service is up
            logger.info("CarRegistrationAPI connection test successful")
            return True
        except Exception as exc:
            logger.warning("CarRegistrationAPI connection test failed: %s", exc)
            return False

    def get_stats(self) -> dict:
        return {"api_calls": self._api_calls, "preferred_style": self._preferred_style}

    # Internal helpers ---------------------------------------------------

    def _call_api(self, plate: str, state: str) -> dict:
        """Try each request style until one succeeds.  Returns parsed dict."""
        # If we already know which style works, try that first
        styles = ["json", "form", "soap"]
        if self._preferred_style:
            styles.remove(self._preferred_style)
            styles.insert(0, self._preferred_style)

        last_exc: Exception | None = None
        for style in styles:
            try:
                data = self._call_style(style, plate, state)
                with self._lock:
                    self._api_calls += 1
                    self._preferred_style = style
                logger.debug(
                    "API call OK  style=%s plate=%s state=%s", style, plate, state
                )
                return data
            except Exception as exc:
                logger.debug("Style %s failed for %s/%s: %s", style, plate, state, exc)
                last_exc = exc

        raise ConnectionError(
            f"All API call styles failed for {plate}/{state}"
        ) from last_exc

    def _call_style(self, style: str, plate: str, state: str) -> dict:
        """Execute a single request in the given *style* and return parsed
        response data."""
        url_rest = f"{self._base_url}{self._REST_PATH}"
        url_soap = f"{self._base_url}{self._SOAP_PATH}"

        payload = {
            "username": self._username,
            "password": self._password,
            "plateNumber": plate,
            "state": state,
        }

        if style == "json":
            resp = self._session.post(
                url_rest,
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()

        if style == "form":
            resp = self._session.post(
                url_rest,
                data=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            # Response may be JSON or XML-wrapped
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                return resp.json()
            # Try XML
            return self._parse_xml_body(resp.text)

        if style == "soap":
            envelope = self._SOAP_ENVELOPE.format(
                username=self._username,
                password=self._password,
                plate=plate,
                state=state,
            )
            resp = self._session.post(
                url_soap,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "https://www.carregistrationapi.com.au/CheckRegistration",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return self._parse_xml_body(resp.text)

        raise ValueError(f"Unknown API style: {style}")

    @staticmethod
    def _parse_xml_body(xml_text: str) -> dict:
        """Best-effort extraction of key/value pairs from an XML response."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"Unparseable XML response: {exc}") from exc

        data: dict = {}
        # Walk every element and use the local tag name as the key
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if elem.text and elem.text.strip():
                data[tag] = elem.text.strip()
        if not data:
            raise ValueError("XML response contained no usable data")
        return data

    @staticmethod
    def _parse_response(data: dict, plate: str, state: str) -> RegoLookupResult:
        """Normalise a raw API response dict into a :class:`RegoLookupResult`."""
        # The API may use different key names — try common variants
        def _get(*keys: str) -> str:
            for k in keys:
                for dk in data:
                    if dk.lower() == k.lower():
                        return str(data[dk])
            return ""

        status_raw = _get("registrationStatus", "status", "RegistrationStatus", "regStatus")
        make = _get("make", "Make", "vehicleMake")
        model = _get("model", "Model", "vehicleModel")
        body = _get("bodyType", "BodyType", "body_type", "bodyShape")
        expiry = _get("expiryDate", "ExpiryDate", "expiry_date", "registrationExpiry")

        # Normalise status
        status = status_raw.lower()
        if status in ("registered", "current", "active", "valid"):
            status = "registered"
        elif status in ("expired", "lapsed"):
            status = "expired"
        elif status in ("cancelled", "suspended", "deregistered"):
            status = "cancelled"
        elif status:
            status = status_raw  # keep original if unrecognised
        else:
            status = "not_found"

        return RegoLookupResult(
            plate=plate,
            state=state,
            status=status,
            expiry_date=expiry,
            make=make,
            model=model,
            body_type=body,
            source="api",
            raw=data,
        )

    # Mock / test mode ---------------------------------------------------

    @staticmethod
    def _mock_lookup(plate: str, state: str) -> RegoLookupResult:
        """Return deterministic fake data for development / testing."""
        # Use the first character to vary mock responses
        char = plate[0].upper() if plate else "A"
        if char in "ABCDE":
            return RegoLookupResult(
                plate=plate, state=state or "NSW", status="registered",
                expiry_date="2027-06-30", make="Toyota", model="HiLux",
                body_type="Utility", source="mock",
            )
        if char in "FGHIJ":
            return RegoLookupResult(
                plate=plate, state=state or "VIC", status="expired",
                expiry_date="2024-01-15", make="Holden", model="Commodore",
                body_type="Sedan", source="mock",
            )
        return RegoLookupResult(
            plate=plate, state=state or "QLD", status="not_found", source="mock",
        )


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

class RegoLookupService:
    """Orchestrates rego lookups: checks the local DB cache first, then the
    external API.

    Usage::

        db = VehicleDatabase("data.db")
        api = CarRegistrationAPI("user", "pass")
        service = RegoLookupService(db, api)
        result = service.lookup("ABC123", state="NSW")
    """

    def __init__(
        self,
        db: VehicleDatabase | None = None,
        api: CarRegistrationAPI | None = None,
        enabled: bool = True,
    ):
        self._db = db
        self._api = api
        self._enabled = enabled
        self._cache_hits = 0
        self._api_lookups = 0
        self._lock = threading.Lock()

    # Public interface ---------------------------------------------------

    def lookup(self, plate: str, state: str = "") -> RegoLookupResult | None:
        """Look up a plate.  Checks the local DB cache first, then the API.

        Returns ``None`` when the service is disabled.
        """
        if not self._enabled:
            return None

        plate = plate.strip().upper()
        if not plate:
            return None

        # Step 1 — check local cache
        if self._db is not None:
            try:
                cached = self._db.get_rego_cache(plate)
            except Exception:
                logger.debug("DB cache read failed for %s", plate, exc_info=True)
                cached = None

            if cached:
                with self._lock:
                    self._cache_hits += 1
                logger.debug("Cache hit for plate %s", plate)
                return RegoLookupResult(
                    plate=plate,
                    state=cached.get("state", ""),
                    status=cached.get("status", ""),
                    expiry_date=cached.get("expiry_date", ""),
                    make=cached.get("make", ""),
                    model=cached.get("model", ""),
                    body_type=cached.get("body_type", ""),
                    source="cache",
                    raw=json.loads(cached["raw_response"])
                    if cached.get("raw_response")
                    else {},
                )

        # Step 2 — call external API
        if self._api is not None:
            try:
                result = self._api.lookup(plate, state)
                with self._lock:
                    self._api_lookups += 1

                # Cache successful results
                if self._db is not None and result.status != "error":
                    try:
                        self._db.save_rego_result(
                            plate_text=plate,
                            state=result.state,
                            status=result.status,
                            expiry_date=result.expiry_date,
                            make=result.make,
                            model=result.model,
                            body_type=result.body_type,
                            raw_response=json.dumps(result.raw),
                            source=result.source,
                        )
                    except Exception:
                        logger.debug(
                            "Failed to cache rego result for %s", plate, exc_info=True
                        )
                return result
            except Exception as exc:
                logger.warning("Rego API lookup failed for %s: %s", plate, exc)

        # Nothing available
        return RegoLookupResult(plate=plate, status="not_found", source="not_found")

    def bulk_lookup(
        self, plates: list[str], state: str = ""
    ) -> dict[str, RegoLookupResult | None]:
        """Look up multiple plates sequentially.

        Returns a dict keyed by (uppercased) plate text.
        """
        results: dict[str, RegoLookupResult | None] = {}
        for plate in plates:
            key = plate.strip().upper()
            results[key] = self.lookup(plate, state)
        return results

    def get_stats(self) -> dict:
        with self._lock:
            stats: dict = {
                "enabled": self._enabled,
                "cache_hits": self._cache_hits,
                "api_lookups": self._api_lookups,
            }
        if self._api is not None:
            stats["api"] = self._api.get_stats()
        return stats
