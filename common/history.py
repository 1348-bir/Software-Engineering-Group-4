"""Shared JSON response for session-scoped game history polling."""

from flask import jsonify, request


def history_response(db, uid, statistics):
    """Return up to 50 recent records and statistics for the given user."""
    try:
        after_id = int(request.args.get('after', 0))
    except (ValueError, TypeError):
        return jsonify(error='after must be an integer'), 400
    rows = db.recent_attempts(uid, limit=50)
    return jsonify({
        'attempts': [row for row in rows if row['id'] > after_id],
        'stats': statistics(uid),
        'latest_id': rows[0]['id'] if rows else after_id,
    })
