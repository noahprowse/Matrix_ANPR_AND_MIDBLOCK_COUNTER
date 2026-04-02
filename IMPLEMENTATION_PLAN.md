# Matrix ANPR & Midblock Counter — Implementation Plan

## Project Overview

A Windows desktop application with two core modules:

1. **ANPR Video Extract** — Plays video files, detects and reads vehicle number plates, records plate text + timestamp + site number, exports to Excel.
2. **Midblock Vehicle Counter** — Plays video files, user draws a count line, AI detects and classifies vehicles crossing the line using the Austroads classification system, exports counts to Excel.

---

## Technology Stack

| Component | Technology | Reason |
|---|---|---|
| **Language** | Python 3.11+ | Best AI/ML ecosystem, rapid development |
| **GUI Framework** | PySide6 (Qt for Python) | LGPL license (free for commercial use), native video playback, QGraphicsScene for interactive overlays, professional widget set |
| **Video I/O** | OpenCV (`opencv-python`) | Frame extraction, preprocessing, timestamp retrieval |
| **ANPR Detection** | YOLO11 (`ultralytics`) for plate detection | State of the art, 96%+ accuracy |
| **ANPR OCR** | PaddleOCR | Highest accuracy for Latin-character plates (outperforms EasyOCR and Tesseract) |
| **Vehicle Detection** | YOLO11 (`ultralytics`) | Pre-trained COCO weights detect car, motorcycle, bus, truck, bicycle |
| **Object Tracking** | ByteTrack (built into Ultralytics) | Best accuracy/speed balance for fixed-camera counting |
| **Line Counting** | Roboflow `supervision` library | Production-ready `LineZone` with per-class, direction-aware counting |
| **Excel Export** | `pandas` + `openpyxl` | Data manipulation + formatted Excel reports |
| **Packaging** | PyInstaller | Standalone Windows .exe, mature PySide6 support |

### Python Dependencies

```
PySide6>=6.6
opencv-python>=4.9
ultralytics>=8.3
paddleocr>=2.7
paddlepaddle>=2.6
supervision>=0.25
pandas>=2.2
openpyxl>=3.1
numpy>=1.26
pyinstaller>=6.0
```

---

## Module 1: ANPR Video Extract

### 1.1 What It Does

- User opens a video file (.mp4, .avi, .mkv, .mov)
- Video plays in a preview player with standard controls (play/pause, seek, speed)
- User enters a **Site Number** (text field)
- AI detects number plates in each frame and reads the text via OCR
- Duplicate plates across consecutive frames are deduplicated (same plate = one entry)
- Results are displayed in a live table: Plate Number | Timestamp | Confidence
- User exports results to a formatted Excel file

### 1.2 ANPR Pipeline (per frame)

```
Video File
  → OpenCV VideoCapture (frame extraction)
  → Frame sampling (every 3rd frame at 30fps = ~10fps processing)
  → YOLO11 plate detection model (bounding box around plate)
  → Crop plate region + preprocessing:
      - Resize to minimum 100px height
      - Grayscale conversion
      - CLAHE contrast enhancement
      - Bilateral filter denoising
      - Adaptive thresholding
  → PaddleOCR text extraction
  → Regex validation against Australian plate formats
  → Deduplication via object tracking (ByteTrack assigns vehicle IDs)
      - Collect all OCR readings per vehicle ID
      - Take highest-confidence or most-frequent reading
  → Store: {plate_text, timestamp, confidence, frame_number, vehicle_id}
```

### 1.3 ANPR Models

**Option A — Fully Local (No API costs, recommended)**
- Plate detection: YOLO11 fine-tuned on license plate dataset from Roboflow Universe (10,125 annotated images)
- Pre-trained model available: `morsetechlab/yolov11-license-plate-detection` on Hugging Face
- OCR: PaddleOCR (pip install, runs locally)

**Option B — API-based (Higher accuracy, requires internet)**
- Plate Recognizer Snapshot API ($10–35/month)
- Explicit Australia support with regional tuning
- Python wrapper: `deep-license-plate-recognition` GitHub repo
- On-premise Docker SDK available for offline use (perpetual license)

**Option C — Commercial SDK (One-time cost)**
- SimpleLPR ($450 one-time, pip install, unlimited distribution)
- 85–95% accuracy, built-in temporal tracking for video deduplication

**Recommendation:** Start with Option A (fully local) using YOLO11 + PaddleOCR. If accuracy is insufficient for Australian plates, upgrade to Plate Recognizer API.

### 1.4 Australian Plate Format Validation

Post-OCR regex filtering to reject garbage readings. Common Australian patterns:
- NSW: `[A-Z]{2,3}[0-9]{2,3}[A-Z]{0,2}` (e.g., ABC12D, AB12CD)
- VIC: `[A-Z]{3}[0-9]{3}`, `1[A-Z]{2}[0-9]{1,2}[A-Z]{2}`
- QLD: `[0-9]{3}[A-Z]{3}`

Reference: `ANPR-Australia/ANPR-RevenueNSW` GitHub repo for NSW-specific regex patterns.

### 1.5 Excel Output Format (ANPR)

| Column | Description |
|---|---|
| Site Number | User-entered site identifier |
| Plate Number | Detected plate text |
| Date | Date from video timestamp or file metadata |
| Time | HH:MM:SS timestamp in the video |
| Confidence | OCR confidence score (0–100%) |
| Direction | If applicable (based on vehicle tracking) |

### 1.6 Key Open-Source References

| Project | URL | Relevance |
|---|---|---|
| FastANPR | github.com/arvindrajan92/fastanpr | YOLOv8 + PaddleOCR, pip-installable |
| Video-ANPR | github.com/sveyek/Video-ANPR | YOLOv8 + tracking, per-vehicle OCR aggregation |
| computervisioneng ANPR | github.com/computervisioneng/real-time-number-plate-recognition-anpr | YOLO + SORT tracking with OCR |
| deep-license-plate-recognition | github.com/parkpow/deep-license-plate-recognition | Plate Recognizer API wrapper with video support |
| PlateCatcher | platecatcher.uk | Free Windows app for reference (supports AU plates) |

---

## Module 2: Midblock Vehicle Counter

### 2.1 What It Does

- User opens a video file
- Video plays in a preview player
- User draws one or more **count lines** on the video by clicking and dragging
- User selects which **Austroads classification** categories to track
- AI detects vehicles, classifies them by type, tracks them, and counts crossings of the line
- Counts are direction-aware (in vs. out / northbound vs. southbound)
- Results are displayed in a live summary table
- User exports results to a formatted Excel file with counts broken down by class and time interval

### 2.2 Austroads Vehicle Classification System

The Austroads classification system (current standard: AP-G104-23) uses 12 classes + active transport:

| Class | Code | Name | Typical Vehicles | YOLO Mapping |
|---|---|---|---|---|
| 1 | SV | Short Vehicle | Cars, SUVs, utes, motorcycles | `car` + `motorcycle` |
| 2 | SVT | Short Vehicle Towing | Cars towing trailers/caravans | `car` (with trailer detection) |
| 3 | TB2 | Two-Axle Truck/Bus | 2-axle rigid trucks, minibuses | `truck` (small) + `bus` (small) |
| 4 | TB3 | Three-Axle Truck/Bus | 3-axle trucks, articulated buses | `bus` (large) + `truck` (medium) |
| 5 | T4 | Four-Axle Truck | Heavy rigid trucks | `truck` (by length) |
| 6 | ART3 | Three-Axle Articulated | Light semi-trailers | `truck` (by length) |
| 7 | ART4 | Four-Axle Articulated | Standard semi-trailers | `truck` (by length) |
| 8 | ART5 | Five-Axle Articulated | Common semi-trailer (tri-axle) | `truck` (by length) |
| 9 | ART6 | Six+ Axle Articulated | Heavy semi-trailers | `truck` (by length) |
| 10 | BD | B-Double | B-double combinations | `truck` (very long) |
| 11 | DRT | Double Road Train | Double road trains | `truck` (very long) |
| 12 | TRT | Triple Road Train | Triple road trains | `truck` (very long) |
| AT | — | Active Transport | Bicycles, pedestrians, e-scooters | `bicycle` + `person` |

**AI Classification Strategy:**

YOLO's 5 vehicle COCO classes (car, motorcycle, bus, truck, bicycle) provide a solid Level 1 grouping. For more granular Austroads classification:

1. **Reliable from YOLO alone:** Class 1 (car/motorcycle), Class 3/4 (bus), basic truck vs. car
2. **Requires length estimation:** Classes 5–12 (different truck configurations) — use calibrated bounding box dimensions to estimate vehicle length
3. **User-assisted classification:** Allow users to configure the mapping between detected categories and Austroads classes, or manually reclassify edge cases

**Practical approach for the first version:**
- Implement a simplified Austroads grouping that YOLO can reliably distinguish:
  - Class 1: Cars + SUVs + Utes (YOLO `car`)
  - Class 1 (sub): Motorcycles (YOLO `motorcycle`)
  - Class 3/4: Buses (YOLO `bus`)
  - Class 3: Light trucks (YOLO `truck`, short bounding box)
  - Class 5–9: Heavy trucks/articulated (YOLO `truck`, long bounding box)
  - Class 10–12: Road trains (YOLO `truck`, very long bounding box)
  - AT: Bicycles (YOLO `bicycle`)
- Allow users to customize the class mapping via the UI

### 2.3 Counting Pipeline (per frame)

```
Video File
  → OpenCV VideoCapture
  → YOLO11 detection (car, motorcycle, bus, truck, bicycle classes)
  → ByteTrack object tracking (assigns persistent IDs across frames)
  → For each tracked vehicle:
      - Compute centroid position
      - Check if centroid crosses the user-drawn count line
      - Determine crossing direction (in/out) via cross-product math
      - Classify by Austroads class (YOLO class + length estimation)
      - Increment per-class, per-direction counter
      - Mark vehicle ID as "counted" to prevent double-counting
  → Display: bounding boxes, tracking IDs, count line, live totals
```

### 2.4 Line-Crossing Detection Algorithm

Using the Roboflow `supervision` library's `LineZone`:

```python
import supervision as sv
from ultralytics import YOLO

model = YOLO("yolo11m.pt")

LINE_START = sv.Point(x1, y1)  # user-drawn start
LINE_END = sv.Point(x2, y2)    # user-drawn end
line_zone = sv.LineZone(start=LINE_START, end=LINE_END)

# Per frame:
results = model.track(frame, tracker="bytetrack.yaml", persist=True)
detections = sv.Detections.from_ultralytics(results[0])
line_zone.trigger(detections)
# line_zone.in_count, line_zone.out_count are updated
```

Direction is determined by the line vector orientation — the "in" direction is the left-hand normal.

### 2.5 Excel Output Format (Vehicle Counter)

**Sheet 1: Summary**
| Column | Description |
|---|---|
| Site Number | User-entered site identifier |
| Survey Date | Date of the video |
| Survey Period | Start time – End time |
| Total Vehicles | Grand total |
| Per-class totals | One column per Austroads class |

**Sheet 2: Interval Data**
| Time Interval | Direction | Class 1 | Class 2 | Class 3 | ... | Class 12 | AT | Total |
|---|---|---|---|---|---|---|---|---|
| 07:00–07:15 | NB | 45 | 2 | 3 | ... | 0 | 5 | 55 |
| 07:00–07:15 | SB | 38 | 1 | 4 | ... | 0 | 3 | 46 |
| 07:15–07:30 | NB | ... | | | | | | |

Time intervals: 15-minute bins (standard for traffic surveys, configurable).

### 2.6 Key Open-Source References

| Project | URL | Relevance |
|---|---|---|
| Ultralytics ObjectCounter | docs.ultralytics.com/guides/object-counting | Built-in line/region counting |
| Roboflow supervision | github.com/roboflow/supervision | LineZone, per-class counting, annotators |
| richard-zi/carcounter | github.com/richard-zi/carcounter | YOLOv8 + ByteTrack + Streamlit UI |
| arief25ramadhan/vehicle-tracking-counting | github.com/arief25ramadhan/vehicle-tracking-counting | Clean YOLOv8 + ByteTrack implementation |
| Behnam-Asadi/YOLOv8-traffic-analysis | github.com/Behnam-Asadi/YOLOv8-traffic-analysis | Speed + direction analysis |
| SrujanPR/Vehicle-Detection-and-Counter-using-Yolo11 | github.com/SrujanPR/Vehicle-Detection-and-Counter-using-Yolo11 | Latest YOLO11 counting |
| OpenDataCam | github.com/opendatacam/opendatacam | Full open-source traffic counter with web UI |

---

## Application Architecture

### 3.1 Project Structure

```
Matrix_ANPR_AND_MIDBLOCK_COUNTER/
├── main.py                          # Entry point, launches MainWindow
├── requirements.txt
├── assets/
│   ├── icons/                       # App icons
│   ├── models/                      # YOLO weight files
│   │   ├── yolo11m.pt               # Vehicle detection model
│   │   └── plate_detector.pt        # License plate detection model
│   └── styles/                      # Qt stylesheets
├── src/
│   ├── __init__.py
│   ├── app.py                       # MainWindow with tab navigation
│   ├── common/
│   │   ├── __init__.py
│   │   ├── video_player.py          # Reusable video player widget
│   │   ├── video_worker.py          # QThread for OpenCV frame processing
│   │   ├── overlay_view.py          # QGraphicsView with drawable overlays
│   │   ├── excel_exporter.py        # pandas + openpyxl export logic
│   │   └── settings.py              # App configuration
│   ├── anpr/
│   │   ├── __init__.py
│   │   ├── anpr_tab.py              # ANPR module main UI (QWidget)
│   │   ├── plate_detector.py        # YOLO plate detection wrapper
│   │   ├── plate_ocr.py             # PaddleOCR wrapper + preprocessing
│   │   ├── plate_tracker.py         # Deduplication logic per vehicle
│   │   ├── plate_validator.py       # Australian plate regex validation
│   │   └── anpr_export.py           # ANPR-specific Excel formatting
│   └── counter/
│       ├── __init__.py
│       ├── counter_tab.py           # Counter module main UI (QWidget)
│       ├── vehicle_detector.py      # YOLO vehicle detection wrapper
│       ├── vehicle_classifier.py    # Austroads class mapping logic
│       ├── line_counter.py          # supervision LineZone integration
│       ├── count_line_widget.py     # Interactive line drawing UI
│       └── counter_export.py        # Counter-specific Excel formatting
├── tests/
│   ├── test_anpr.py
│   ├── test_counter.py
│   └── test_data/                   # Sample video clips for testing
└── build/
    ├── matrix.spec                  # PyInstaller spec file
    └── installer/                   # InnoSetup or InstallForge scripts
```

### 3.2 GUI Layout

```
┌─────────────────────────────────────────────────────────┐
│  Matrix Traffic Tools           [ANPR] [Counter] [Settings] │  ← Tab bar
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────┐  ┌──────────────────┐  │
│  │                             │  │ Site Number: [___]│  │
│  │                             │  │                  │  │
│  │       VIDEO PREVIEW         │  │ Status: Running  │  │
│  │    (with AI overlays)       │  │ Plates Found: 47 │  │
│  │                             │  │                  │  │
│  │  [count line drawn here]    │  │ ┌──────────────┐ │  │
│  │                             │  │ │ Results Table│ │  │
│  └─────────────────────────────┘  │ │ ABC123 07:01│ │  │
│  [▶ Play] [⏸] [⏩] ──●──── 2:34  │ │ XYZ789 07:02│ │  │
│                                   │ │ ...         │ │  │
│                                   │ └──────────────┘ │  │
│                                   │                  │  │
│                                   │ [▶ Start] [Export]│  │
│                                   └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Threading Model

```
Main Thread (GUI)
  ├── Video display updates (QPixmap to QLabel/QGraphicsView)
  ├── User input handling (buttons, line drawing, forms)
  └── Results table updates

Worker Thread (QThread)
  ├── OpenCV VideoCapture frame loop
  ├── YOLO inference (detection)
  ├── ByteTrack tracking
  ├── OCR (ANPR mode) or line counting (counter mode)
  └── Emits signals: frame_ready(QImage), detection_result(dict)
```

Signals connect the worker thread to the main thread safely. All GUI updates happen on the main thread via Qt signal-slot mechanism.

---

## Implementation Phases

### Phase 1: Core Framework (Week 1–2)
1. Set up project structure and dependencies
2. Build the main window with tab navigation (PySide6)
3. Build the reusable video player widget:
   - Open file dialog for video selection
   - Play/pause/seek controls
   - Frame display via OpenCV → QImage → QPixmap
   - Worker thread for non-blocking video decode
4. Build the QGraphicsView overlay system for drawing count lines
5. Build the settings/configuration panel

### Phase 2: ANPR Module (Week 3–4)
1. Integrate YOLO11 plate detection model
2. Integrate PaddleOCR for text recognition
3. Implement plate preprocessing pipeline (CLAHE, binarization, deskew)
4. Implement Australian plate regex validation
5. Implement vehicle tracking for plate deduplication (ByteTrack)
6. Build the ANPR results table (live updating)
7. Build the ANPR Excel export with formatting
8. Test with sample Australian traffic video

### Phase 3: Vehicle Counter Module (Week 5–6)
1. Integrate YOLO11 vehicle detection (COCO pre-trained)
2. Implement ByteTrack vehicle tracking
3. Integrate supervision `LineZone` for line-crossing counting
4. Build the interactive count line drawing UI
5. Implement Austroads class mapping (YOLO class → Austroads class)
6. Implement vehicle length estimation from bounding boxes (optional enhancement)
7. Build the counter results table (live per-class counts)
8. Build the counter Excel export with 15-minute interval breakdown
9. Test with sample traffic video

### Phase 4: Polish & Packaging (Week 7–8)
1. Error handling and edge cases (corrupted video, no detections, GPU fallback to CPU)
2. Progress indicators for long video processing
3. User preferences persistence (last used settings, default paths)
4. Performance optimization (batch inference, frame skipping controls)
5. PyInstaller packaging and testing on clean Windows machine
6. User documentation / help dialogs
7. Build installer (InnoSetup or InstallForge)

---

## Existing Software & AI Tools Reference

### ANPR Software to Study
| Tool | Type | Key Feature |
|---|---|---|
| Plate Recognizer | Cloud API + on-prem SDK | Best AU plate accuracy, video processing guide |
| FastANPR | Python library (pip) | YOLOv8 + PaddleOCR, self-contained |
| SimpleLPR | Commercial SDK ($450) | One-time cost, Python binding, temporal tracking |
| PlateCatcher | Free Windows app | Reference for UX and feature set |
| OpenALPR | Legacy open-source | Unmaintained, but useful for understanding the pipeline |

### Vehicle Counting Software to Study
| Tool | Type | Key Feature |
|---|---|---|
| Ultralytics Solutions | Python library | Built-in ObjectCounter with line/region counting |
| Roboflow supervision | Python library | LineZone, multi-class counting, excellent annotators |
| OpenDataCam | Open-source app | Complete traffic counter with web UI, REST API |
| Camlytics | Commercial desktop | On-premises, classifies car/van/truck/bus/bike |
| GoodVision | Commercial cloud | 8+ vehicle classes, used in APAC, 1-second API |
| Sensor Dynamics Traffic AI | Commercial (AU) | Australian-specific, >98% accuracy, NHVR compliance |
| richard-zi/carcounter | Open-source | YOLOv8 + ByteTrack + Streamlit, closest reference app |

### Australian-Specific Resources
| Resource | URL | Purpose |
|---|---|---|
| Austroads AP-G104-23 | austroads.gov.au | Current vehicle classification standard |
| ANPR-Australia GitHub | github.com/ANPR-Australia | NSW plate format regex patterns |
| SA DIT Classification Chart | dit.sa.gov.au | Visual reference for all 12 classes |
| MetroCount ARX Scheme | metrocount.com | Axle-based classification logic reference |
| Transport for NSW ML Cameras | transport.nsw.gov.au | Government AI camera deployment reference |

---

## Hardware Requirements

### Minimum (CPU-only inference)
- Windows 10/11 64-bit
- Intel i5 or AMD equivalent
- 8 GB RAM
- 2 GB disk space (app + models)
- Processing speed: ~2–5 FPS (acceptable for offline video analysis)

### Recommended (GPU-accelerated)
- NVIDIA GPU with 4+ GB VRAM (GTX 1650 or better)
- CUDA 11.8+ and cuDNN installed
- 16 GB RAM
- Processing speed: ~15–30 FPS

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Low ANPR accuracy on AU plates | Start with YOLO11 + PaddleOCR; fall back to Plate Recognizer API if <90% accuracy |
| Cannot distinguish Austroads Classes 5–12 | Implement length-based estimation; offer user manual override; document limitations |
| Large model files (>500MB) | Use YOLO11s or YOLO11m (9–20MB); separate model download on first run |
| PySide6 packaging issues | Test PyInstaller early in Phase 1; keep a working .spec file |
| Video codec compatibility | Use OpenCV VideoCapture which handles most formats via FFmpeg backend |
| GPU not available | Graceful fallback to CPU inference with a warning about reduced speed |
