from __future__ import annotations

from authentication.auth_utils import get_user_allowed_branches


def user_has_branch_access(request, branch_id) -> bool:
    if not request.session.get("user_id") or not branch_id:
        return False
    allowed_ids = {int(branch["id"]) for branch in get_user_allowed_branches(request.session.get("user_id"))}
    try:
        return int(branch_id) in allowed_ids
    except (TypeError, ValueError):
        return False


def posted_record_edit_message():
    return "Posted financial record cannot be edited. Cancel and recreate."


def no_hard_delete_message():
    return "Business records are not hard-deleted. Use cancel/close actions instead."
