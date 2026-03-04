from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.auth.deps import get_current_user
from app.db.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


class UpdateManagerRequest(BaseModel):
    manager_id: UUID | None = None


def manager_only(current: dict) -> None:
    if current.get("role") != "SUPPORT_MANAGER":
        raise HTTPException(status_code=403, detail="Only SUPPORT_MANAGER can manage users")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current=Depends(get_current_user)):
    manager_only(current)
    return db.query(User).order_by(User.created_at.asc()).all()


@router.put("/{user_id}/manager", response_model=UserOut)
def update_user_manager(
    user_id: UUID,
    payload: UpdateManagerRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    manager_only(current)
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.manager_id:
        manager = db.query(User).filter(User.user_id == payload.manager_id).first()
        if not manager:
            raise HTTPException(status_code=404, detail="Manager not found")
        if manager.role != "SUPPORT_MANAGER":
            raise HTTPException(status_code=400, detail="Manager must have SUPPORT_MANAGER role")

    user.manager_id = payload.manager_id
    db.commit()
    db.refresh(user)
    return user
