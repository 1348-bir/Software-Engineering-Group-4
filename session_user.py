"""Shared anonymous browser identity for practice and game histories."""
from uuid import uuid4
from flask import session


def current_user():
    if 'uid' not in session:
        session['uid'] = uuid4().hex[:16]
    return session['uid']
