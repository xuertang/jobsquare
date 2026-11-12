"""FastAPI dependencies shared by the routers."""
from __future__ import annotations

from typing import Iterator

from fastapi import HTTPException, Request

from . import db


def get_conn(request: Request) -> Iterator:
    """One connection per request: commit on success, roll back on error."""
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def found(row, what: str = "item"):
    if row is None:
        raise HTTPException(404, f"{what} not found")
    return row
