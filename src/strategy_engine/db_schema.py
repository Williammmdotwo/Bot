from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime

Base = declarative_base()

# Note: AI-related tables have been removed as the system now uses pure technical analysis
# Future tables can be added here for trading signals, performance metrics, etc.
