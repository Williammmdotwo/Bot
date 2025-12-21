from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

Base = declarative_base()

class AIDecision(Base):
    """
    SQLAlchemy model for AI decisions table
    """
    __tablename__ = "ai_decisions"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Unique decision identifier
    decision_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    
    # Input data snapshot
    input_snapshot = Column(Text, nullable=False)
    
    # Final prompt sent to AI
    final_prompt = Column(Text, nullable=False)
    
    # Raw AI response
    ai_raw_response = Column(Text, nullable=False)
    
    # Parsed signal
    parsed_signal = Column(Text, nullable=False)
    
    # Timestamp when record was created
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

def create_ai_decisions_table(database_url: str):
    """
    Create the ai_decisions table in the specified database
    """
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    print("ai_decisions table created successfully")
