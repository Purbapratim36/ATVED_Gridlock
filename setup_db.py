"""
ATVED GridLock — Database Setup & Seed Script

Seeds the database with:
- 3 real demo users (with fake Aadhaar for login)
- 7 additional synthetic drivers
- 5 camera locations with lat/lng
- Various vehicle plates

Run: python setup_db.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

from atved.db.models import Base, Driver, RegisteredPlate, Camera, CameraStatus

DATABASE_URL = "sqlite+aiosqlite:///atved.db"


# ---------------------------------------------------------------------------
# Demo Users (Real team members for hackathon demo)
# ---------------------------------------------------------------------------
DEMO_USERS = [
    {
        "name": "Kunaljit Kashyap",
        "email": "kunaljit@gridlock.demo",
        "phone": "9678620969",
        "aadhaar_number": "4832 7651 9023",  # Fake Aadhaar for demo login
        "bank_account_masked": "XXXX-XXXX-4521",
        "bank_name": "State Bank of India",
        "bank_balance": 75000.0,
        "vehicle_make": "Honda",
        "vehicle_model": "Activa 6G",
        "vehicle_color": "Black",
        "plates": ["AS 01 KK 4521"],
        "traffic_score": 1000,
    },
    {
        "name": "Purba Pratim Mahanta",
        "email": "purba@gridlock.demo",
        "phone": "6000605406",
        "aadhaar_number": "7156 3248 0917",  # Fake Aadhaar for demo login
        "bank_account_masked": "XXXX-XXXX-7823",
        "bank_name": "HDFC Bank",
        "bank_balance": 62000.0,
        "vehicle_make": "Royal Enfield",
        "vehicle_model": "Classic 350",
        "vehicle_color": "Gunmetal Grey",
        "plates": ["AS 03 PM 7823"],
        "traffic_score": 1000,
    },
    {
        "name": "Mayur",
        "email": "mayur@gridlock.demo",
        "phone": "7002870742",
        "aadhaar_number": "6289 4073 1548",  # Fake Aadhaar for demo login
        "bank_account_masked": "XXXX-XXXX-3190",
        "bank_name": "ICICI Bank",
        "bank_balance": 48000.0,
        "vehicle_make": "TVS",
        "vehicle_model": "Apache RTR 160",
        "vehicle_color": "Red",
        "plates": ["AS 05 MY 3190"],
        "traffic_score": 1000,
    },
]

# ---------------------------------------------------------------------------
# Synthetic Drivers (for demo variety)
# ---------------------------------------------------------------------------
SYNTHETIC_USERS = [
    {
        "name": "Rahul Sharma",
        "email": "rahul@example.com",
        "phone": "9876543210",
        "aadhaar_number": "5123 4567 8901",
        "bank_account_masked": "XXXX-XXXX-5678",
        "bank_name": "Punjab National Bank",
        "bank_balance": 35000.0,
        "vehicle_make": "Maruti Suzuki",
        "vehicle_model": "Swift",
        "vehicle_color": "White",
        "plates": ["MH 12 RS 5678"],
        "traffic_score": 720,
    },
    {
        "name": "Priya Devi",
        "email": "priya@example.com",
        "phone": "9988776655",
        "aadhaar_number": "3456 7890 1234",
        "bank_account_masked": "XXXX-XXXX-8901",
        "bank_name": "Axis Bank",
        "bank_balance": 92000.0,
        "vehicle_make": "Hyundai",
        "vehicle_model": "i20",
        "vehicle_color": "Blue",
        "plates": ["DL 3C PD 8901"],
        "traffic_score": 950,
    },
    {
        "name": "Amit Kumar",
        "email": "amit@example.com",
        "phone": "9112233445",
        "aadhaar_number": "8901 2345 6789",
        "bank_account_masked": "XXXX-XXXX-2345",
        "bank_name": "Bank of Baroda",
        "bank_balance": 18000.0,
        "vehicle_make": "Bajaj",
        "vehicle_model": "Pulsar NS200",
        "vehicle_color": "Black",
        "plates": ["KA 01 AK 2345"],
        "traffic_score": 380,
    },
    {
        "name": "Sneha Gupta",
        "email": "sneha@example.com",
        "phone": "9001122334",
        "aadhaar_number": "2345 6789 0123",
        "bank_account_masked": "XXXX-XXXX-6789",
        "bank_name": "Kotak Mahindra Bank",
        "bank_balance": 120000.0,
        "vehicle_make": "Tata",
        "vehicle_model": "Nexon EV",
        "vehicle_color": "Teal Blue",
        "plates": ["TN 09 SG 6789"],
        "traffic_score": 880,
    },
    {
        "name": "Deepak Singh",
        "email": "deepak@example.com",
        "phone": "9887766554",
        "aadhaar_number": "6789 0123 4567",
        "bank_account_masked": "XXXX-XXXX-0123",
        "bank_name": "Union Bank of India",
        "bank_balance": 8500.0,
        "vehicle_make": "Hero",
        "vehicle_model": "Splendor Plus",
        "vehicle_color": "Silver",
        "plates": ["UP 14 DS 0123"],
        "traffic_score": 150,
    },
    {
        "name": "Ananya Borah",
        "email": "ananya@example.com",
        "phone": "9776655443",
        "aadhaar_number": "1234 5678 9012",
        "bank_account_masked": "XXXX-XXXX-5432",
        "bank_name": "State Bank of India",
        "bank_balance": 55000.0,
        "vehicle_make": "Honda",
        "vehicle_model": "City",
        "vehicle_color": "Platinum White",
        "plates": ["AS 02 AB 5432"],
        "traffic_score": 550,
    },
    {
        "name": "Vikram Choudhury",
        "email": "vikram@example.com",
        "phone": "9665544332",
        "aadhaar_number": "9012 3456 7890",
        "bank_account_masked": "XXXX-XXXX-7654",
        "bank_name": "HDFC Bank",
        "bank_balance": 42000.0,
        "vehicle_make": "Yamaha",
        "vehicle_model": "FZ-S V3",
        "vehicle_color": "Matte Black",
        "plates": ["AS 06 VC 7654"],
        "traffic_score": 650,
    },
]

# ---------------------------------------------------------------------------
# Camera Locations (Guwahati, Assam — for the demo)
# ---------------------------------------------------------------------------
CAMERAS = [
    {
        "external_id": "CAM-GHY-001",
        "location_name": "Dispur Last Gate Junction",
        "latitude": 26.1445,
        "longitude": 91.7882,
        "stream_url": "rtsp://demo/cam1",
        "status": CameraStatus.HEALTHY,
    },
    {
        "external_id": "CAM-GHY-002",
        "location_name": "Ganeshguri Flyover",
        "latitude": 26.1525,
        "longitude": 91.7758,
        "stream_url": "rtsp://demo/cam2",
        "status": CameraStatus.HEALTHY,
    },
    {
        "external_id": "CAM-GHY-003",
        "location_name": "Zoo Road Tiniali",
        "latitude": 26.1736,
        "longitude": 91.7651,
        "stream_url": "rtsp://demo/cam3",
        "status": CameraStatus.HEALTHY,
    },
    {
        "external_id": "CAM-GHY-004",
        "location_name": "Paltan Bazaar Railway Station",
        "latitude": 26.1850,
        "longitude": 91.7467,
        "stream_url": "rtsp://demo/cam4",
        "status": CameraStatus.HEALTHY,
    },
    {
        "external_id": "CAM-GHY-005",
        "location_name": "Maligaon Chariali",
        "latitude": 26.1922,
        "longitude": 91.7289,
        "stream_url": "rtsp://demo/cam5",
        "status": CameraStatus.DEGRADED,
    },
]


async def setup():
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    print("=" * 60)
    print("  ATVED GridLock — Database Setup")
    print("=" * 60)

    # Drop and recreate all tables for clean demo
    print("\n📦 Creating all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created.\n")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:

        # ── Insert Demo Users ──────────────────────────────────────
        print("👤 Inserting DEMO users (team members):")
        for user_data in DEMO_USERS:
            driver = Driver(
                name=user_data["name"],
                email=user_data["email"],
                phone=user_data["phone"],
                aadhaar_number=user_data["aadhaar_number"],
                password_hash="demo_hash",
                is_registered=True,
                traffic_score=user_data["traffic_score"],
                bank_account_masked=user_data["bank_account_masked"],
                bank_name=user_data["bank_name"],
                bank_balance=user_data["bank_balance"],
                vehicle_make=user_data["vehicle_make"],
                vehicle_model=user_data["vehicle_model"],
                vehicle_color=user_data["vehicle_color"],
            )
            session.add(driver)
            await session.flush()

            for plate_text in user_data["plates"]:
                plate = RegisteredPlate(driver_id=driver.id, plate_text=plate_text)
                session.add(plate)

            print(f"   ✅ {user_data['name']}")
            print(f"      Aadhaar: {user_data['aadhaar_number']}")
            print(f"      Phone: {user_data['phone']}")
            print(f"      Plate: {', '.join(user_data['plates'])}")
            print(f"      Bank: {user_data['bank_name']} ({user_data['bank_account_masked']})")
            print()

        # ── Insert Synthetic Users ─────────────────────────────────
        print("👥 Inserting synthetic drivers:")
        for user_data in SYNTHETIC_USERS:
            driver = Driver(
                name=user_data["name"],
                email=user_data["email"],
                phone=user_data["phone"],
                aadhaar_number=user_data["aadhaar_number"],
                password_hash="mock_hash",
                is_registered=True,
                traffic_score=user_data["traffic_score"],
                bank_account_masked=user_data["bank_account_masked"],
                bank_name=user_data["bank_name"],
                bank_balance=user_data["bank_balance"],
                vehicle_make=user_data["vehicle_make"],
                vehicle_model=user_data["vehicle_model"],
                vehicle_color=user_data["vehicle_color"],
            )
            session.add(driver)
            await session.flush()

            for plate_text in user_data["plates"]:
                plate = RegisteredPlate(driver_id=driver.id, plate_text=plate_text)
                session.add(plate)

            print(f"   ✅ {user_data['name']} | Score: {user_data['traffic_score']} | Plate: {', '.join(user_data['plates'])}")

        # ── Insert Cameras ─────────────────────────────────────────
        print("\n📷 Inserting camera locations:")
        for cam_data in CAMERAS:
            cam = Camera(
                external_id=cam_data["external_id"],
                location_name=cam_data["location_name"],
                latitude=cam_data["latitude"],
                longitude=cam_data["longitude"],
                stream_url=cam_data["stream_url"],
                status=cam_data["status"],
            )
            session.add(cam)
            status_icon = "🟢" if cam_data["status"] == CameraStatus.HEALTHY else "🟡"
            print(f"   {status_icon} {cam_data['external_id']} — {cam_data['location_name']} ({cam_data['latitude']}, {cam_data['longitude']})")

        await session.commit()

    await engine.dispose()

    print("\n" + "=" * 60)
    print("  ✅ Database seeded successfully!")
    print("=" * 60)
    print("\n🔑 Demo Login Credentials (Aadhaar → OTP):")
    print("─" * 50)
    for u in DEMO_USERS:
        print(f"  {u['name']}")
        print(f"    Aadhaar: {u['aadhaar_number']}")
        print(f"    Phone:   {u['phone']} (OTP will be sent here)")
        print()


if __name__ == "__main__":
    asyncio.run(setup())
