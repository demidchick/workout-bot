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
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    
    conn.commit()
    cur.close()
    conn.close()

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