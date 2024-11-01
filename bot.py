import logging
from datetime import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from config import TOKEN
from workout_calculator import calculate_next_workout
from progression_tracker import log_progression

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Initialize from EXERCISES only if data.json doesn't exist
        from exercises import EXERCISES
        initial_data = {
            "exercises": [
                {
                    "name": name,
                    "weight": weight,
                    "reps": reps,
                    "sets": sets,
                    "increment": increment
                }
                for name, weight, reps, sets, increment in EXERCISES
            ],
            "last_update": None
        }
        save_data(initial_data)  # Save initial data
        return initial_data

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)

def get_display_name(exercise_name):
    name_mapping = {
        'Overhead Press': 'Shoulders',
        'Bench Press': 'Chest',
        'Chest Row': 'Back',
        'Leg Press': 'Glutes',
        'Leg Curl': 'Hams',
        'Dumbbell Curl': 'Biceps',
        'Overhead Cable': 'Triceps 1',
        'Pulldowns': 'Triceps 2',
        'Cable Crunch': 'Core'
    }
    return name_mapping.get(exercise_name, exercise_name)

def format_workout_message(exercises, title, show_volume_change=False):
    message = f"*{title}*\n\n"
    if show_volume_change:
        message += "`Exercise    Weight Reps  %`\n"
        message += "`─────────────────────────`\n"
        
        for exercise in exercises:
            volume_change = exercise.get('volume_change', 0)
            name = exercise['name'][:10]  # Truncate name to 10 chars
            message += f"`{name:<10} {exercise['weight']:>5.1f} {exercise['reps']:>3d} {volume_change:>+3.0f}`\n"
    else:
        message += "`Exercise    Weight Reps`\n"
        message += "`────────────────────`\n"
        
        for exercise in exercises:
            name = exercise['name'][:10]  # Truncate name to 10 chars
            message += f"`{name:<10} {exercise['weight']:>5.1f} {exercise['reps']:>3d}`\n"
    
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your workout progression bot.\n"
        "Use /current to see current weights\n"
        "Use /plan_next to see next workout targets"
    )

async def current_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    message = format_workout_message(data['exercises'], "Current workout targets:")
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def next_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    next_exercises = []
    
    for exercise in data['exercises']:
        result = calculate_next_workout(
            exercise['name'],
            exercise['weight'],
            exercise['reps'],
            exercise['sets'],
            exercise['increment']
        )
        name, weight, reps, volume_change = result
        next_exercises.append({
            'name': name,
            'weight': weight,
            'reps': reps,
            'sets': exercise['sets'],
            'volume_change': volume_change
        })
    
    message = format_workout_message(next_exercises, "Next workout targets:", show_volume_change=True)
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def create_exercise_checklist():
    data = load_data()
    keyboard = []
    row = []
    
    for i, exercise in enumerate(data['exercises']):
        callback_data = f"toggle_{i}"
        button = InlineKeyboardButton(
            f"⬜ {exercise['name']}",
            callback_data=callback_data
        )
        row.append(button)
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Save Selection (0 selected)", callback_data="save_selection")])
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.data.startswith('toggle_'):
        try:
            message = query.message
            old_keyboard = message.reply_markup.inline_keyboard
            new_keyboard = []
            selected_count = 0
            
            # Create new keyboard with new buttons
            for row in old_keyboard[:-1]:  # Exclude save button
                new_row = []
                for button in row:
                    if button.callback_data == query.data:
                        # Create new button with toggled state
                        current_text = button.text
                        new_text = current_text.replace('⬜', '✅') if '⬜' in current_text else current_text.replace('✅', '⬜')
                        new_button = InlineKeyboardButton(text=new_text, callback_data=button.callback_data)
                    else:
                        # Keep existing button
                        new_button = InlineKeyboardButton(text=button.text, callback_data=button.callback_data)
                    
                    if '✅' in new_button.text:
                        selected_count += 1
                    
                    new_row.append(new_button)
                new_keyboard.append(new_row)
            
            # Add save button
            new_keyboard.append([InlineKeyboardButton(
                text=f"Save Selection ({selected_count} selected)", 
                callback_data="save_selection"
            )])
            
            # Create new markup with new keyboard
            new_markup = InlineKeyboardMarkup(new_keyboard)
            
            # Update message with new markup
            await message.edit_text(
                text="Select exercises to keep unchanged:",
                reply_markup=new_markup
            )
            
            await query.answer(text="Selection updated!")
            
        except Exception as e:
            logging.error(f"Error in toggle handler: {str(e)}")
            await query.answer(text="Error updating selection")
    
    elif query.data == 'update_all':
        data = load_data()
        for exercise in data['exercises']:
            # Before updating the exercise, store old values
            old_weight = exercise['weight']
            old_reps = exercise['reps']
            
            # Calculate new values
            result = calculate_next_workout(
                exercise['name'],
                exercise['weight'],
                exercise['reps'],
                exercise['sets'],
                exercise['increment']
            )
            _, weight, reps, _ = result
            
            # Update the exercise
            exercise['weight'] = weight
            exercise['reps'] = reps
            
            # Log the progression
            log_progression(
                exercise['name'],
                old_weight,
                weight,
                old_reps,
                reps,
                "auto_update"
            )
        
        data['last_update'] = datetime.now().isoformat()
        save_data(data)
        await query.edit_message_text("All exercises updated for next week!")
        await next_workout(update, context)
    
    elif query.data == 'select_exercises':
        keyboard = await create_exercise_checklist()
        await query.edit_message_text(
            "Select exercises to keep unchanged:",
            reply_markup=keyboard
        )
    
    elif query.data == 'save_selection':
        keyboard = query.message.reply_markup.inline_keyboard
        data = load_data()
        selected_indices = []
        selected_exercises = []
        
        # Find selected exercises
        for row in keyboard:
            for button in row:
                if button.callback_data.startswith('toggle_') and '✅' in button.text:
                    index = int(button.callback_data.split('_')[1])
                    selected_indices.append(index)
                    selected_exercises.append(data['exercises'][index]['name'])
        
        # Update non-selected exercises
        for i, exercise in enumerate(data['exercises']):
            if i not in selected_indices:
                result = calculate_next_workout(
                    exercise['name'],
                    exercise['weight'],
                    exercise['reps'],
                    exercise['sets'],
                    exercise['increment']
                )
                _, weight, reps, _ = result
                exercise['weight'] = weight
                exercise['reps'] = reps
        
        data['last_update'] = datetime.now().isoformat()
        save_data(data)
        
        # Create feedback message with kept exercises
        if selected_exercises:
            kept_exercises = "\n• " + "\n• ".join(selected_exercises)
            message = f"Exercises updated! The following exercises were kept unchanged:{kept_exercises}"
        else:
            message = "All exercises were updated!"
            
        await query.edit_message_text(message)
        await next_workout(update, context)

async def plan_next_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = await create_exercise_checklist()
    await update.message.reply_text(
        "Select exercises to keep unchanged for next week:",
        reply_markup=keyboard
    )

async def reset_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Define the initial exercises
        initial_data = {
            "exercises": [
                {
                    "name": "Overhead Press",
                    "weight": 35,
                    "reps": 11,
                    "sets": 3,
                    "increment": 5
                },
                {
                    "name": "Bench Press",
                    "weight": 16.25,
                    "reps": 10,
                    "sets": 3,
                    "increment": 1.25
                },
                {
                    "name": "Chest Row",
                    "weight": 25,
                    "reps": 11,
                    "sets": 3,
                    "increment": 1.25
                },
                {
                    "name": "Leg Press",
                    "weight": 50,
                    "reps": 12,
                    "sets": 2,
                    "increment": 1.25
                },
                {
                    "name": "Leg Curl",
                    "weight": 30,
                    "reps": 12,
                    "sets": 2,
                    "increment": 10
                },
                {
                    "name": "Dumbbell Curl",
                    "weight": 12.5,
                    "reps": 11,
                    "sets": 2,
                    "increment": 2.5
                },
                {
                    "name": "Overhead Cable",
                    "weight": 30,
                    "reps": 10,
                    "sets": 2,
                    "increment": 5
                },
                {
                    "name": "Pulldowns",
                    "weight": 50,
                    "reps": 8,
                    "sets": 2,
                    "increment": 10
                },
                {
                    "name": "Cable Crunch",
                    "weight": 50,
                    "reps": 12,
                    "sets": 2,
                    "increment": 10
                }
            ],
            "last_update": None
        }
        
        save_data(initial_data)
        await update.message.reply_text("Exercise data has been reset to initial values!")
        # Show the current workout after reset
        await current_workout(update, context)
    except Exception as e:
        await update.message.reply_text(f"Error resetting exercises: {str(e)}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Update command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("current", current_workout))
    application.add_handler(CommandHandler("plan_next", plan_next_week))  # Renamed command
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.run_polling()

if __name__ == '__main__':
    main()
