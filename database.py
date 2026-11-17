"""
Database Module for Smart Parking Availability and Queue Notification System (Phase-2)
Handles SQLite database initialization, mock data seeding, CRUD operations,
status transitions, 2-minute reservations, queue triggers, parking history, and notifications.
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)

DB_PATH = getattr(config, "DATABASE_PATH", "data/parking_system.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a SQLite database connection with row factory"""
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = "smart_parking_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


class DatabaseManager:
    """Encapsulates all database operations for Smart Parking System"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DB_PATH
        self.init_db()

    def init_db(self, force_reseed: bool = False) -> None:
        """Create tables if not exist and seed initial mock data"""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. Admin table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 2. Locations table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    distance_km REAL DEFAULT 0.0,
                    car_slots_count INTEGER NOT NULL,
                    bike_slots_count INTEGER NOT NULL,
                    is_live BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 3. Parking Slots table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parking_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id INTEGER NOT NULL,
                    slot_number TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL, -- 'Car' or 'Bike'
                    status TEXT NOT NULL DEFAULT 'available', -- 'available', 'occupied', or 'reserved'
                    is_special BOOLEAN DEFAULT 0,
                    vehicle_number TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE CASCADE,
                    UNIQUE(location_id, slot_number)
                );
                """
            )

            # 4. Reservations table (2-minute temporary reservation)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_id INTEGER NOT NULL,
                    slot_number TEXT NOT NULL,
                    location_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    vehicle_number TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL,
                    reserved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'active', -- 'active', 'confirmed', 'expired', 'cancelled'
                    FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE CASCADE,
                    FOREIGN KEY (slot_id) REFERENCES parking_slots (id) ON DELETE CASCADE
                );
                """
            )

            # 5. Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT,
                    vehicle_number TEXT UNIQUE NOT NULL,
                    vehicle_type TEXT NOT NULL, -- 'Car' or 'Bike'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # 6. Queue table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_name TEXT NOT NULL,
                    vehicle_number TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL, -- 'Car' or 'Bike'
                    location_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Waiting', -- 'Waiting', 'Notified', 'Parked', 'Cancelled'
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notified_at TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
                );
                """
            )

            # 7. Parking History table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS parking_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id INTEGER NOT NULL,
                    slot_id INTEGER,
                    slot_number TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL, -- 'Car' or 'Bike'
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    vehicle_number TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE CASCADE
                );
                """
            )

            # 8. Notifications table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_name TEXT,
                    location_id INTEGER,
                    slot_number TEXT,
                    message TEXT NOT NULL,
                    type TEXT DEFAULT 'availability', -- 'availability', 'system', 'queue', 'reservation'
                    status TEXT NOT NULL DEFAULT 'unread', -- 'unread', 'read'
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id) ON DELETE CASCADE
                );
                """
            )
            # Check migrations
            cursor.execute("PRAGMA table_info(locations);")
            loc_cols = [col[1] for col in cursor.fetchall()]
            if loc_cols and "distance_km" not in loc_cols:
                cursor.execute("ALTER TABLE locations ADD COLUMN distance_km REAL DEFAULT 0.0;")

            conn.commit()

        # Check if locations exist, if not seed demo data
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM locations;")
            loc_count = cur.fetchone()["count"]

            cur.execute("SELECT COUNT(*) as count FROM admin;")
            admin_count = cur.fetchone()["count"]

            if loc_count == 0 or admin_count == 0 or force_reseed:
                self.seed_demo_data()

    def seed_demo_data(self) -> None:
        """Seed initial realistic demo data for 5 parking locations with distances"""
        logger.info("Seeding realistic demo mock data into database...")
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            # Clear existing data for fresh seed
            cur.execute("DELETE FROM notifications;")
            cur.execute("DELETE FROM parking_history;")
            cur.execute("DELETE FROM queue;")
            cur.execute("DELETE FROM reservations;")
            cur.execute("DELETE FROM parking_slots;")
            cur.execute("DELETE FROM users;")
            cur.execute("DELETE FROM locations;")
            cur.execute("DELETE FROM admin;")

            # 1. Seed Admin
            admin_user = getattr(config, "ADMIN_USERNAME", "admin")
            admin_pass = getattr(config, "ADMIN_PASSWORD", "admin123")
            cur.execute(
                "INSERT INTO admin (username, password_hash, role) VALUES (?, ?, ?);",
                (admin_user, hash_password(admin_pass), "admin"),
            )

            # 2. Seed 5 Mock Locations with exact demo distances
            locations_data = getattr(
                config,
                "MOCK_LOCATIONS",
                [
                    {
                        "id": 1,
                        "code": "NMIT_MAIN",
                        "name": "NMIT Main Gate Parking",
                        "description": "Primary parking area located at the NMIT main entrance",
                        "distance_km": 0.4,
                        "car_slots": 10,
                        "bike_slots": 5,
                        "is_live": True,
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
                ],
            )

            for loc in locations_data:
                cur.execute(
                    """
                    INSERT INTO locations (id, code, name, description, distance_km, car_slots_count, bike_slots_count, is_live)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        loc["id"],
                        loc["code"],
                        loc["name"],
                        loc["description"],
                        loc.get("distance_km", 1.0),
                        loc["car_slots"],
                        loc["bike_slots"],
                        1 if loc.get("is_live", False) else 0,
                    ),
                )

            # 3. Seed Users
            demo_users = [
                ("Rahul Sharma", "+91 9876543210", "KA01AB1234", "Car"),
                ("Akash Kumar", "+91 9876543211", "KA05XY5678", "Bike"),
                ("Priya Patel", "+91 9876543212", "KA03CD4567", "Car"),
                ("Vikram Singh", "+91 9876543213", "KA04EF8901", "Bike"),
                ("Ananya Roy", "+91 9876543214", "KA02GH2345", "Car"),
                ("Suresh Reddy", "+91 9876543215", "KA51JK6789", "Car"),
                ("Deepa Rao", "+91 9876543216", "KA05MN3456", "Bike"),
                ("Karthik M", "+91 9876543217", "KA01PQ7890", "Car"),
                ("Sneha K", "+91 9876543218", "KA04RS1212", "Bike"),
                ("Rohan Gupta", "+91 9876543219", "KA03TV3434", "Car"),
            ]

            user_id_map = {}
            for name, phone, plate, vtype in demo_users:
                cur.execute(
                    "INSERT INTO users (name, phone, vehicle_number, vehicle_type) VALUES (?, ?, ?, ?);",
                    (name, phone, plate, vtype),
                )
                user_id_map[plate] = cur.lastrowid

            # 4. Seed Parking Slots for each location with realistic occupancy
            loc_patterns = {
                1: {"car_occ": 4, "bike_occ": 2},
                2: {"car_occ": 12, "bike_occ": 8},
                3: {"car_occ": 8, "bike_occ": 4},
                4: {"car_occ": 5, "bike_occ": 2},
                5: {"car_occ": 6, "bike_occ": 4},
            }

            car_plates_pool = [
                "KA01AB1234", "KA03CD4567", "KA02GH2345", "KA51JK6789", "KA01PQ7890",
                "KA03TV3434", "KA04XY9999", "KA05ZZ1111", "KA02KL2222", "KA01MM3333",
                "KA03NN4444", "KA05OO5555", "KA04PP6666", "KA01QQ7777", "KA02RR8888"
            ]
            bike_plates_pool = [
                "KA05XY5678", "KA04EF8901", "KA05MN3456", "KA04RS1212", "KA03BB2020",
                "KA01CC3030", "KA02DD4040", "KA04EE5050", "KA05FF6060", "KA01GG7070"
            ]

            now = datetime.now()

            for loc in locations_data:
                loc_id = loc["id"]
                car_count = loc["car_slots"]
                bike_count = loc["bike_slots"]
                pat = loc_patterns.get(loc_id, {"car_occ": int(car_count * 0.5), "bike_occ": int(bike_count * 0.5)})

                # Car Slots: A01..
                for i in range(1, car_count + 1):
                    slot_num = f"A{i:02d}"
                    is_occ = (i <= pat["car_occ"])
                    status = "occupied" if is_occ else "available"
                    plate = car_plates_pool[(i - 1) % len(car_plates_pool)] if is_occ else None
                    is_special = 1 if i == 1 else 0
                    time_offset = now - timedelta(minutes=(i * 7 + loc_id * 3))
                    cur.execute(
                        """
                        INSERT INTO parking_slots (location_id, slot_number, vehicle_type, status, is_special, vehicle_number, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        (loc_id, slot_num, "Car", status, is_special, plate, time_offset.strftime("%Y-%m-%d %H:%M:%S")),
                    )

                # Bike Slots: B01..
                for j in range(1, bike_count + 1):
                    slot_num = f"B{j:02d}"
                    is_occ = (j <= pat["bike_occ"])
                    status = "occupied" if is_occ else "available"
                    plate = bike_plates_pool[(j - 1) % len(bike_plates_pool)] if is_occ else None
                    is_special = 1 if j == 1 else 0
                    time_offset = now - timedelta(minutes=(j * 5 + loc_id * 4))
                    cur.execute(
                        """
                        INSERT INTO parking_slots (location_id, slot_number, vehicle_type, status, is_special, vehicle_number, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        (loc_id, slot_num, "Bike", status, is_special, plate, time_offset.strftime("%Y-%m-%d %H:%M:%S")),
                    )

            # 5. Seed Queue Users (3-5 users)
            queue_demo = [
                ("Rahul Sharma", "KA01AB1234", "Car", 1, 1, "Waiting", now - timedelta(minutes=15)),
                ("Akash Kumar", "KA05XY5678", "Bike", 1, 2, "Waiting", now - timedelta(minutes=12)),
                ("Priya Patel", "KA03CD4567", "Car", 1, 3, "Waiting", now - timedelta(minutes=8)),
                ("Vikram Singh", "KA04EF8901", "Bike", 2, 1, "Waiting", now - timedelta(minutes=5)),
            ]

            for uname, vplate, vtype, loc_id, pos, status, jtime in queue_demo:
                uid = user_id_map.get(vplate)
                cur.execute(
                    """
                    INSERT INTO queue (user_id, user_name, vehicle_number, vehicle_type, location_id, position, status, joined_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (uid, uname, vplate, vtype, loc_id, pos, status, jtime.strftime("%Y-%m-%d %H:%M:%S")),
                )

            # 6. Seed Parking History (15-20 historical records)
            history_samples = [
                (1, "A01", "Car", "occupied", "available", "KA01AB1234", now - timedelta(minutes=65)),
                (1, "A01", "Car", "available", "occupied", "KA02GH2345", now - timedelta(minutes=50)),
                (1, "A03", "Car", "occupied", "available", "KA51JK6789", now - timedelta(minutes=38)),
                (1, "B02", "Bike", "available", "occupied", "KA05XY5678", now - timedelta(minutes=35)),
                (1, "B04", "Bike", "occupied", "available", "KA04EF8901", now - timedelta(minutes=28)),
                (2, "A04", "Car", "available", "occupied", "KA01PQ7890", now - timedelta(minutes=45)),
                (2, "A07", "Car", "occupied", "available", "KA03TV3434", now - timedelta(minutes=40)),
                (3, "B01", "Bike", "available", "occupied", "KA05MN3456", now - timedelta(minutes=30)),
                (4, "A02", "Car", "occupied", "available", "KA04XY9999", now - timedelta(minutes=55)),
                (5, "B03", "Bike", "available", "occupied", "KA04RS1212", now - timedelta(minutes=20)),
            ]

            for loc_id, snum, vtype, prev_s, new_s, vplate, tstamp in history_samples:
                cur.execute(
                    """
                    INSERT INTO parking_history (location_id, slot_number, vehicle_type, previous_status, new_status, vehicle_number, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (loc_id, snum, vtype, prev_s, new_s, vplate, tstamp.strftime("%Y-%m-%d %H:%M:%S")),
                )

            # 7. Seed Initial In-Dashboard Notifications
            notif_samples = [
                (1, "Rahul Sharma", 1, "A03", "🔔 Parking Slot A03 (CAR) is now available at NMIT Main Gate.", "availability", now - timedelta(minutes=38)),
                (2, "Akash Kumar", 1, "B04", "🔔 Parking Slot B04 (BIKE) is now available at NMIT Main Gate.", "availability", now - timedelta(minutes=28)),
                (None, "System", 1, None, "ℹ️ Smart Parking System Online.", "system", now - timedelta(hours=2)),
            ]

            for uid, uname, loc_id, snum, msg, ntype, tstamp in notif_samples:
                cur.execute(
                    """
                    INSERT INTO notifications (user_id, user_name, location_id, slot_number, message, type, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, 'unread', ?);
                    """,
                    (uid, uname, loc_id, snum, msg, ntype, tstamp.strftime("%Y-%m-%d %H:%M:%S")),
                )

            conn.commit()
            logger.info("Demo data seeded successfully!")

    # ==================== AUTH METHODS ====================

    def authenticate_admin(self, username: str, password: str) -> bool:
        """Verify admin login credentials"""
        if not username or not password:
            return False

        demo_user = getattr(config, "ADMIN_USERNAME", "admin")
        demo_pass = getattr(config, "ADMIN_PASSWORD", "admin123")
        if username == demo_user and password == demo_pass:
            return True

        hashed = hash_password(password)
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM admin WHERE username = ?;", (username,))
            row = cur.fetchone()
            if row and (row["password_hash"] == hashed or row["password_hash"] == password):
                return True
        return False

    # ==================== 2-MINUTE RESERVATION ENGINE ====================

    def clean_expired_reservations(self) -> int:
        """Find active reservations that have passed expires_at, revert slot to available"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        expired_count = 0
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT r.*, p.status as current_slot_status 
                FROM reservations r
                JOIN parking_slots p ON r.slot_id = p.id
                WHERE r.status = 'active' AND r.expires_at <= ?;
                """,
                (now_str,),
            )
            expired_rows = cur.fetchall()

            for row in expired_rows:
                res_id = row["id"]
                slot_id = row["slot_id"]
                slot_num = row["slot_number"]
                loc_id = row["location_id"]
                vtype = row["vehicle_type"]

                # Mark reservation expired
                cur.execute("UPDATE reservations SET status = 'expired' WHERE id = ?;", (res_id,))

                # If slot is still 'reserved', revert to 'available'
                if row["current_slot_status"] == "reserved":
                    cur.execute(
                        "UPDATE parking_slots SET status = 'available', vehicle_number = NULL, last_updated = ? WHERE id = ?;",
                        (now_str, slot_id),
                    )

                    # Log to history
                    cur.execute(
                        """
                        INSERT INTO parking_history (location_id, slot_id, slot_number, vehicle_type, previous_status, new_status, timestamp)
                        VALUES (?, ?, ?, ?, 'reserved', 'available', ?);
                        """,
                        (loc_id, slot_id, slot_num, vtype, now_str),
                    )

                    # Notification
                    notif_msg = f"⏳ Reservation expired for Slot {slot_num}. The slot is now available."
                    cur.execute(
                        """
                        INSERT INTO notifications (location_id, slot_number, message, type, status, timestamp)
                        VALUES (?, ?, ?, 'reservation', 'unread', ?);
                        """,
                        (loc_id, slot_num, notif_msg, now_str),
                    )
                    expired_count += 1

            conn.commit()
        return expired_count

    def reserve_slot(
        self,
        location_id: int,
        slot_number: str,
        user_name: str,
        vehicle_number: str,
        vehicle_type: str = "Car",
        duration_seconds: int = 120,
    ) -> Dict[str, Any]:
        """
        Reserve a parking slot for 2 minutes (120 seconds).
        Prevents double-booking if already reserved or occupied.
        """
        self.clean_expired_reservations()

        vehicle_number = vehicle_number.strip().upper()
        user_name = user_name.strip()
        vehicle_type = vehicle_type.strip().capitalize()
        now = datetime.now()
        expires_at = now + timedelta(seconds=duration_seconds)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        exp_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            # Find slot
            cur.execute(
                "SELECT * FROM parking_slots WHERE location_id = ? AND slot_number = ?;",
                (location_id, slot_number),
            )
            slot = cur.fetchone()
            if not slot:
                raise ValueError(f"Slot {slot_number} not found for location {location_id}")

            slot_id = slot["id"]

            # Double Booking Prevention
            if slot["status"] == "occupied":
                raise ValueError(f"Slot {slot_number} is already OCCUPIED.")

            if slot["status"] == "reserved":
                # Check active reservation
                cur.execute(
                    "SELECT * FROM reservations WHERE slot_id = ? AND status = 'active';",
                    (slot_id,),
                )
                active_res = cur.fetchone()
                if active_res:
                    raise ValueError(f"Slot {slot_number} is already RESERVED by another driver.")

            # Update slot status to 'reserved'
            cur.execute(
                """
                UPDATE parking_slots
                SET status = 'reserved', vehicle_number = ?, last_updated = ?
                WHERE id = ?;
                """,
                (vehicle_number, now_str, slot_id),
            )

            # Insert reservation
            cur.execute(
                """
                INSERT INTO reservations (slot_id, slot_number, location_id, user_name, vehicle_number, vehicle_type, reserved_at, expires_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active');
                """,
                (slot_id, slot_number, location_id, user_name, vehicle_number, vehicle_type, now_str, exp_str),
            )
            res_id = cur.lastrowid

            # Log to history
            cur.execute(
                """
                INSERT INTO parking_history (location_id, slot_id, slot_number, vehicle_type, previous_status, new_status, vehicle_number, timestamp)
                VALUES (?, ?, ?, ?, 'available', 'reserved', ?, ?);
                """,
                (location_id, slot_id, slot_number, vehicle_type, vehicle_number, now_str),
            )

            # Notification
            notif_msg = f"🟠 Slot {slot_number} reserved by {user_name} ({vehicle_number}). 2-minute timer started."
            cur.execute(
                """
                INSERT INTO notifications (location_id, slot_number, message, type, status, timestamp)
                VALUES (?, ?, ?, 'reservation', 'unread', ?);
                """,
                (location_id, slot_number, notif_msg, now_str),
            )

            conn.commit()

            return {
                "id": res_id,
                "slot_id": slot_id,
                "slot_number": slot_number,
                "location_id": location_id,
                "user_name": user_name,
                "vehicle_number": vehicle_number,
                "vehicle_type": vehicle_type,
                "status": "reserved",
                "duration_seconds": duration_seconds,
                "remaining_seconds": duration_seconds,
                "reserved_at": now_str,
                "expires_at": exp_str,
            }

    def confirm_arrival(self, slot_id_or_number: Any, location_id: Optional[int] = None) -> Dict[str, Any]:
        """
        User arrives at slot: RESERVED → OCCUPIED.
        """
        self.clean_expired_reservations()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            # Find slot
            if isinstance(slot_id_or_number, int):
                cur.execute("SELECT * FROM parking_slots WHERE id = ?;", (slot_id_or_number,))
            else:
                loc_filter = "AND location_id = ?" if location_id else ""
                params = (slot_id_or_number, location_id) if location_id else (slot_id_or_number,)
                cur.execute(f"SELECT * FROM parking_slots WHERE slot_number = ? {loc_filter};", params)

            slot = cur.fetchone()
            if not slot:
                raise ValueError("Parking slot not found")

            slot_id = slot["id"]
            slot_number = slot["slot_number"]
            loc_id = slot["location_id"]
            vtype = slot["vehicle_type"]
            vnumber = slot["vehicle_number"]

            # Update active reservation if any
            cur.execute(
                "UPDATE reservations SET status = 'confirmed' WHERE slot_id = ? AND status = 'active';",
                (slot_id,),
            )

            # Update slot to occupied
            cur.execute(
                "UPDATE parking_slots SET status = 'occupied', last_updated = ? WHERE id = ?;",
                (now_str, slot_id),
            )

            # Log to history
            cur.execute(
                """
                INSERT INTO parking_history (location_id, slot_id, slot_number, vehicle_type, previous_status, new_status, vehicle_number, timestamp)
                VALUES (?, ?, ?, ?, 'reserved', 'occupied', ?, ?);
                """,
                (loc_id, slot_id, slot_number, vtype, vnumber, now_str),
            )

            # Notification
            notif_msg = f"✓ Parking Confirmed: Slot {slot_number} is now OCCUPIED by {vnumber or 'Vehicle'}."
            cur.execute(
                """
                INSERT INTO notifications (location_id, slot_number, message, type, status, timestamp)
                VALUES (?, ?, ?, 'reservation', 'unread', ?);
                """,
                (loc_id, slot_number, notif_msg, now_str),
            )

            conn.commit()

            return {
                "success": True,
                "slot_id": slot_id,
                "slot_number": slot_number,
                "status": "occupied",
                "message": "Parking Confirmed ✓",
                "timestamp": now_str,
            }

    def cancel_reservation(self, slot_id_or_res_id: int, is_reservation_id: bool = False) -> Dict[str, Any]:
        """Cancel active reservation: RESERVED → AVAILABLE"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            if is_reservation_id:
                cur.execute("SELECT * FROM reservations WHERE id = ?;", (slot_id_or_res_id,))
                res = cur.fetchone()
                if not res:
                    raise ValueError("Reservation not found")
                slot_id = res["slot_id"]
            else:
                slot_id = slot_id_or_res_id

            cur.execute("SELECT * FROM parking_slots WHERE id = ?;", (slot_id,))
            slot = cur.fetchone()
            if not slot:
                raise ValueError("Slot not found")

            slot_number = slot["slot_number"]
            loc_id = slot["location_id"]
            vtype = slot["vehicle_type"]

            # Cancel reservation
            cur.execute(
                "UPDATE reservations SET status = 'cancelled' WHERE slot_id = ? AND status = 'active';",
                (slot_id,),
            )

            # Revert slot
            cur.execute(
                "UPDATE parking_slots SET status = 'available', vehicle_number = NULL, last_updated = ? WHERE id = ?;",
                (now_str, slot_id),
            )

            # Log to history
            cur.execute(
                """
                INSERT INTO parking_history (location_id, slot_id, slot_number, vehicle_type, previous_status, new_status, timestamp)
                VALUES (?, ?, ?, ?, 'reserved', 'available', ?);
                """,
                (loc_id, slot_id, slot_number, vtype, now_str),
            )

            # Notification
            notif_msg = f"Reservation cancelled for Slot {slot_number}. Slot is now available."
            cur.execute(
                """
                INSERT INTO notifications (location_id, slot_number, message, type, status, timestamp)
                VALUES (?, ?, ?, 'reservation', 'unread', ?);
                """,
                (loc_id, slot_number, notif_msg, now_str),
            )

            conn.commit()

            return {
                "success": True,
                "slot_id": slot_id,
                "slot_number": slot_number,
                "status": "available",
                "message": "Reservation cancelled.",
            }

    def get_active_reservations(self, location_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all active reservations with calculated remaining seconds"""
        self.clean_expired_reservations()
        now = datetime.now()

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            query = """
                SELECT r.*, l.name as location_name
                FROM reservations r
                LEFT JOIN locations l ON r.location_id = l.id
                WHERE r.status = 'active'
            """
            params: List[Any] = []
            if location_id is not None:
                query += " AND r.location_id = ?"
                params.append(location_id)

            query += " ORDER BY r.expires_at ASC;"
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

            results = []
            for r in rows:
                item = dict(r)
                exp_dt = datetime.strptime(item["expires_at"], "%Y-%m-%d %H:%M:%S")
                diff = int((exp_dt - now).total_seconds())
                item["remaining_seconds"] = max(0, diff)
                item["minutes_remaining"] = f"{diff // 60:02d}:{diff % 60:02d}"
                results.append(item)

            return results

    # ==================== LOCATIONS & SLOTS METHODS ====================

    def get_locations(self, max_distance_km: Optional[float] = None, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all parking locations with live slot occupancy calculations and distance filtering"""
        self.clean_expired_reservations()
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM locations ORDER BY distance_km ASC, id ASC;")
            loc_rows = cur.fetchall()

            locations = []
            for row in loc_rows:
                loc_id = row["id"]
                loc_dict = dict(row)
                dist = loc_dict.get("distance_km", 0.0)

                # Filter by distance if requested and no search query
                if search_query:
                    q = search_query.lower()
                    if q not in loc_dict["name"].lower() and q not in loc_dict["code"].lower():
                        continue
                elif max_distance_km is not None:
                    if dist > max_distance_km:
                        continue

                # Get slot counts
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total_slots,
                        SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available_slots,
                        SUM(CASE WHEN status = 'occupied' THEN 1 ELSE 0 END) as occupied_slots,
                        SUM(CASE WHEN status = 'reserved' THEN 1 ELSE 0 END) as reserved_slots,
                        SUM(CASE WHEN vehicle_type = 'Car' AND status = 'occupied' THEN 1 ELSE 0 END) as occupied_cars,
                        SUM(CASE WHEN vehicle_type = 'Car' AND status = 'available' THEN 1 ELSE 0 END) as available_cars,
                        SUM(CASE WHEN vehicle_type = 'Car' THEN 1 ELSE 0 END) as total_cars,
                        SUM(CASE WHEN vehicle_type = 'Bike' AND status = 'occupied' THEN 1 ELSE 0 END) as occupied_bikes,
                        SUM(CASE WHEN vehicle_type = 'Bike' AND status = 'available' THEN 1 ELSE 0 END) as available_bikes,
                        SUM(CASE WHEN vehicle_type = 'Bike' THEN 1 ELSE 0 END) as total_bikes
                    FROM parking_slots
                    WHERE location_id = ?;
                    """,
                    (loc_id,),
                )
                stats = cur.fetchone()

                cur.execute(
                    "SELECT COUNT(*) as q_count FROM queue WHERE location_id = ? AND status = 'Waiting';",
                    (loc_id,),
                )
                q_count = cur.fetchone()["q_count"]

                total = stats["total_slots"] or 0
                occ = stats["occupied_slots"] or 0
                resv = stats["reserved_slots"] or 0
                avail = stats["available_slots"] or 0
                occ_pct = round(((occ + resv) / total * 100), 1) if total > 0 else 0.0

                loc_dict.update(
                    {
                        "total_slots": total,
                        "available_slots": avail,
                        "occupied_slots": occ,
                        "reserved_slots": resv,
                        "occupied_cars": stats["occupied_cars"] or 0,
                        "available_cars": stats["available_cars"] or 0,
                        "total_cars": stats["total_cars"] or 0,
                        "occupied_bikes": stats["occupied_bikes"] or 0,
                        "available_bikes": stats["available_bikes"] or 0,
                        "total_bikes": stats["total_bikes"] or 0,
                        "queue_count": q_count,
                        "occupancy_pct": occ_pct,
                        "is_full": avail == 0,
                    }
                )
                locations.append(loc_dict)

            return locations

    def get_location_by_id(self, location_id: int) -> Optional[Dict[str, Any]]:
        """Get location details by ID"""
        locations = self.get_locations()
        for loc in locations:
            if loc["id"] == location_id:
                return loc
        return None

    def get_slots(
        self, location_id: int, vehicle_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return all parking slots for a given location, with active reservation info attached"""
        self.clean_expired_reservations()
        now = datetime.now()

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            if vehicle_type:
                cur.execute(
                    """
                    SELECT p.*, r.id as reservation_id, r.user_name as reserved_by, r.expires_at as reservation_expires_at
                    FROM parking_slots p
                    LEFT JOIN reservations r ON p.id = r.slot_id AND r.status = 'active'
                    WHERE p.location_id = ? AND LOWER(p.vehicle_type) = LOWER(?)
                    ORDER BY p.slot_number ASC;
                    """,
                    (location_id, vehicle_type),
                )
            else:
                cur.execute(
                    """
                    SELECT p.*, r.id as reservation_id, r.user_name as reserved_by, r.expires_at as reservation_expires_at
                    FROM parking_slots p
                    LEFT JOIN reservations r ON p.id = r.slot_id AND r.status = 'active'
                    WHERE p.location_id = ?
                    ORDER BY p.vehicle_type DESC, p.slot_number ASC;
                    """,
                    (location_id,),
                )
            rows = cur.fetchall()

            results = []
            for r in rows:
                item = dict(r)
                if item.get("reservation_expires_at"):
                    exp_dt = datetime.strptime(item["reservation_expires_at"], "%Y-%m-%d %H:%M:%S")
                    diff = int((exp_dt - now).total_seconds())
                    item["remaining_seconds"] = max(0, diff)
                    item["remaining_formatted"] = f"{diff // 60:02d}:{diff % 60:02d}"
                else:
                    item["remaining_seconds"] = 0
                    item["remaining_formatted"] = ""
                results.append(item)

            return results

    def get_slot_by_id(self, slot_id: int) -> Optional[Dict[str, Any]]:
        """Get a single slot by ID"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM parking_slots WHERE id = ?;", (slot_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # ==================== FR3 & FR7 STATUS TRANSITION & NOTIFICATION ENGINE ====================

    def update_slot_status(
        self,
        location_id: int,
        slot_number: str,
        new_status: str,
        vehicle_type: Optional[str] = None,
        vehicle_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update slot status and trigger FR3 Auto Notification and FR7 History.
        """
        new_status = new_status.lower()
        if new_status not in ["available", "occupied", "reserved"]:
            raise ValueError("Status must be 'available', 'occupied', or 'reserved'")

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM parking_slots WHERE location_id = ? AND slot_number = ?;",
                (location_id, slot_number),
            )
            slot = cur.fetchone()
            if not slot:
                raise ValueError(f"Slot {slot_number} not found for location {location_id}")

            slot_id = slot["id"]
            previous_status = slot["status"]
            vtype = vehicle_type or slot["vehicle_type"]
            vnumber = vehicle_number if new_status in ["occupied", "reserved"] else None
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Update slot
            cur.execute(
                """
                UPDATE parking_slots
                SET status = ?, vehicle_number = ?, last_updated = ?
                WHERE id = ?;
                """,
                (new_status, vnumber, now_str, slot_id),
            )

            # Log to FR7 Parking History
            cur.execute(
                """
                INSERT INTO parking_history (location_id, slot_id, slot_number, vehicle_type, previous_status, new_status, vehicle_number, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (location_id, slot_id, slot_number, vtype, previous_status, new_status, vnumber or slot["vehicle_number"], now_str),
            )

            notification_result = None

            # FR3: Check if transitioned OCCUPIED/RESERVED -> AVAILABLE
            if previous_status in ["occupied", "reserved"] and new_status == "available":
                # Find the next waiting user in queue for this location and vehicle type
                cur.execute(
                    """
                    SELECT * FROM queue
                    WHERE location_id = ? AND LOWER(vehicle_type) = LOWER(?) AND status = 'Waiting'
                    ORDER BY position ASC, joined_at ASC
                    LIMIT 1;
                    """,
                    (location_id, vtype),
                )
                next_user = cur.fetchone()

                if not next_user:
                    cur.execute(
                        """
                        SELECT * FROM queue
                        WHERE location_id = ? AND status = 'Waiting'
                        ORDER BY position ASC, joined_at ASC
                        LIMIT 1;
                        """,
                        (location_id,),
                    )
                    next_user = cur.fetchone()

                if next_user:
                    queue_id = next_user["id"]
                    user_id = next_user["user_id"]
                    user_name = next_user["user_name"]
                    notif_msg = f"🔔 Parking Slot {slot_number} ({vtype.upper()}) is now available. {user_name} is next in the queue."

                    cur.execute(
                        """
                        UPDATE queue
                        SET status = 'Notified', notified_at = ?
                        WHERE id = ?;
                        """,
                        (now_str, queue_id),
                    )

                    cur.execute(
                        """
                        INSERT INTO notifications (user_id, user_name, location_id, slot_number, message, type, status, timestamp)
                        VALUES (?, ?, ?, ?, ?, 'availability', 'unread', ?);
                        """,
                        (user_id, user_name, location_id, slot_number, notif_msg, now_str),
                    )

                    # Re-order remaining waiting users
                    cur.execute(
                        """
                        SELECT id FROM queue
                        WHERE location_id = ? AND status = 'Waiting'
                        ORDER BY position ASC, joined_at ASC;
                        """,
                        (location_id,),
                    )
                    remaining = cur.fetchall()
                    for idx, rem in enumerate(remaining, start=1):
                        cur.execute("UPDATE queue SET position = ? WHERE id = ?;", (idx, rem["id"]))

                    notification_result = {
                        "queue_id": queue_id,
                        "user_name": user_name,
                        "slot_number": slot_number,
                        "message": notif_msg,
                        "timestamp": now_str,
                    }
                else:
                    notif_msg = f"🔔 Parking Slot {slot_number} ({vtype.upper()}) is now available."
                    cur.execute(
                        """
                        INSERT INTO notifications (location_id, slot_number, message, type, status, timestamp)
                        VALUES (?, ?, ?, 'availability', 'unread', ?);
                        """,
                        (location_id, slot_number, notif_msg, now_str),
                    )
                    notification_result = {
                        "slot_number": slot_number,
                        "message": notif_msg,
                        "timestamp": now_str,
                    }

            conn.commit()

            return {
                "success": True,
                "slot_id": slot_id,
                "slot_number": slot_number,
                "previous_status": previous_status,
                "new_status": new_status,
                "last_updated": now_str,
                "notification": notification_result,
            }

    # ==================== FR6 QUEUE MANAGEMENT METHODS ====================

    def join_queue(
        self,
        user_name: str,
        vehicle_number: str,
        vehicle_type: str,
        location_id: int = 1,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a user to the parking queue. Prevents duplicate active entries."""
        if not user_name or not vehicle_number or not vehicle_type:
            raise ValueError("user_name, vehicle_number, and vehicle_type are required")

        vehicle_number = vehicle_number.strip().upper()
        user_name = user_name.strip()
        vehicle_type = vehicle_type.strip().capitalize()
        if vehicle_type not in ["Car", "Bike"]:
            vehicle_type = "Car"

        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            # Prevent duplicate active entries
            cur.execute(
                """
                SELECT * FROM queue
                WHERE UPPER(vehicle_number) = ? AND location_id = ? AND status = 'Waiting';
                """,
                (vehicle_number, location_id),
            )
            existing = cur.fetchone()
            if existing:
                raise ValueError(
                    f"Vehicle {vehicle_number} is already in the queue at position #{existing['position']}."
                )

            cur.execute("SELECT id FROM users WHERE UPPER(vehicle_number) = ?;", (vehicle_number,))
            user_row = cur.fetchone()
            if user_row:
                user_id = user_row["id"]
            else:
                cur.execute(
                    "INSERT INTO users (name, phone, vehicle_number, vehicle_type) VALUES (?, ?, ?, ?);",
                    (user_name, phone or "", vehicle_number, vehicle_type),
                )
                user_id = cur.lastrowid

            cur.execute(
                "SELECT COUNT(*) as cnt FROM queue WHERE location_id = ? AND status = 'Waiting';",
                (location_id,),
            )
            current_waiting = cur.fetchone()["cnt"]
            new_position = current_waiting + 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                """
                INSERT INTO queue (user_id, user_name, vehicle_number, vehicle_type, location_id, position, status, joined_at)
                VALUES (?, ?, ?, ?, ?, ?, 'Waiting', ?);
                """,
                (user_id, user_name, vehicle_number, vehicle_type, location_id, new_position, now_str),
            )
            queue_id = cur.lastrowid

            notif_msg = f"📋 {user_name} ({vehicle_number}, {vehicle_type}) joined queue at Position #{new_position}."
            cur.execute(
                """
                INSERT INTO notifications (user_id, user_name, location_id, message, type, status, timestamp)
                VALUES (?, ?, ?, ?, 'queue', 'unread', ?);
                """,
                (user_id, user_name, location_id, notif_msg, now_str),
            )

            conn.commit()

            return {
                "id": queue_id,
                "user_id": user_id,
                "user_name": user_name,
                "vehicle_number": vehicle_number,
                "vehicle_type": vehicle_type,
                "location_id": location_id,
                "position": new_position,
                "status": "Waiting",
                "joined_at": now_str,
            }

    def get_queue(
        self, location_id: Optional[int] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve queue entries"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            query = "SELECT q.*, l.name as location_name FROM queue q LEFT JOIN locations l ON q.location_id = l.id WHERE 1=1"
            params: List[Any] = []

            if location_id is not None:
                query += " AND q.location_id = ?"
                params.append(location_id)

            if status:
                query += " AND q.status = ?"
                params.append(status)

            query += " ORDER BY q.status = 'Waiting' DESC, q.position ASC, q.joined_at ASC;"
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def remove_from_queue(self, queue_id: int) -> bool:
        """Remove or cancel a queue item"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM queue WHERE id = ?;", (queue_id,))
            q_item = cur.fetchone()
            if not q_item:
                return False

            loc_id = q_item["location_id"]
            cur.execute("DELETE FROM queue WHERE id = ?;", (queue_id,))

            cur.execute(
                """
                SELECT id FROM queue
                WHERE location_id = ? AND status = 'Waiting'
                ORDER BY position ASC, joined_at ASC;
                """,
                (loc_id,),
            )
            remaining = cur.fetchall()
            for idx, rem in enumerate(remaining, start=1):
                cur.execute("UPDATE queue SET position = ? WHERE id = ?;", (idx, rem["id"]))

            conn.commit()
            return True

    def notify_queue_user(self, queue_id: int, slot_number: Optional[str] = None) -> Dict[str, Any]:
        """Manually trigger notification for a specific queue user"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM queue WHERE id = ?;", (queue_id,))
            q_item = cur.fetchone()
            if not q_item:
                raise ValueError("Queue item not found")

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            snum_str = slot_number or "An Available Slot"
            notif_msg = f"🔔 Parking Slot {snum_str} is now available. {q_item['user_name']} is next in the queue."

            cur.execute(
                """
                UPDATE queue
                SET status = 'Notified', notified_at = ?
                WHERE id = ?;
                """,
                (now_str, queue_id),
            )

            cur.execute(
                """
                INSERT INTO notifications (user_id, user_name, location_id, slot_number, message, type, status, timestamp)
                VALUES (?, ?, ?, ?, ?, 'availability', 'unread', ?);
                """,
                (q_item["user_id"], q_item["user_name"], q_item["location_id"], slot_number, notif_msg, now_str),
            )

            # Re-index remaining
            cur.execute(
                """
                SELECT id FROM queue
                WHERE location_id = ? AND status = 'Waiting'
                ORDER BY position ASC, joined_at ASC;
                """,
                (q_item["location_id"],),
            )
            remaining = cur.fetchall()
            for idx, rem in enumerate(remaining, start=1):
                cur.execute("UPDATE queue SET position = ? WHERE id = ?;", (idx, rem["id"]))

            conn.commit()

            return {
                "success": True,
                "queue_id": queue_id,
                "user_name": q_item["user_name"],
                "message": notif_msg,
                "timestamp": now_str,
            }

    # ==================== FR7 PARKING HISTORY & NOTIFICATIONS ====================

    def get_parking_history(
        self, location_id: Optional[int] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve recent parking activity history"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            query = """
                SELECT h.*, l.name as location_name 
                FROM parking_history h
                LEFT JOIN locations l ON h.location_id = l.id
                WHERE 1=1
            """
            params: List[Any] = []
            if location_id is not None:
                query += " AND h.location_id = ?"
                params.append(location_id)

            query += " ORDER BY h.timestamp DESC, h.id DESC LIMIT ?;"
            params.append(limit)

            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_notifications(
        self, limit: int = 50, unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Retrieve notifications"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            query = """
                SELECT n.*, l.name as location_name
                FROM notifications n
                LEFT JOIN locations l ON n.location_id = l.id
                WHERE 1=1
            """
            params: List[Any] = []
            if unread_only:
                query += " AND n.status = 'unread'"

            query += " ORDER BY n.timestamp DESC, n.id DESC LIMIT ?;"
            params.append(limit)

            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def mark_notification_read(self, notification_id: int) -> bool:
        """Mark a notification as read"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE notifications SET status = 'read' WHERE id = ?;", (notification_id,))
            conn.commit()
            return cur.rowcount > 0

    def mark_all_notifications_read(self) -> int:
        """Mark all notifications as read"""
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE notifications SET status = 'read' WHERE status = 'unread';")
            conn.commit()
            return cur.rowcount

    # ==================== FR5 DASHBOARD STATISTICS ====================

    def get_dashboard_stats(self, location_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculate complete dashboard statistics"""
        self.clean_expired_reservations()
        with get_db_connection(self.db_path) as conn:
            cur = conn.cursor()

            slot_filter = ""
            queue_filter = ""
            params = []
            if location_id is not None:
                slot_filter = "WHERE location_id = ?"
                queue_filter = "WHERE location_id = ? AND status = 'Waiting'"
                params = [location_id]
            else:
                queue_filter = "WHERE status = 'Waiting'"

            cur.execute(
                f"""
                SELECT 
                    COUNT(*) as total_slots,
                    SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available_slots,
                    SUM(CASE WHEN status = 'occupied' THEN 1 ELSE 0 END) as occupied_slots,
                    SUM(CASE WHEN status = 'reserved' THEN 1 ELSE 0 END) as reserved_slots,
                    SUM(CASE WHEN vehicle_type = 'Car' THEN 1 ELSE 0 END) as total_car_slots,
                    SUM(CASE WHEN vehicle_type = 'Car' AND status = 'available' THEN 1 ELSE 0 END) as available_car_slots,
                    SUM(CASE WHEN vehicle_type = 'Car' AND status = 'occupied' THEN 1 ELSE 0 END) as occupied_car_slots,
                    SUM(CASE WHEN vehicle_type = 'Car' AND status = 'reserved' THEN 1 ELSE 0 END) as reserved_car_slots,
                    SUM(CASE WHEN vehicle_type = 'Bike' THEN 1 ELSE 0 END) as total_bike_slots,
                    SUM(CASE WHEN vehicle_type = 'Bike' AND status = 'available' THEN 1 ELSE 0 END) as available_bike_slots,
                    SUM(CASE WHEN vehicle_type = 'Bike' AND status = 'occupied' THEN 1 ELSE 0 END) as occupied_bike_slots,
                    SUM(CASE WHEN vehicle_type = 'Bike' AND status = 'reserved' THEN 1 ELSE 0 END) as reserved_bike_slots
                FROM parking_slots
                {slot_filter};
                """,
                tuple(params),
            )
            slot_stats = cur.fetchone()

            cur.execute(f"SELECT COUNT(*) as q_count FROM queue {queue_filter};", tuple(params))
            queue_stats = cur.fetchone()

            cur.execute("SELECT COUNT(*) as unread_notifs FROM notifications WHERE status = 'unread';")
            notif_stats = cur.fetchone()

            cur.execute("SELECT COUNT(*) as active_res_count FROM reservations WHERE status = 'active';")
            res_stats = cur.fetchone()

            total = slot_stats["total_slots"] or 0
            occupied = slot_stats["occupied_slots"] or 0
            reserved = slot_stats["reserved_slots"] or 0
            available = slot_stats["available_slots"] or 0
            cars_detected = slot_stats["occupied_car_slots"] or 0
            bikes_detected = slot_stats["occupied_bike_slots"] or 0
            queue_count = queue_stats["q_count"] or 0
            unread_count = notif_stats["unread_notifs"] or 0
            active_reservations = res_stats["active_res_count"] or 0

            occupancy_pct = round(((occupied + reserved) / total * 100), 1) if total > 0 else 0.0

            car_total = slot_stats["total_car_slots"] or 0
            car_avail = slot_stats["available_car_slots"] or 0
            car_occ = slot_stats["occupied_car_slots"] or 0
            car_res = slot_stats["reserved_car_slots"] or 0
            car_occ_pct = round(((car_occ + car_res) / car_total * 100), 1) if car_total > 0 else 0.0

            bike_total = slot_stats["total_bike_slots"] or 0
            bike_avail = slot_stats["available_bike_slots"] or 0
            bike_occ = slot_stats["occupied_bike_slots"] or 0
            bike_res = slot_stats["reserved_bike_slots"] or 0
            bike_occ_pct = round(((bike_occ + bike_res) / bike_total * 100), 1) if bike_total > 0 else 0.0

            return {
                "total_slots": total,
                "available_slots": available,
                "occupied_slots": occupied,
                "reserved_slots": reserved,
                "cars_detected": cars_detected,
                "bikes_detected": bikes_detected,
                "users_in_queue": queue_count,
                "active_reservations": active_reservations,
                "occupancy_percentage": occupancy_pct,
                "unread_notifications": unread_count,
                "is_full": available == 0,
                "cars": {
                    "total": car_total,
                    "available": car_avail,
                    "occupied": car_occ,
                    "reserved": car_res,
                    "occupancy_percentage": car_occ_pct,
                    "is_full": car_avail == 0,
                },
                "bikes": {
                    "total": bike_total,
                    "available": bike_avail,
                    "occupied": bike_occ,
                    "reserved": bike_res,
                    "occupancy_percentage": bike_occ_pct,
                    "is_full": bike_avail == 0,
                },
            }


# Singleton database instance
db = DatabaseManager()
