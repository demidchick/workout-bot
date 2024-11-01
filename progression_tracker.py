import csv
from datetime import datetime
import os

def log_progression(exercise_name, old_weight, new_weight, old_reps, new_reps, reason):
    filename = 'progression_history.csv'
    file_exists = os.path.isfile(filename)
    
    with open(filename, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # Write headers if file is new
        if not file_exists:
            writer.writerow(['timestamp', 'exercise', 'old_weight', 'new_weight', 
                           'weight_change', 'old_reps', 'new_reps', 'reps_change', 'reason'])
        
        # Calculate changes
        weight_change = round(new_weight - old_weight, 2)
        reps_change = new_reps - old_reps
        
        # Write the progression data
        writer.writerow([
            datetime.now().isoformat(),
            exercise_name,
            old_weight,
            new_weight,
            weight_change,
            old_reps,
            new_reps,
            reps_change,
            reason
        ]) 