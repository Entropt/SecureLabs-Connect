import sqlite3
from datetime import datetime
from flask import current_app
import os

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(current_app.config['DB_PATH'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    """Initialize the SQLite database for tracking Juice Shop instances"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create instances table
    c.execute('''
    CREATE TABLE IF NOT EXISTS instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        container_id TEXT,
        port INTEGER,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assignment_id TEXT
    )
    ''')
    
    # Create solved challenges table
    c.execute('''
    CREATE TABLE IF NOT EXISTS solved_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        challenge_id INTEGER NOT NULL,
        solved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assignment_id TEXT,
        UNIQUE(user_id, challenge_id, assignment_id)
    )
    ''')
    
    # Create assignment challenges table
    c.execute('''
    CREATE TABLE IF NOT EXISTS assignment_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id TEXT NOT NULL,
        challenge_id INTEGER NOT NULL,
        challenge_name TEXT NOT NULL,
        challenge_description TEXT,
        challenge_difficulty INTEGER,
        UNIQUE(assignment_id, challenge_id)
    )
    ''')
    
    conn.commit()
    conn.close()