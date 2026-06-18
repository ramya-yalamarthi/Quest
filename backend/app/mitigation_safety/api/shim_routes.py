"""410 Gone shims for the routes superseded by this module (MS-26).

The pre-existing SRS routes `POST /mitigate/execute` and `POST /mitigate/rollback`
are replaced by the staged pipeline. Hitting them returns 410 with a pointer.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


router = APIRouter(tags=["mitigation_safety"])


@router.post("/mitigate/execute", status_code=410)
def shim_execute():
    raise HTTPException(
        410,
        detail={
            "error": "Gone",
            "msg": (
                "POST /mitigate/execute is superseded. Use "
                "POST /tickets/{id}/mitigate/stage followed by "
                "POST /tickets/{id}/mitigate/promote."
            ),
            "rfc": "MS-26",
        },
    )


@router.post("/mitigate/rollback", status_code=410)
def shim_rollback():
    raise HTTPException(
        410,
        detail={
            "error": "Gone",
            "msg": (
                "POST /mitigate/rollback is generalized. Use "
                "POST /tickets/{id}/mitigate/revert."
            ),
            "rfc": "MS-26",
        },
    )
