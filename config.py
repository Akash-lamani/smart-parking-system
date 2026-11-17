"""
Configuration file for Car Parking Detection System
All configurable parameters are centralized here for easy management
"""

from typing import Final, List, Tuple

# Parking Space Dimensions
PARKING_WIDTH: Final[int] = 107
PARKING_HEIGHT: Final[int] = 48

# Detection Thresholds
OCCUPANCY_THRESHOLD: Final[int] = 900  # Pixel count threshold for space occupancy
CONFIDENCE_THRESHOLD: Final[float] = 0.5  # Minimum confidence for vehicle detection

# YOLO Model Configuration
MODEL_PATH: Final[str] = "yolov8n.pt"
CAR_CLASSES: Final[List[int]] = [2, 5, 7]  # COCO classes: cars (2), buses (5), trucks (7)
BIKE_CLASSES: Final[List[int]] = [3, 1]    # COCO classes: motorcycles (3), bicycles (1)
ALL_VEHICLE_CLASSES: Final[List[int]] = [2, 3, 5, 7, 1]
VEHICLE_TYPE_NAMES: Final[dict] = {
    2: "Car",
    3: "Bike",
    1: "Bicycle",
    5: "Bus",
    7: "Truck",
}

# File Paths
POSITION_FILE: Final[str] = "CarParkPos"
DEFAULT_VIDEO_PATH: Final[str] = "carPark.mp4"
DEFAULT_IMAGE_PATH: Final[str] = "carParkImg.png"

# Directory Structure
REPORTS_DIR: Final[str] = "reports"
DATA_DIR: Final[str] = "data"
MODELS_DIR: Final[str] = "models"
DATABASE_PATH: Final[str] = "data/parking_system.db"

# CSV Configuration
CSV_FILE: Final[str] = "parking_status.csv"
CSV_APPEND_MODE: Final[bool] = True  # Set to True to keep historical data

# Admin Demo Credentials
ADMIN_USERNAME: Final[str] = "admin"
ADMIN_PASSWORD: Final[str] = "admin123"
SECRET_KEY: Final[str] = "smart-parking-nmit-phase2-super-secret-key-2026"

# 5 Mock Parking Locations for Demonstration with Distances
MOCK_LOCATIONS: Final[List[dict]] = [
    {
        "id": 1,
        "code": "NMIT_MAIN",
        "name": "NMIT Main Gate Parking",
        "description": "Primary parking area located at the NMIT main entrance",
        "distance_km": 0.4,
        "car_slots": 10,
        "bike_slots": 5,
        "is_live": True,  # Location connected with live camera/video demo
    },
    {
        "id": 2,
        "code": "NMIT_HOSTEL",
        "name": "NMIT Hostel Parking",
        "description": "High-capacity residential student parking zone",
        "distance_km": 0.8,
        "car_slots": 20,
        "bike_slots": 15,
        "is_live": False,
    },
    {
        "id": 3,
        "code": "NMIT_ACAD",
        "name": "NMIT Academic Block Parking",
        "description": "Dedicated parking for faculty, staff, and students near Academic Block",
        "distance_km": 1.2,
        "car_slots": 15,
        "bike_slots": 8,
        "is_live": False,
    },
    {
        "id": 4,
        "code": "NMIT_LIB",
        "name": "NMIT Library Parking",
        "description": "Quiet zone parking adjacent to the central library",
        "distance_km": 1.6,
        "car_slots": 8,
        "bike_slots": 5,
        "is_live": False,
    },
    {
        "id": 5,
        "code": "DMART",
        "name": "DMart Parking",
        "description": "Commercial shopping center customer parking area",
        "distance_km": 4.2,
        "car_slots": 10,
        "bike_slots": 8,
        "is_live": False,
    },
]

# UI Configuration
BORDER_SIZE: Final[int] = 50
WINDOW_NAME: Final[str] = "Parking Detection"

# Zoom Configuration
MIN_ZOOM: Final[float] = 0.5
MAX_ZOOM: Final[float] = 3.0
ZOOM_STEP: Final[float] = 0.1
PAN_STEP: Final[int] = 50

# Colors (BGR format)
COLOR_EMPTY: Final[Tuple[int, int, int]] = (0, 255, 0)  # Green
COLOR_OCCUPIED: Final[Tuple[int, int, int]] = (0, 0, 255)  # Red
COLOR_SPECIAL: Final[Tuple[int, int, int]] = (0, 255, 255)  # Yellow
COLOR_REGULAR: Final[Tuple[int, int, int]] = (255, 0, 255)  # Magenta
COLOR_SELECTION: Final[Tuple[int, int, int]] = (0, 255, 0)  # Green
COLOR_BIKE: Final[Tuple[int, int, int]] = (255, 165, 0)  # Orange/Cyan for Bikes

# Special Parking Detection
YELLOW_PERCENTAGE_THRESHOLD: Final[int] = (
    3  # Minimum percentage of yellow pixels for special parking
)
MIN_LINE_LENGTH_RATIO: Final[float] = 0.3  # Minimum line length as ratio of space dimension

# Report Configuration
REPORT_DPI: Final[int] = 300
REPORT_FIGSIZE: Final[Tuple[int, int]] = (15, 10)

