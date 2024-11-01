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
                reason VARCHAR(50)
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
        
        # Initialize with default exercises if table is empty
        cur.execute('SELECT COUNT(*) FROM exercises')
        if cur.fetchone()[0] == 0:
            initial_exercises = [
                ("Overhead Press", 35, 11, 3, 5),
                ("Bench Press", 16.25, 10, 3, 1.25),
                ("Chest Row", 25, 11, 3, 1.25),
                ("Leg Press", 50, 12, 2, 1.25),
                ("Leg Curl", 30, 12, 2, 10),
                ("Dumbbell Curl", 12.5, 11, 2, 2.5),
                ("Overhead Cable", 30, 10, 2, 5),
                ("Pulldowns", 50, 8, 2, 10),
                ("Cable Crunch", 50, 12, 2, 10)
            ]
            
            for name, weight, reps, sets, increment in initial_exercises:
                cur.execute('''
                    INSERT INTO exercises (name, weight, reps, sets, increment)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO NOTHING
                ''', (name, weight, reps, sets, increment))
        
        conn.commit()
        logging.info("Table created successfully!")
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        raise e

def log_progression(exercise_name, old_weight, new_weight, old_reps, new_reps, reason):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        weight_change = round(new_weight - old_weight, 2)
        reps_change = new_reps - old_reps
        
        cur.execute('''
            INSERT INTO progression_history 
            (timestamp, exercise, old_weight, new_weight, weight_change, 
             old_reps, new_reps, reps_change, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            datetime.now(),
            exercise_name,
            old_weight,
            new_weight,
            weight_change,
            old_reps,
            new_reps,
            reps_change,
            reason
        ))
        
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Error logging progression: {str(e)}")

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