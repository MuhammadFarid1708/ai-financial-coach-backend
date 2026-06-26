from uuid import UUID
from pydantic import BaseModel, EmailStr
from typing import Optional

# ─── USER SCHEMAS ───
class UserCreate(BaseModel):
    email: str
    username: str  # Add this line
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: str
    username: Optional[str] = None  # Add this line so it returns the username safely

    class Config:
        from_attributes = True  # Or orm_mode = True if using Pydantic v1


# ─── FINANCIAL PROFILE SCHEMAS ───
class FinancialProfileCreate(BaseModel):
    monthly_income: float
    monthly_expenses: float
    savings_goal: float
    risk_tolerance: str

class FinancialProfileResponse(BaseModel):
    id: int
    user_id: UUID
    monthly_income: float
    monthly_expenses: float
    savings_goal: float
    risk_tolerance: str

    class Config:
        from_attributes = True