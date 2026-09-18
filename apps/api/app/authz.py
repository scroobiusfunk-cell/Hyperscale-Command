"""Who may see what.

One module rather than a check inlined in each route, because an authorization
rule that lives in three places is a rule that is wrong in one of them. Q28 was
exactly that shape: the evidence image route checked that the caller was a real
user and nothing else, so any authenticated account could read any photograph in
any project by id.

**What this cannot yet express.** There is no project membership anywhere in the
schema — `AppUser` carries global roles and nothing ties a person to a project.
So "a reviewer may see evidence on their own projects" is not sayable here, and
a reviewer's reach is every project in the deployment. That is tolerable for a
single-project pilot and is not tolerable for the second project. Narrowing it
needs a membership table, which is a real modelling decision rather than
something to invent in an authorization helper. See Q28.
"""

from __future__ import annotations

from app.models.enums import UserRole
from app.models.evidence import Evidence
from app.models.identity import AppUser

#: Roles whose job is looking at other people's evidence.
_REVIEWING_ROLES = frozenset({UserRole.REVIEWER, UserRole.ADMIN})


def may_view_evidence(user: AppUser, evidence: Evidence) -> bool:
    """Whether this person may look at this photograph.

    A reviewer or an admin may, because judging evidence is the job. Anyone else
    may see only what they captured themselves — which is what lets a tech read
    "too blurry to read the label" next to the photograph it is about, without
    opening the whole project's evidence to everyone holding a login.
    """
    if not user.is_active:
        return False
    if _REVIEWING_ROLES & set(user.roles):
        return True
    return evidence.captured_by == user.id


def may_handle_exports(user: AppUser) -> bool:
    """Whether this person may build, download or confirm a results package.

    A package is the whole project's rulings in one file, with the failures
    called out and the photographs alongside — every judgement made on the job,
    downloadable by anybody who can reach the endpoint. The routes had no role
    check at all, which mattered less while nothing served the bytes and matters
    now that the console does.

    The same set as reviewing, and for the same reason: confirming a package was
    entered into CxAlloy is an assertion about the system of record, and it
    clears the undelivered count for everybody. It is not a thing to leave open
    to any account holding a login.
    """
    return user.is_active and bool(_REVIEWING_ROLES & set(user.roles))
