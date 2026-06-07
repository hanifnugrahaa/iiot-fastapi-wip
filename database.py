import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Gunakan TURSO_DATABASE_URL jika ada, jika tidak fallback ke sqlite lokal
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
    # Format untuk libsql-experimental: sqlite+libsql://<url>?authToken=<token>&secure=true
    # Pastikan URL dari env disesuaikan, atau jika formatnya sudah lengkap, gunakan langsung.
    # Namun lebih aman menggunakan format sqlite+libsql:// dan mengirim args.
    
    # Jika URL dari env sudah mengandung sqlite+libsql, gunakan saja.
    if TURSO_DATABASE_URL.startswith("libsql://"):
        TURSO_DATABASE_URL = TURSO_DATABASE_URL.replace("libsql://", "sqlite+libsql://", 1)
    elif TURSO_DATABASE_URL.startswith("https://"):
        TURSO_DATABASE_URL = TURSO_DATABASE_URL.replace("https://", "sqlite+libsql://", 1)

    SQLALCHEMY_DATABASE_URL = f"{TURSO_DATABASE_URL}?authToken={TURSO_AUTH_TOKEN}&secure=true"
    
    # Turso / libSQL tidak memerlukan check_same_thread=False karena SQLAlchemy handle connection pool
    connect_args = {'check_same_thread': False}
else:
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./iiot_data.db")
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
