from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def session_factory(database_url: str) -> sessionmaker[Session]:
    url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return sessionmaker(create_engine(url, pool_pre_ping=True))
