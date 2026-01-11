from db import get_connection


def get_user_stats(user_id):
    with get_connection() as conn:
        ratings_count = conn.execute(
            "SELECT COUNT(*) AS total FROM ratings WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
        shortlist_count = conn.execute(
            "SELECT COUNT(*) AS total FROM shortlists WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
    return {"ratings_count": ratings_count, "shortlist_count": shortlist_count}
