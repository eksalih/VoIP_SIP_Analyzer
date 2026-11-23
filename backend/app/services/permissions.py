"""
Roles and permissions (v2.3.0).

  admin       everything (users, settings, deletion)
  supervisor  all calls, play and download recordings, upload/analyse captures
  user        only calls involving their own extensions; may play (not download) those recordings

A role is just a set of permissions, so adding a role or moving a permission is a one-line change.
"""
from fastapi import HTTPException
from sqlalchemy import false, or_

from app.models.call import Call

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "supervisor": {"calls.view_all", "recordings.play", "recordings.download", "analysis.use"},
    "user": {"calls.view_own", "recordings.play"},
}


def has_permission(user, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(user.role, set())
    return "*" in perms or permission in perms


def call_scope(user):
    """
    SQL condition limiting calls to what the user may see, or None for no limit.
    Raises 403 for a role that may not view calls at all.
    """
    if has_permission(user, "calls.view_all"):
        return None
    if has_permission(user, "calls.view_own"):
        exts = user.extension_list
        return or_(Call.caller.in_(exts), Call.called.in_(exts)) if exts else false()
    raise HTTPException(status_code=403, detail="Not allowed to view calls")


def can_access_call(user, call: Call) -> bool:
    if has_permission(user, "calls.view_all"):
        return True
    if has_permission(user, "calls.view_own"):
        exts = set(user.extension_list)
        return call.caller in exts or call.called in exts
    return False
