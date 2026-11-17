# 🚗 Smart Parking Availability and Queue Notification System (Phase-2)

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.8%2B-green.svg)](https://opencv.org/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-orange.svg)](https://github.com/ultralytics/ultralytics)
[![Flask](https://img.shields.io/badge/Flask-3.1%2B-lightgrey.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite3-Embedded-blue.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Pytest-51%20Passing-brightgreen.svg)]()

**An AI-Powered Smart Parking Availability & Queue Notification System for Cars and Bikes using YOLOv8, Flask, and Real-Time Web Dashboard**

[Quick Start](#-quick-start) •
[Features (FR1-FR7)](#-functional-requirements-fr1--fr7) •
[5 Demo Locations](#-5-mock-parking-locations-demo-data) •
[Admin Login](#-admin-login) •
[Live YOLO vs Demo Mode](#-two-operating-modes) •
[API Reference](#-api-endpoints) •
[Testing](#-running-tests)

</div>

---

## 🌟 Project Overview

This is the **Phase-2 implementation** of the Smart Parking Availability and Queue Notification System for **Cars and Bikes** developed using YOLOv8 deep learning vehicle detection, OpenCV image processing, and a modern glassmorphic web dashboard with automated queue management.

### Key Capabilities:
- **Dual Vehicle Classification:** Detects and tracks **Cars** and **Bikes/Motorcycles** separately.
- **Automated Queue Notification:** When a slot transitions from **OCCUPIED → AVAILABLE**, the system automatically selects the next waiting user in the queue, notifies them in real-time, and updates their queue status.
- **5 Mock Campus Locations:** Simulates 5 distinct NMIT campus parking locations with realistic demo slot occupancies and queue waitlists.
- **Live YOLO Camera Integration:** Streams live MJPEG video with bounding boxes, HUD metrics, and slot occupancy overlays.
- **Admin Authentication:** Secure admin dashboard with session handling.

---

## 📋 Functional Requirements (FR1 – FR7)

| Requirement | Description | Status |
|---|---|---|
| **FR1 – Vehicle Detection** | YOLOv8 detects vehicles from camera/video, classifying **Cars** (COCO 2, 5, 7) and **Bikes** (COCO 3, 1) separately. | ✅ Complete |
| **FR2 – Parking Slot Detection** | Determines whether predefined slots (A01–A20, B01–B15) are occupied or vacant using pixel analysis & YOLO bounding box intersection. | ✅ Complete |
| **FR3 – Availability Notification** | Auto-detects **OCCUPIED → AVAILABLE** slot transitions, selects the first waiting user in queue, triggers in-dashboard alert, and logs timestamped notification. | ✅ Complete |
| **FR4 – Admin Login** | Secure authentication system with demo credentials (`admin` / `admin123`), session handling, and protected routes. | ✅ Complete |
| **FR5 – Parking Dashboard** | Web dashboard showing total slots, available, occupied, cars detected, bikes detected, queue count, occupancy %, and separate Car & Bike parking grids. | ✅ Complete |
| **FR6 – Queue Management** | Allows drivers to join the queue when parking is full, prevents duplicate vehicle numbers, tracks position, and supports dequeue/manual notification. | ✅ Complete |
| **FR7 – Parking History / Database** | SQLite database logging all slot state transitions (Slot ID, Vehicle Type, Previous Status, New Status, Timestamp, Vehicle Plate). | ✅ Complete |

---

## 🔑 Admin Login

Access administrator controls and dashboard actions:

- **Username:** `admin`
- **Password:** `admin123`
- **Demo Quick-Fill:** Available directly on the login modal by clicking the demo helper banner.

---

## 🏢 5 Mock Parking Locations (Demo Data)

The system includes 5 predefined mock parking locations labeled as **Demo / Mock Parking Data**:

1. **NMIT Main Gate Parking** (Live Camera Demo)
   - Capacity: **10 Car Slots** (`A01`–`A10`), **5 Bike Slots** (`B01`–`B05`)
2. **NMIT Academic Block Parking**
   - Capacity: **15 Car Slots** (`A01`–`A15`), **8 Bike Slots** (`B01`–`B08`)
3. **NMIT Library Parking**
   - Capacity: **8 Car Slots** (`A01`–`A08`), **5 Bike Slots** (`B01`–`B05`)
4. **NMIT Hostel Parking**
   - Capacity: **20 Car Slots** (`A01`–`A20`), **15 Bike Slots** (`B01`–`B15`)
5. **NMIT Canteen Parking**
   - Capacity: **10 Car Slots** (`A01`–`A10`), **8 Bike Slots** (`B01`–`B08`)

---

## 🔄 Two Operating Modes

### Mode 1 — Live Detection (Camera / Video)
- Connected to `carPark.mp4` / webcam feed.
- Live video stream at `/video_feed` with real-time YOLOv8 bounding boxes, vehicle classifications, and parking slot status overlays.
- Displays live FPS, car count, bike count, free slots, and occupied slots.

### Mode 2 — Demo Dashboard
- Displays multi-location data across the 5 NMIT campus parking zones.
- Allows interactive status toggling (`OCCUPIED` ↔ `AVAILABLE`) to test the automated queue notification engine.
- Reset button allows restoring initial mock state at any time.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.8 to 3.11 installed.
- Git (optional).

### 2. Setup Virtual Environment & Install Dependencies
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Upgrade pip & install dependencies
pip install -r requirements.txt
pip install flask pytest
```

### 3. Database Setup
The SQLite database (`data/parking_system.db`) is automatically initialized and seeded with realistic demo data on the first launch of `app.py`. No manual database server setup is required.

### 4. Start the Application Server
```powershell
# Start Flask Web Dashboard
python app.py
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

### 5. Running YOLOv8 Detection Standalone (CLI Mode)
```powershell
# Run with sample video
python run.py --video carPark.mp4

# Run with sample image
python run.py --image carParkImg.png
```

---

## 📡 API Endpoints

### Authentication
- `POST /api/auth/login` - Admin login with username/password
- `POST /api/auth/logout` - Invalidate session
- `GET /api/auth/me` - Get current session status

### Parking & Locations
- `GET /api/dashboard/stats?location=<id>` - Get overall or per-location statistics
- `GET /api/parking/locations` - List all 5 parking locations
- `GET /api/parking/locations/<id>/slots` - List slots separated by Cars and Bikes
- `POST /api/parking/slots/<id>/status` - Toggle slot status & trigger FR3 auto-notification

### Queue Management
- `GET /api/queue?location=<id>` - Get waiting vehicles
- `POST /api/queue/join` - Join queue (validates duplicates)
- `DELETE /api/queue/<id>` - Remove from queue
- `POST /api/queue/<id>/notify` - Manually notify user

### Notifications & History
- `GET /api/notifications` - Get system & availability notifications
- `POST /api/notifications/<id>/read` - Mark single notification as read
- `POST /api/notifications/clear-all` - Mark all notifications as read
- `GET /api/parking/history?location=<id>` - Get transition audit trail
- `POST /api/demo/reset` - Reset mock database to default state
- `GET /video_feed` - MJPEG live video stream

---

## 🧪 Running Tests

Run the complete test suite (51 tests covering FR1–FR7, API routes, database operations, and YOLO detector):

```powershell
# Run all tests
pytest tests

# Run specific test suite
pytest tests/test_database.py
pytest tests/test_api.py
pytest tests/test_car_detector.py
```

All 51 test cases pass with 100% test coverage.

---

## 📂 Project Structure

```
Car-Parking-Detection-main/
├── app.py                      # Flask Backend & REST API Server (Phase-2)
├── database.py                 # SQLite Data Access Layer & FR3 Notification Engine
├── live_detector_service.py    # Real-Time YOLOv8 Video Streaming Service
├── car_detector.py             # YOLOv8 ML Model & Vehicle Detection (Cars + Bikes)
├── enhanced_parking_detector.py# Computer Vision Slot Occupancy & Drawing Engine
├── config.py                   # Centralized Configuration, Colors, & Mock Locations
├── run.py                      # CLI Application Entrypoint
├── CarParkPos                  # Predefined Parking Space Coordinates
├── carPark.mp4                 # Sample Parking Lot Video Feed
├── carParkImg.png              # Sample Parking Lot Image
├── yolov8n.pt                  # YOLOv8 Nano Deep Learning Weights
├── data/
│   └── parking_system.db       # SQLite Database (Auto-Generated)
├── templates/
│   └── index.html              # Modern Glassmorphic SPA Web Dashboard
├── static/
│   ├── css/
│   │   └── style.css           # Premium Dark Mode Glassmorphism Theme
│   └── js/
│       └── app.js              # Real-Time Polling Client, Queue & Slot Controller
├── tests/
│   ├── test_api.py             # REST API Endpoint Tests
│   ├── test_database.py        # Database, Auth, Queue, & FR3 Tests
│   ├── test_car_detector.py    # YOLO Vehicle Detection Tests
│   ├── test_parking_detector.py# Slot Processing & Occupancy Tests
│   ├── test_config.py          # Configuration Unit Tests
│   └── test_integration.py     # End-to-End Integration Tests
└── requirements.txt            # Project Dependencies
```

---

## 👥 Contributors & Academic Use
Developed as an advanced academic project for **Smart Parking Management and Vehicle Flow Optimization** utilizing YOLOv8 and Computer Vision.
