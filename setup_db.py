"""Initialize the database and insert a mock driver for the demo.

This script bypasses the ATVED config system and connects directly
to the Docker Compose PostgreSQL instance.
"""

import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

# Import all models so Base.metadata knows about every table
from atved.db.models import Base, Driver, RegisteredPlate

DATABASE_URL = "postgresql+asyncpg://atved:atved_password@localhost:5432/atved_db"

async def setup():
    engine = create_async_engine(
        DATABASE_URL,
        echo=True,
        connect_args={"ssl": False},          # Docker Postgres has no SSL
    )

    print("Creating all tables …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.\n")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Check if driver already exists
        res = await session.execute(
            select(Driver).where(Driver.email == "john@example.com")
        )
        driver = res.scalar_one_or_none()

        if driver is None:
            driver = Driver(
                name="John Doe",
                email="john@example.com",
                password_hash="mock_hash",
                is_registered=True,
                traffic_score=1000,
            )
            session.add(driver)
            await session.commit()
            await session.refresh(driver)

            plate = RegisteredPlate(
                driver_id=driver.id, plate_text="MH 12 AB 1234"
            )
            session.add(plate)
            await session.commit()
            print("[OK] Mock driver 'John Doe' + plate 'MH 12 AB 1234' inserted.")
        else:
            print("[INFO] Driver already exists - skipping insert.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(setup())
