import psycopg2
from datetime import datetime
import os
from urllib.parse import urlparse
import logging

def get_db_connection():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    result = urlparse(database_url)
    connection = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )
    return connection

def init_db():
    logging.info("Attempting to initialize database...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        logging.info("Creating progression_history table...")
        cur.execute('''
            CREATE TABLE IF NOT EXISTS progression_history (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                exercise VARCHAR(100),
                old_weight FLOAT,
                new_weight FLOAT,
                weight_change FLOAT,
                old_reps INTEGER,
                new_reps INTEGER,
                reps_change INTEGER,
                old_volume FLOAT8,
                new_volume FLOAT8,
                volume_change_percent FLOAT8
            )
        ''')
        
        # Create exercises table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS exercises (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE,
                weight FLOAT,
                reps INTEGER,
                sets INTEGER,
                increment FLOAT,
                last_update TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Verify that exercises table has data
        cur.execute('SELECT COUNT(*) FROM exercises')
        if cur.fetchone()[0] == 0:
            logging.error("Exercises table is empty! Please populate the table with exercise data.")
            raise ValueError("Exercises table is empty")
        
        conn.commit()
        logging.info("Tables verified successfully!")
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        raise e

def log_progression(exercise_name, old_weight, new_weight, old_reps, new_reps):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get sets from exercises table
        cur.execute("SELECT sets FROM exercises WHERE name = %s", (exercise_name,))
        result = cur.fetchone()
        if not result:
            raise ValueError(f"Could not find sets for exercise {exercise_name}")
        sets = result[0]
        
        # Calculate volumes and changes
        old_volume = old_weight * old_reps * sets
        new_volume = new_weight * new_reps * sets
        volume_change_percent = ((new_volume / old_volume) - 1) * 100 if old_volume > 0 else 0
        weight_change = round(new_weight - old_weight, 2)
        reps_change = new_reps - old_reps
        
        # Insert into progression_history
        cur.execute("""
            INSERT INTO progression_history 
            (timestamp, exercise, old_weight, new_weight, weight_change, 
             old_reps, new_reps, reps_change,
             old_volume, new_volume, volume_change_percent)
            VALUES 
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            datetime.now(),
            exercise_name,
            old_weight,
            new_weight,
            weight_change,
            old_reps,
            new_reps,
            reps_change,
            round(old_volume, 2),
            round(new_volume, 2),
            round(volume_change_percent, 2)
        ))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def get_progression_history():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT * FROM progression_history 
            ORDER BY timestamp DESC 
            LIMIT 50
        ''')
        
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return rows
    except Exception as e:
        logging.error(f"Error getting progression history: {str(e)}")
        return []