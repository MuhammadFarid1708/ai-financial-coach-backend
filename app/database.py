import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Hardcoded production database URL with the correct psycopg driver
DATABASE_URL = "postgresql+psycopg://postgre:MaMdlhgKCEl5DNeV5g7R9TRyYNwVuzQV@dpg-d8v4u3ugvqtc73bqn1e0-a.singapore-postgres.render.com/ai_financial_coach"

print("--- FORCING PRODUCTION CONNECTION TO RENDER POSTGRES ---")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()