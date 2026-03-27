from backend.db import get_db


def get_user_by_id(user_id):
    if not user_id:
        return None
    row = get_db().execute(
        "SELECT id, google_sub, email, name, avatar_url, created_at, last_login_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_google_sub(google_sub):
    if not google_sub:
        return None
    row = get_db().execute(
        "SELECT id, google_sub, email, name, avatar_url, created_at, last_login_at FROM users WHERE google_sub = ?",
        (google_sub,),
    ).fetchone()
    return dict(row) if row else None


def upsert_google_user(*, google_sub, email, name, avatar_url=None):
    db = get_db()
    existing = get_user_by_google_sub(google_sub)
    if existing:
        db.execute(
            """
            UPDATE users
            SET email = ?, name = ?, avatar_url = ?, last_login_at = CURRENT_TIMESTAMP
            WHERE google_sub = ?
            """,
            (email, name, avatar_url, google_sub),
        )
        db.commit()
        return get_user_by_google_sub(google_sub)

    cursor = db.execute(
        """
        INSERT INTO users (google_sub, email, name, avatar_url)
        VALUES (?, ?, ?, ?)
        """,
        (google_sub, email, name, avatar_url),
    )
    db.commit()
    return get_user_by_id(cursor.lastrowid)
