import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load local .env variables if present
load_dotenv()

# Prioritize the environment variable from Render
DATABASE_URL = os.getenv("DATABASE_URL")

# Production safety checks for drivers
if DATABASE_URL:
    # 1. Render/Neon might provide 'postgres://', but SQLAlchemy requires 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # 2. Add driver compatibility for psycopg if needed
    if "postgresql://" in DATABASE_URL and "+psycopg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    # Fallback default value if completely missing (for absolute safety)
    DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/ai_financial_coach"

# Create the engine with the corrected production URL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()