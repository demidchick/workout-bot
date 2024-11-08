def calculate_next_workout(name, current_weight, current_reps, sets, weight_increment):
    current_volume = current_weight * current_reps * sets
    min_target = current_volume * 1.02
    max_target = current_volume * 1.06
    
    def get_volume(weight, reps):
        return weight * reps * sets
    
    combinations = []
    
    # Expanded weight options in a more logical order
    weights_to_try = [
        current_weight + (2 * weight_increment),
        current_weight + weight_increment,
        current_weight,
        current_weight - weight_increment,
        current_weight - (2 * weight_increment),
    ]
    
    # Try all valid weight/rep combinations
    for weight in weights_to_try:
        if weight <= 0:  # Skip invalid weights
            continue
        for reps in range(6, 16):  # 6-15 rep range
            volume = get_volume(weight, reps)
            if min_target <= volume <= max_target:
                increase = (volume/current_volume - 1) * 100
                if 2 <= increase <= 6:  # Only add combinations within our target range
                    combinations.append((weight, reps, volume, increase))
    
    # Fallback logic
    if not combinations and current_reps < 15:
        # First fallback: try adding one rep at current weight
        fallback_reps = current_reps + 1
        fallback_volume = get_volume(current_weight, fallback_reps)
        fallback_increase = (fallback_volume/current_volume - 1) * 100
        if 2 <= fallback_increase <= 6:  # Only add if within range
            combinations.append((current_weight, fallback_reps, fallback_volume, fallback_increase))
        
        # Second fallback: try adding one rep at lower weight
        lower_weight = current_weight - weight_increment
        if lower_weight > 0:
            lower_volume = get_volume(lower_weight, fallback_reps)
            lower_increase = (lower_volume/current_volume - 1) * 100
            if 2 <= lower_increase <= 6:  # Only add if within range
                combinations.append((lower_weight, fallback_reps, lower_volume, lower_increase))
    
    if not combinations:
        return (name, current_weight, current_reps, 0)
    
    def sort_key(combo):
        weight, reps, volume, increase = combo
        # Prioritize: minimum increase within 2-6% range, closest to current weight, closest to current reps
        return (
            increase,  # Choose minimum increase (since all values are already within 2-6% range)
            abs(weight - current_weight),
            abs(reps - current_reps)
        )
    
    best = min(combinations, key=sort_key)
    return (name, best[0], best[1], best[3])
