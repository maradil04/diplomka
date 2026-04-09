from backend.db import get_db


def get_user_by_id(user_id):
    if not user_id:
        return None
    row = get_db().execute(
        "SELECT id, google_sub, email, name, avatar_url, created_at, last_login_at FROM users WHERE id = %s",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_user_by_google_sub(google_sub):
    if not google_sub:
        return None
    row = get_db().execute(
        "SELECT id, google_sub, email, name, avatar_url, created_at, last_login_at FROM users WHERE google_sub = %s",
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
            SET email = %s, name = %s, avatar_url = %s, last_login_at = CURRENT_TIMESTAMP
            WHERE google_sub = %s
            """,
            (email, name, avatar_url, google_sub),
        )
        db.commit()
        return get_user_by_google_sub(google_sub)

    row = db.execute(
        """
        INSERT INTO users (google_sub, email, name, avatar_url)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (google_sub, email, name, avatar_url),
    ).fetchone()
    db.commit()
    return get_user_by_id(row["id"])
