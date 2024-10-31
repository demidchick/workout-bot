EXERCISES = [
    ("Overhead Press", 35, 11, 3, 5),
    ("Bench Press", 16.25, 10, 3, 1.25),
    ("Chest Row", 25, 11, 3, 1.25),
    ("Leg Press", 50, 12, 2, 1.25),
    ("Leg Curl", 30, 12, 2, 10),
    ("Dumbbell Curl", 12.5, 11, 2, 2.5),
    ("Overhead Cable", 30, 10, 2, 5),
    ("Pulldowns", 50, 8, 2, 10),
    ("Cable Crunch", 50, 12, 2, 10),
]

def calculate_next_workout(name, current_weight, current_reps, sets, weight_increment):
    current_volume = current_weight * current_reps * sets
    min_target = current_volume * 1.02
    max_target = current_volume * 1.06
    
    def get_volume(weight, reps):
        return weight * reps * sets
    
    combinations = []
    
    weights_to_try = [
        current_weight + weight_increment,
        current_weight + (2 * weight_increment),
        current_weight,
    ]
    
    lower_weight = current_weight
    for _ in range(3):
        lower_weight -= weight_increment
        if lower_weight > 0:
            weights_to_try.append(lower_weight)
    
    for weight in weights_to_try:
        for reps in range(8, 13):
            volume = get_volume(weight, reps)
            if min_target <= volume <= max_target:
                increase = (volume/current_volume - 1) * 100
                combinations.append((weight, reps, volume, increase))
    
    if not combinations:
        fallback_reps = current_reps + 1
        fallback_volume = get_volume(current_weight, fallback_reps)
        fallback_increase = (fallback_volume/current_volume - 1) * 100
        combinations.append((current_weight, fallback_reps, fallback_volume, fallback_increase))
    
    if not combinations:
        return (name, current_weight, current_reps, 0)
    
    def sort_key(combo):
        weight, reps, volume, increase = combo
        return (abs(5 - increase), -weight, reps)
    
    best = min(combinations, key=sort_key)
    return (name, best[0], best[1], best[3])  # Return tuple instead of string