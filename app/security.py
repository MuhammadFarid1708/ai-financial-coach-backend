import os
from datetime import datetime, timedelta
import jwt
import bcrypt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your_fallback_super_secret_key_here")
ALGORITHM = "HS256"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against its stored bcrypt hash."""
    try:
        # Convert strings to bytes for native bcrypt execution
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hashes a password securely using modern native bcrypt."""
    # Generate a salt and hash the password string as bytes
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    # Return it as a clean string to be stored smoothly in PostgreSQL
    return hashed_bytes.decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Generates a secure asymmetric JWT access token for authentication."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt