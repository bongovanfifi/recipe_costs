import streamlit as st
from sqlalchemy import text, create_engine
from pathlib import Path


def get_connection():
    """Get database connection"""
    db_path = Path(".streamlit/db.db").absolute()    
    # Create .streamlit directory if it doesn't exist
    db_path.parent.mkdir(exist_ok=True)
    
    # Always try to create tables
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Debug: show tables
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        
        statements = Path(__file__).parent.joinpath("schema.sql").read_text().split(';')
        for statement in statements:
            if statement.strip():  # Skip empty statements
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    if "already exists" not in str(e):
                        raise e
        
        conn.commit()
    
    return st.connection('db', type='sql', url=f"sqlite:///{db_path}")
    