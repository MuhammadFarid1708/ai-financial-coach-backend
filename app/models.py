import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, Boolean, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    # Primary Key as a native PostgreSQL UUID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    username = Column(String(255), nullable=True)


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ForeignKey linking to users.id using a strict native UUID type definition
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Core User Financial Parameters
    monthly_income = Column(Float, default=0.0)
    monthly_expenses = Column(Float, default=0.0)
    savings_goal = Column(Float, default=0.0)
    risk_tolerance = Column(String, default="Moderate")


class AIInsight(Base):
    __tablename__ = "ai_insights"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Conversational Threads tracked natively via unique UUID session keys
    session_id = Column(UUID(as_uuid=True), index=True, default=uuid.uuid4, nullable=False)
    
    # Request & Structural Content Tracking
    user_prompt = Column(String, nullable=False)
    conversational_response = Column(String, nullable=False)
    
    # Frontend Rendering Visual Indicators
    chart_bool = Column(Boolean, default=False)
    chart_data = Column(JSON, nullable=True) 
    
    category = Column(String, default="Custom Goal Strategy")