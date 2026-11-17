"""
Smart Parking Availability and Queue Notification System - Backend Web Server (Phase-2)
Flask application providing REST APIs, authentication, real-time statistics,
queue management, parking history, in-dashboard notifications, and live YOLO MJPEG video stream.
"""

import functools
import logging
import os
from typing import Any, Callable, Dict, Optional

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import config
from database import db
from live_detector_service import get_live_service

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = getattr(config, "SECRET_KEY", "smart-parking-phase2-default-secret-key-2026")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def login_required(f: Callable) -> Callable:
    """Decorator to enforce admin authentication on protected endpoints"""
    @functools.wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        # Allow if session has admin or if Authorization Bearer header is present
        auth_header = request.headers.get("Authorization", "")
        if session.get("is_authenticated") or auth_header.startswith("Bearer "):
            return f(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized. Please log in as admin.", "authenticated": False}), 401
        return redirect(url_for("login_page"))
    return decorated_function


# ==================== PAGE ROUTES ====================

@app.route("/")
def index() -> str:
    """Render main SPA dashboard page"""
    is_auth = session.get("is_authenticated", False)
    return render_template("index.html", is_authenticated=is_auth, username=session.get("username", "Guest"))


@app.route("/login")
def login_page() -> Any:
    """Render or redirect to login page"""
    if session.get("is_authenticated"):
        return redirect(url_for("index"))
    return render_template("index.html", view="login", is_authenticated=False)


# ==================== AUTHENTICATION APIS (FR4) ====================

@app.route("/api/auth/login", methods=["POST"])
def api_login() -> Response:
    """Admin login endpoint (Credentials: admin / admin123)"""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required."}), 400

    if db.authenticate_admin(username, password):
        session["is_authenticated"] = True
        session["username"] = username
        session["role"] = "admin"
        logger.info(f"Admin logged in successfully: {username}")
        return jsonify({
            "success": True,
            "message": "Login successful.",
            "token": "demo-admin-jwt-token-phase2",
            "user": {"username": username, "role": "admin"}
        }), 200
    else:
        logger.warning(f"Failed login attempt for username: {username}")
        return jsonify({"success": False, "error": "Invalid username or password. Demo credentials: admin / admin123"}), 401


@app.route("/api/auth/logout", methods=["POST", "GET"])
def api_logout() -> Response:
    """Admin logout endpoint"""
    username = session.get("username", "User")
    session.clear()
    logger.info(f"User logged out: {username}")
    return jsonify({"success": True, "message": "Logged out successfully."}), 200


@app.route("/api/auth/me", methods=["GET"])
def api_me() -> Response:
    """Get current session user status"""
    is_auth = session.get("is_authenticated", False)
    return jsonify({
        "authenticated": is_auth,
        "username": session.get("username", "Guest") if is_auth else None,
        "role": session.get("role", "guest") if is_auth else None
    })


# ==================== DASHBOARD STATS (FR5) ====================

@app.route("/api/dashboard/stats", methods=["GET"])
def api_dashboard_stats() -> Response:
    """
    Get consolidated dashboard statistics:
    Total Slots, Available Slots, Occupied Slots, Cars, Bikes, Queue, Occupancy %
    Supports query parameter: ?location=<id>
    """
    loc_id = request.args.get("location")
    location_id = int(loc_id) if loc_id and loc_id.isdigit() else None
    stats = db.get_dashboard_stats(location_id=location_id)
    return jsonify({"success": True, "stats": stats, "location_id": location_id})


# ==================== PARKING LOCATIONS & SLOTS ====================

@app.route("/api/parking/locations", methods=["GET"])
def api_get_locations() -> Response:
    """Get list of mock parking locations with distance filtering and search support"""
    max_dist = request.args.get("max_distance")
    search_q = request.args.get("search")
    max_distance_km = float(max_dist) if max_dist else None

    locations = db.get_locations(max_distance_km=max_distance_km, search_query=search_q)
    return jsonify({"success": True, "locations": locations, "count": len(locations)})


@app.route("/api/parking/locations/<int:loc_id>", methods=["GET"])
def api_get_location(loc_id: int) -> Response:
    """Get single parking location details"""
    location = db.get_location_by_id(loc_id)
    if not location:
        return jsonify({"success": False, "error": f"Location {loc_id} not found"}), 404
    return jsonify({"success": True, "location": location})


@app.route("/api/parking/locations/<int:loc_id>/slots", methods=["GET"])
def api_get_location_slots(loc_id: int) -> Response:
    """Get all parking slots for a location (with separate Car and Bike groupings and reservation info)"""
    vtype = request.args.get("type")
    slots = db.get_slots(loc_id, vehicle_type=vtype)
    
    # Split into Cars and Bikes for easy consumption
    car_slots = [s for s in slots if s["vehicle_type"].lower() == "car"]
    bike_slots = [s for s in slots if s["vehicle_type"].lower() == "bike"]

    return jsonify({
        "success": True,
        "location_id": loc_id,
        "slots": slots,
        "car_slots": car_slots,
        "bike_slots": bike_slots,
        "total_count": len(slots),
        "car_count": len(car_slots),
        "bike_count": len(bike_slots)
    })


@app.route("/api/parking/slots/<int:slot_id>/status", methods=["POST"])
def api_update_slot_status(slot_id: int) -> Response:
    """
    Toggle or update a parking slot's status ('available' / 'occupied' / 'reserved').
    Triggers FR3 availability notification to waiting queue users if OCCUPIED -> AVAILABLE.
    Records transition in FR7 parking history.
    """
    data = request.get_json() or {}
    slot = db.get_slot_by_id(slot_id)
    if not slot:
        return jsonify({"success": False, "error": f"Slot {slot_id} not found"}), 404

    current_status = slot["status"]
    new_status = data.get("status")
    if not new_status:
        # Toggle if not provided
        new_status = "available" if current_status in ["occupied", "reserved"] else "occupied"

    vehicle_number = data.get("vehicle_number")
    vehicle_type = data.get("vehicle_type", slot["vehicle_type"])

    try:
        result = db.update_slot_status(
            location_id=slot["location_id"],
            slot_number=slot["slot_number"],
            new_status=new_status,
            vehicle_type=vehicle_type,
            vehicle_number=vehicle_number
        )
        return jsonify({"success": True, "result": result})
    except Exception as e:
        logger.error(f"Error updating slot status: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


# ==================== 2-MINUTE RESERVATION APIS ====================

@app.route("/api/parking/slots/<int:slot_id>/reserve", methods=["POST"])
def api_reserve_slot(slot_id: int) -> Response:
    """
    Reserve an available parking slot for 2 minutes (120 seconds).
    Prevents double booking if slot is already reserved or occupied.
    """
    slot = db.get_slot_by_id(slot_id)
    if not slot:
        return jsonify({"success": False, "error": f"Slot {slot_id} not found"}), 404

    data = request.get_json() or {}
    user_name = data.get("user_name", "Driver").strip()
    vehicle_number = data.get("vehicle_number", "").strip()
    vehicle_type = data.get("vehicle_type", slot["vehicle_type"]).strip()
    duration_seconds = int(data.get("duration_seconds", 120))

    if not vehicle_number:
        return jsonify({"success": False, "error": "Vehicle plate number is required for reservation."}), 400

    try:
        res = db.reserve_slot(
            location_id=slot["location_id"],
            slot_number=slot["slot_number"],
            user_name=user_name,
            vehicle_number=vehicle_number,
            vehicle_type=vehicle_type,
            duration_seconds=duration_seconds,
        )
        return jsonify({"success": True, "reservation": res, "message": "Slot reserved for 2 minutes."}), 201
    except ValueError as val_err:
        return jsonify({"success": False, "error": str(val_err)}), 409
    except Exception as e:
        logger.error(f"Error reserving slot: {e}")
        return jsonify({"success": False, "error": f"Reservation failed: {e}"}), 500


@app.route("/api/parking/slots/<int:slot_id>/arrive", methods=["POST"])
def api_confirm_arrival(slot_id: int) -> Response:
    """User arrives at reserved slot: RESERVED → OCCUPIED"""
    try:
        res = db.confirm_arrival(slot_id)
        return jsonify({"success": True, "result": res, "message": "Parking Confirmed ✓"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/parking/slots/<int:slot_id>/cancel-reservation", methods=["POST"])
def api_cancel_reservation(slot_id: int) -> Response:
    """Cancel reservation: RESERVED → AVAILABLE"""
    try:
        res = db.cancel_reservation(slot_id)
        return jsonify({"success": True, "result": res, "message": "Reservation cancelled."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/reservations/active", methods=["GET"])
def api_get_active_reservations() -> Response:
    """Get all active reservations with calculated countdown timers"""
    loc_id = request.args.get("location")
    location_id = int(loc_id) if loc_id and loc_id.isdigit() else None
    reservations = db.get_active_reservations(location_id=location_id)
    return jsonify({"success": True, "reservations": reservations, "count": len(reservations)})


# ==================== QUEUE MANAGEMENT (FR6) ====================

@app.route("/api/queue", methods=["GET"])
def api_get_queue() -> Response:
    """Get current parking queue items"""
    loc_id = request.args.get("location")
    location_id = int(loc_id) if loc_id and loc_id.isdigit() else None
    status = request.args.get("status")
    queue_items = db.get_queue(location_id=location_id, status=status)
    return jsonify({"success": True, "queue": queue_items, "count": len(queue_items)})


@app.route("/api/queue/join", methods=["POST"])
def api_join_queue() -> Response:
    """Join the parking queue with user details, vehicle plate, and type (Car/Bike)"""
    data = request.get_json() or {}
    user_name = data.get("user_name", "").strip()
    vehicle_number = data.get("vehicle_number", "").strip()
    vehicle_type = data.get("vehicle_type", "Car").strip()
    location_id = int(data.get("location_id", 1))
    phone = data.get("phone", "").strip()

    if not user_name or not vehicle_number:
        return jsonify({"success": False, "error": "User name and vehicle plate number are required."}), 400

    try:
        entry = db.join_queue(
            user_name=user_name,
            vehicle_number=vehicle_number,
            vehicle_type=vehicle_type,
            location_id=location_id,
            phone=phone
        )
        return jsonify({"success": True, "message": "Successfully joined the queue.", "entry": entry}), 201
    except ValueError as val_err:
        return jsonify({"success": False, "error": str(val_err)}), 409
    except Exception as e:
        logger.error(f"Error joining queue: {e}")
        return jsonify({"success": False, "error": f"Failed to join queue: {e}"}), 500


@app.route("/api/queue/<int:queue_id>", methods=["DELETE"])
def api_delete_queue(queue_id: int) -> Response:
    """Remove / cancel a queue entry"""
    success = db.remove_from_queue(queue_id)
    if success:
        return jsonify({"success": True, "message": f"Queue entry {queue_id} removed."})
    return jsonify({"success": False, "error": f"Queue entry {queue_id} not found."}), 404


@app.route("/api/queue/<int:queue_id>/notify", methods=["POST"])
def api_notify_queue(queue_id: int) -> Response:
    """Manually notify a waiting queue user"""
    data = request.get_json() or {}
    slot_number = data.get("slot_number", "A01")
    try:
        res = db.notify_queue_user(queue_id, slot_number=slot_number)
        return jsonify({"success": True, "notification": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


# ==================== NOTIFICATIONS (FR3) ====================

@app.route("/api/notifications", methods=["GET"])
def api_get_notifications() -> Response:
    """Get system and parking availability notifications"""
    limit = int(request.args.get("limit", 50))
    unread_only = request.args.get("unread", "").lower() in ["true", "1"]
    notifs = db.get_notifications(limit=limit, unread_only=unread_only)
    unread_count = sum(1 for n in notifs if n["status"] == "unread")
    return jsonify({
        "success": True,
        "notifications": notifs,
        "unread_count": unread_count,
        "total": len(notifs)
    })


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def api_mark_notification_read(notif_id: int) -> Response:
    """Mark single notification as read"""
    success = db.mark_notification_read(notif_id)
    return jsonify({"success": success, "id": notif_id})


@app.route("/api/notifications/clear-all", methods=["POST"])
def api_mark_all_notifications_read() -> Response:
    """Mark all notifications as read"""
    count = db.mark_all_notifications_read()
    return jsonify({"success": True, "cleared_count": count})


# ==================== PARKING HISTORY (FR7) ====================

@app.route("/api/parking/history", methods=["GET"])
def api_get_history() -> Response:
    """Get recent parking slot activity history"""
    loc_id = request.args.get("location")
    location_id = int(loc_id) if loc_id and loc_id.isdigit() else None
    limit = int(request.args.get("limit", 50))
    history = db.get_parking_history(location_id=location_id, limit=limit)
    return jsonify({"success": True, "history": history, "count": len(history)})


# ==================== DEMO DATA RESET ====================

@app.route("/api/demo/reset", methods=["POST"])
def api_reset_demo() -> Response:
    """Reset / reload database with initial realistic mock demo data"""
    try:
        db.seed_demo_data()
        logger.info("Demo data reset triggered by admin/client")
        return jsonify({"success": True, "message": "Demo data successfully reset to initial default state."})
    except Exception as e:
        logger.error(f"Error resetting demo data: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== LIVE YOLO VIDEO STREAM & STATS ====================

@app.route("/video_feed")
def video_feed() -> Response:
    """MJPEG streaming endpoint for live YOLOv8 camera/video feed"""
    service = get_live_service()
    return Response(
        service.generate_mjpeg_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/live/stats", methods=["GET"])
def api_live_stats() -> Response:
    """Get live detection stats from the active YOLOv8 stream"""
    service = get_live_service()
    stats = service.get_stats()
    return jsonify({"success": True, "live_stats": stats})


# ==================== ADMIN PARKING SLOTS CONFIGURATION ====================

@app.route("/api/camera/snapshot")
def api_camera_snapshot() -> Response:
    """Return single JPEG frame snapshot for interactive slot boundary editing"""
    service = get_live_service()
    jpeg_bytes = service.get_snapshot_jpeg()
    if jpeg_bytes:
        return Response(jpeg_bytes, mimetype="image/jpeg")
    return jsonify({"error": "Snapshot not available"}), 404


@app.route("/api/admin/parking-slots", methods=["GET"])
@login_required
def api_admin_get_parking_slots() -> Response:
    """Get configured parking slots for visual canvas editor (Admin only)"""
    service = get_live_service()
    slots = service.get_parking_spaces()
    return jsonify({
        "success": True,
        "slots": slots,
        "count": len(slots),
        "frame_width": 1100,
        "frame_height": 720,
        "snapshot_url": "/api/camera/snapshot"
    })


@app.route("/api/admin/parking-slots", methods=["POST"])
@login_required
def api_admin_save_parking_slots() -> Response:
    """Save updated parking slot boundaries and IDs to YOLO detector system (Admin only)"""
    data = request.get_json() or {}
    slots_data = data.get("slots", [])
    if not isinstance(slots_data, list):
        return jsonify({"success": False, "error": "Invalid slots data format. Expected array of slots."}), 400

    # Validate and clean slots
    cleaned_slots = []
    for idx, s in enumerate(slots_data):
        slot_id = str(s.get("id") or f"A{idx+1:02d}").strip().upper()
        vtype = str(s.get("vehicle_type", "Car")).strip().capitalize()
        x = int(s.get("x", 0))
        y = int(s.get("y", 0))
        w = max(20, int(s.get("width", config.PARKING_WIDTH)))
        h = max(20, int(s.get("height", config.PARKING_HEIGHT)))
        cleaned_slots.append({
            "id": slot_id,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "vehicle_type": vtype
        })

    # Update live detector service and CarParkPos
    service = get_live_service()
    service.update_parking_spaces(cleaned_slots)
    logger.info(f"Admin saved {len(cleaned_slots)} parking slots successfully")

    return jsonify({
        "success": True,
        "message": f"Successfully saved {len(cleaned_slots)} parking slot boundaries.",
        "count": len(cleaned_slots),
        "slots": cleaned_slots
    })


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error: Any) -> Any:
    if request.path.startswith("/api/"):
        return jsonify({"error": "Resource not found", "status_code": 404}), 404
    return render_template("index.html"), 404


@app.errorhandler(500)
def internal_server_error(error: Any) -> Any:
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error", "status_code": 500}), 500
    return render_template("index.html"), 500


def create_app() -> Flask:
    """Application factory for testing or WSGI runners"""
    return app


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("🚀 SMART PARKING AVAILABILITY & QUEUE NOTIFICATION SYSTEM (PHASE-2)")
    print("=" * 65)
    print("📡 Web Dashboard URL  : http://127.0.0.1:5000")
    print("🔑 Admin Credentials  : username: admin  |  password: admin123")
    print("🚗 Mode 1: Live YOLOv8 Detection [NMIT Main Gate]")
    print("📊 Mode 2: 5 Mock Parking Locations Demo")
    print("=" * 65 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
