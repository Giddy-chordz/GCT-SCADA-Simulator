print("connecting to db...")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from .config import DATABASE_URL


#base class for models
Base = declarative_base()

#dataabase url
SQLALCHEMY_DATABASE_URL = DATABASE_URL

#setup engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

#setup session
SessionLocal = sessionmaker(autocommit = False, autoflush = False, bind = engine)

#setup dependencies to get database session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

print("database connected!")
