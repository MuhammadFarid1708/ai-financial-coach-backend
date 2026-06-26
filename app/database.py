import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load local .env variables for local development
load_dotenv()

# Explicitly check for Render's environment variable first
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    print("--- PRODUCTION DATABASE VARIABLE DETECTED ---")
    # Fix Render/Neon default prefix mismatch
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    # Force psycopg driver mapping injection
    if "postgresql://" in DATABASE_URL and "+psycopg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    print("--- WARNING: NO DATABASE_URL DETECTED IN ENVIRONMENT ---")
    # Fallback to local dev database ONLY if we aren't on Render
    DATABASE_URL = "postgresql+psycopg://postgres:password@localhost:5432/ai_financial_coach"

print(f"Connecting to database endpoint target prefix: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()