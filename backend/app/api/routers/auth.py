from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.auth.jwt import create_access_token
from app.mcp.tools import ensure_user, get_user_by_email
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

HARDCODED = {
    "saakshi@support.ai": {"password": "password123", "display_name": "Saakshi Gupta", "role": "REQUESTER"},
    "anjali@support.ai": {"password": "password123", "display_name": "Anjali Mamidi", "role": "SUPPORT"},
    "subbu@support.ai": {"password": "password123", "display_name": "Subbu", "role": "SUPPORT_MANAGER"},
}

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    entry = HARDCODED.get(payload.email)
    if not entry or entry["password"] != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = ensure_user(db, email=payload.email, display_name=entry["display_name"], role=entry["role"])

    token = create_access_token({
        "user_id": str(user.user_id),
        "email": user.email,
        "role": user.role,
        "display_name": user.display_name,
    })

    return {"access_token": token, "token_type": "bearer", "user": UserOut.model_validate(user)}

@router.get("/me", response_model=UserOut)
def me(current=Depends(__import__("app.auth.deps", fromlist=["get_current_user"]).get_current_user), db: Session = Depends(get_db)):
    # current contains claims
    user = get_user_by_email(db, current["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user