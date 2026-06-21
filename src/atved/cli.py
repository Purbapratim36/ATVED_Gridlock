"""Command line interface for ATVED administrative tasks."""

from __future__ import annotations

import asyncio
import uuid
import click
import structlog
from datetime import datetime

from atved.db.session import async_session_maker
from atved.db.models import StaffUser, StaffRole
from atved.core.security import hash_password

logger = structlog.get_logger(__name__)

@click.group()
def cli():
    """ATVED administrative CLI."""
    pass

@cli.command()
@click.option("--username", required=True, prompt=True)
@click.option("--email", required=True, prompt=True)
@click.option("--password", required=True, prompt=True, hide_input=True)
def create_admin(username: str, email: str, password: str):
    """Create an initial administrator account."""
    async def _create():
        async with async_session_maker() as session:
            user = StaffUser(
                username=username,
                email=email,
                password_hash=hash_password(password),
                role=StaffRole.ADMIN,
                is_active=True
            )
            session.add(user)
            await session.commit()
            click.echo(f"Admin user {username} created successfully.")
            
    asyncio.run(_create())

if __name__ == "__main__":
    cli()
