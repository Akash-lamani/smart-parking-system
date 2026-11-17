"""
Live Detector Service for Smart Parking Availability and Queue Notification System
Handles real-time YOLOv8 video frame inference, vehicle classification (Cars vs Bikes),
parking slot occupancy mapping, and MJPEG frame streaming for the web dashboard.
"""

import logging
import os
import pickle
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np

import config
from car_detector import CarDetector

logger = logging.getLogger(__name__)


class LiveDetectorService:
    """Singleton service for live video capture, YOLO inference, and web MJPEG streaming"""

    _instance: Optional["LiveDetectorService"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LiveDetectorService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, video_path: Optional[str] = None) -> None:
        if getattr(self, "_initialized", False):
            return

        self.video_path = video_path or config.DEFAULT_VIDEO_PATH
        self.detector = CarDetector()
        self.lock = threading.Lock()
        self.running = False
        self.current_frame: Optional[np.ndarray] = None
        self.latest_stats: Dict[str, Any] = {
            "total_slots": 0,
            "available_slots": 0,
            "occupied_slots": 0,
            "cars_detected": 0,
            "bikes_detected": 0,
            "fps": 0.0,
            "status": "Initializing",
            "last_updated": "",
        }
        self.parking_spaces: List[Tuple[int, int]] = []
        self.load_parking_spaces()
        self._start_background_thread()
        self._initialized = True

    def get_default_parking_spaces(self) -> List[Dict[str, Any]]:
        """Default 15 parking slots (A01-A10 Cars, B01-B05 Bikes) calibrated for carParkImg.png"""
        slots = []
        # Car slots row 1: A01 to A06
        for i in range(6):
            slots.append({
                "id": f"A{i+1:02d}",
                "x": 50 + i * 140,
                "y": 100,
                "width": config.PARKING_WIDTH,
                "height": config.PARKING_HEIGHT,
                "vehicle_type": "Car"
            })
        # Car slots row 2: A07 to A10
        for j in range(4):
            slots.append({
                "id": f"A{j+7:02d}",
                "x": 50 + j * 140,
                "y": 240,
                "width": config.PARKING_WIDTH,
                "height": config.PARKING_HEIGHT,
                "vehicle_type": "Car"
            })
        # Bike slots row: B01 to B05
        for k in range(5):
            slots.append({
                "id": f"B{k+1:02d}",
                "x": 620 + k * 85,
                "y": 240,
                "width": 75,
                "height": config.PARKING_HEIGHT,
                "vehicle_type": "Bike"
            })
        return slots

    def load_parking_spaces(self) -> None:
        """Load predefined parking slot coordinates from pickle file or defaults"""
        try:
            if os.path.exists(config.POSITION_FILE):
                with open(config.POSITION_FILE, "rb") as f:
                    loaded = pickle.load(f)
                if loaded and isinstance(loaded, list) and len(loaded) > 0:
                    self.parking_spaces = loaded
                    logger.info(f"Loaded {len(self.parking_spaces)} parking spaces from {config.POSITION_FILE}")
                else:
                    self.parking_spaces = self.get_default_parking_spaces()
            else:
                self.parking_spaces = self.get_default_parking_spaces()
        except Exception as e:
            logger.error(f"Error loading parking spaces: {e}")
            self.parking_spaces = self.get_default_parking_spaces()

    def get_parking_spaces(self) -> List[Dict[str, Any]]:
        """Return standardized list of slot dictionaries for admin editor"""
        with self.lock:
            result = []
            for idx, pos in enumerate(self.parking_spaces):
                if isinstance(pos, dict):
                    item = {
                        "id": str(pos.get("id") or pos.get("slot_number") or f"A{idx+1:02d}"),
                        "x": int(pos.get("x", 0)),
                        "y": int(pos.get("y", 0)),
                        "width": int(pos.get("width", config.PARKING_WIDTH)),
                        "height": int(pos.get("height", config.PARKING_HEIGHT)),
                        "vehicle_type": str(pos.get("vehicle_type", "Car")).capitalize()
                    }
                elif isinstance(pos, (list, tuple)):
                    if len(pos) >= 6:
                        item = {
                            "id": str(pos[4]),
                            "x": int(pos[0]),
                            "y": int(pos[1]),
                            "width": int(pos[2]),
                            "height": int(pos[3]),
                            "vehicle_type": str(pos[5]).capitalize()
                        }
                    elif len(pos) >= 4:
                        item = {
                            "id": f"A{idx+1:02d}",
                            "x": int(pos[0]),
                            "y": int(pos[1]),
                            "width": int(pos[2]),
                            "height": int(pos[3]),
                            "vehicle_type": "Car"
                        }
                    else:
                        item = {
                            "id": f"A{idx+1:02d}",
                            "x": int(pos[0]),
                            "y": int(pos[1]),
                            "width": config.PARKING_WIDTH,
                            "height": config.PARKING_HEIGHT,
                            "vehicle_type": "Car"
                        }
                else:
                    continue
                result.append(item)
            return result

    def update_parking_spaces(self, new_spaces: List[Dict[str, Any]]) -> None:
        """Update active parking spaces in memory and persist to CarParkPos file"""
        with self.lock:
            self.parking_spaces = new_spaces
            try:
                with open(config.POSITION_FILE, "wb") as f:
                    pickle.dump(self.parking_spaces, f)
                logger.info(f"Successfully saved {len(self.parking_spaces)} parking spaces to {config.POSITION_FILE}")
            except Exception as e:
                logger.error(f"Error saving parking spaces to file: {e}")

    def _start_background_thread(self) -> None:
        """Start the background video capture and processing thread"""
        self.running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        logger.info("Live detector background thread started")

    def _process_loop(self) -> None:
        """Continuous video frame processing loop with looping video feed"""
        while self.running:
            if not os.path.exists(self.video_path):
                # Fallback: create synthetic frame if video not found
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    frame,
                    "Video source not available",
                    (50, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2,
                )
                with self.lock:
                    self.current_frame = frame
                time.sleep(1)
                continue

            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                time.sleep(1)
                continue

            fps_timer = time.time()
            frame_count = 0
            current_fps = 0.0

            try:
                while self.running and cap.isOpened():
                    # Loop video if reached end
                    if cap.get(cv2.CAP_PROP_POS_FRAMES) >= cap.get(cv2.CAP_PROP_FRAME_COUNT) - 1:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

                    success, frame = cap.read()
                    if not success:
                        break

                    frame_count += 1
                    if time.time() - fps_timer >= 1.0:
                        current_fps = frame_count / (time.time() - fps_timer)
                        fps_timer = time.time()
                        frame_count = 0

                    # 1. Computer Vision preprocessing for slot occupancy
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    blur = cv2.GaussianBlur(gray, (3, 3), 1)
                    thresh = cv2.adaptiveThreshold(
                        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 16
                    )
                    median = cv2.medianBlur(thresh, 5)
                    kernel = np.ones((3, 3), np.uint8)
                    dilated = cv2.dilate(median, kernel, iterations=1)

                    # 2. Check Parking Spaces Occupancy
                    occupied_slots = 0
                    available_slots = 0

                    h_img, w_img = dilated.shape[:2]
                    spaces_snapshot = list(self.parking_spaces)

                    # Process each predefined parking space
                    for idx, pos in enumerate(spaces_snapshot):
                        if isinstance(pos, dict):
                            x = int(pos.get("x", 0))
                            y = int(pos.get("y", 0))
                            w = int(pos.get("width", config.PARKING_WIDTH))
                            h = int(pos.get("height", config.PARKING_HEIGHT))
                            slot_id = str(pos.get("id") or f"A{idx+1:02d}")
                        elif isinstance(pos, (list, tuple)) and len(pos) >= 6:
                            x, y, w, h = int(pos[0]), int(pos[1]), int(pos[2]), int(pos[3])
                            slot_id = str(pos[4])
                        elif isinstance(pos, (list, tuple)) and len(pos) >= 4:
                            x, y, w, h = int(pos[0]), int(pos[1]), int(pos[2]), int(pos[3])
                            slot_id = f"A{idx+1:02d}"
                        elif isinstance(pos, (list, tuple)) and len(pos) >= 2:
                            x, y = int(pos[0]), int(pos[1])
                            w, h = config.PARKING_WIDTH, config.PARKING_HEIGHT
                            slot_id = f"A{idx+1:02d}"
                        else:
                            continue

                        # Crop and analyze slot pixels
                        x1 = max(0, min(x, w_img - 1))
                        y1 = max(0, min(y, h_img - 1))
                        x2 = max(x1 + 1, min(x + w, w_img))
                        y2 = max(y1 + 1, min(y + h, h_img))
                        img_crop = dilated[y1:y2, x1:x2]
                        count = cv2.countNonZero(img_crop) if img_crop.size > 0 else 0

                        # Calculate threshold proportionally to slot area
                        expected_area = config.PARKING_WIDTH * config.PARKING_HEIGHT
                        current_area = max(1, w * h)
                        threshold = config.OCCUPANCY_THRESHOLD * (current_area / expected_area)

                        if count < threshold:
                            color = (0, 255, 0)  # Green = Available
                            available_slots += 1
                            slot_label = f"{slot_id} -> AVAILABLE"
                        else:
                            color = (0, 0, 255)  # Red = Occupied
                            occupied_slots += 1
                            slot_label = f"{slot_id} -> OCCUPIED"

                        # Draw bounding rectangle
                        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                        
                        # Draw clean label
                        label_y = max(15, y - 6)
                        cv2.putText(
                            frame,
                            slot_label,
                            (x, label_y),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.45,
                            color,
                            2,
                        )

                    # 3. YOLOv8 ML Detection for Cars and Bikes
                    cars_detected = 0
                    bikes_detected = 0

                    try:
                        detections = self.detector.detect(frame, confidence=0.4)
                        for det in detections:
                            bx1, by1, bx2, by2 = det["bbox"]
                            vtype = det["vehicle_type"]
                            conf = det["confidence"]

                            if det["is_bike"]:
                                bikes_detected += 1
                                box_color = (255, 165, 0)  # Orange/Amber for Bike
                                icon = "BIKE"
                            else:
                                cars_detected += 1
                                box_color = (255, 255, 0)  # Cyan/Yellow for Car
                                icon = "CAR"

                            # Draw bounding box
                            cv2.rectangle(frame, (bx1, by1), (bx2, by2), box_color, 2)
                            label_str = f"{icon} {conf:.2f}"
                            cv2.putText(
                                frame,
                                label_str,
                                (bx1, by1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.45,
                                box_color,
                                2,
                            )
                    except Exception as err:
                        logger.debug(f"YOLO detection skip: {err}")

                    # 4. Draw HUD Dashboard Overlay on Frame
                    total_spaces = len(self.parking_spaces)
                    hud_bg = np.zeros((65, frame.shape[1], 3), dtype=np.uint8)
                    cv2.addWeighted(frame[:65, :], 0.3, hud_bg, 0.7, 0, frame[:65, :])

                    # Title and Live badge
                    cv2.putText(
                        frame,
                        "LIVE YOLOv8 DETECTION [NMIT MAIN GATE]",
                        (15, 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 255),
                        2,
                    )

                    # Stats badges
                    stats_text = (
                        f"TOTAL: {total_spaces} | FREE: {available_slots} | OCC: {occupied_slots} | "
                        f"CARS: {cars_detected} | BIKES: {bikes_detected} | FPS: {current_fps:.1f}"
                    )
                    cv2.putText(
                        frame,
                        stats_text,
                        (15, 52),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                    )

                    # Update singleton stats
                    with self.lock:
                        self.current_frame = frame
                        self.latest_stats = {
                            "total_slots": total_spaces,
                            "available_slots": available_slots,
                            "occupied_slots": occupied_slots,
                            "cars_detected": cars_detected,
                            "bikes_detected": bikes_detected,
                            "fps": round(current_fps, 1),
                            "status": "LIVE STREAMING",
                            "last_updated": time.strftime("%H:%M:%S"),
                        }

                    # Throttle to ~25-30 FPS
                    time.sleep(0.033)

            finally:
                cap.release()

    def get_latest_frame_jpeg(self) -> Optional[bytes]:
        """Encode latest frame as JPEG bytes"""
        with self.lock:
            if self.current_frame is None:
                return None
            ret, buffer = cv2.imencode(".jpg", self.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ret:
                return None
            return buffer.tobytes()

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yield MJPEG multipart stream for HTTP response"""
        while True:
            frame_bytes = self.get_latest_frame_jpeg()
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                )
            time.sleep(0.04)

    def get_stats(self) -> Dict[str, Any]:
        """Get copy of latest live detection stats"""
        with self.lock:
            return dict(self.latest_stats)

    def get_snapshot_jpeg(self) -> Optional[bytes]:
        """Get a clean raw frame snapshot (or static image) for slot editing"""
        if os.path.exists(config.DEFAULT_IMAGE_PATH):
            img = cv2.imread(config.DEFAULT_IMAGE_PATH)
            if img is not None:
                ret, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if ret:
                    return buffer.tobytes()
        with self.lock:
            if self.current_frame is not None:
                ret, buffer = cv2.imencode(".jpg", self.current_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    return buffer.tobytes()
        return None

    def stop(self) -> None:
        """Stop processing thread"""
        self.running = False


# Helper factory function
def get_live_service() -> LiveDetectorService:
    return LiveDetectorService()
