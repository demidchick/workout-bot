import logging
from datetime import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from config import TOKEN
from workout_calculator import calculate_next_workout
from progression_tracker import log_progression, init_db, get_progression_history, get_db_connection

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_data():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('SELECT name, weight, reps, sets, increment FROM exercises ORDER BY id')
    exercises = [
        {
            "name": row[0],
            "weight": row[1],
            "reps": row[2],
            "sets": row[3],
            "increment": row[4]
        }
        for row in cur.fetchall()
    ]
    
    cur.close()
    conn.close()
    
    return {
        "exercises": exercises,
        "last_update": datetime.now().isoformat()
    }

def save_data(data):
    conn = get_db_connection()
    cur = conn.cursor()
    
    for exercise in data['exercises']:
        cur.execute('''
            UPDATE exercises 
            SET weight = %s, reps = %s, last_update = NOW()
            WHERE name = %s
        ''', (exercise['weight'], exercise['reps'], exercise['name']))
    
    conn.commit()
    cur.close()
    conn.close()

def format_workout_message(exercises, title, show_volume_change=False):
    message = f"*{title}*\n\n"
    if show_volume_change:
        message += "`Exercise        Weight Reps  %`\n"
        message += "`───────────────────────────────`\n"
        
        for exercise in exercises:
            volume_change = exercise.get('volume_change', 0)
            message += f"`{exercise['name']:<14} {exercise['weight']:>5.1f} {exercise['reps']:>3d} {volume_change:>+3.0f}`\n"
    else:
        message += "`Exercise        Weight Reps`\n"
        message += "`────────────────────────────`\n"
        
        for exercise in exercises:
            message += f"`{exercise['name']:<14} {exercise['weight']:>5.1f} {exercise['reps']:>3d}`\n"
    
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

async def next_workout(update: Update, context: ContextTypes.DEFAULT_TYPE, keep_unchanged=None):
    if keep_unchanged is None:
        keep_unchanged = []
    
    data = load_data()
    next_exercises = []
    
    for exercise in data['exercises']:
        if exercise['name'] in keep_unchanged:
            # Keep exercise unchanged
            next_exercises.append({
                'name': exercise['name'],
                'weight': exercise['weight'],
                'reps': exercise['reps'],
                'sets': exercise['sets'],
                'volume_change': 0
            })
            continue
            
        # Store old values for logging
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
        name, weight, reps, volume_change = result
        
        # Update exercise with new values
        exercise['weight'] = weight
        exercise['reps'] = reps
        
        # Log the progression
        log_progression(
            exercise['name'],
            old_weight,
            weight,
            old_reps,
            reps
        )
        
        next_exercises.append({
            'name': name,
            'weight': weight,
            'reps': reps,
            'sets': exercise['sets'],
            'volume_change': volume_change
        })
    
    # Save the updated values to database
    save_data(data)
    
    message = format_workout_message(next_exercises, "Next workout targets:", show_volume_change=True)
    
    # Handle both message and callback query updates
    if update.message:
        await update.message.reply_text(message, parse_mode='MarkdownV2')
    elif update.callback_query:
        await update.callback_query.message.reply_text(message, parse_mode='MarkdownV2')

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
            # Store old values
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
            
            # Remove this logging call
            # log_progression(
            #     exercise['name'],
            #     old_weight,
            #     weight,
            #     old_reps,
            #     reps
            # )
        
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
                # Store old values before updating
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
                    reps
                )
        
        data['last_update'] = datetime.now().isoformat()
        save_data(data)
        
        # Create feedback message with kept exercises
        if selected_exercises:
            kept_exercises = "\n• " + "\n• ".join(selected_exercises)
            message = f"Exercises updated! The following exercises were kept unchanged:{kept_exercises}"
        else:
            message = "All exercises were updated!"
            
        await query.edit_message_text(message)
        await next_workout(update, context, keep_unchanged=selected_exercises)

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

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = get_progression_history()
        if not rows:
            await update.message.reply_text("No progression history found yet.")
            return
            
        message = "*Recent Exercise Updates:*\n\n"
        for row in rows[:10]:  # Show last 10 updates
            timestamp, exercise = row[1], row[2]
            old_weight, new_weight = row[3], row[4]
            old_reps, new_reps = row[6], row[7]
            
            message += (
                f"*{exercise}*\n"
                f"Date: {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
                f"Weight: {old_weight}→{new_weight} ({row[5]:+.1f}kg)\n"
                f"Reps: {old_reps}→{new_reps} ({row[8]:+d})\n\n"
            )
        
        # Escape special characters for MarkdownV2
        message = (message
                  .replace('.', '\.')
                  .replace('-', '\-')
                  .replace('+', '\+'))
        
        await update.message.reply_text(message, parse_mode='MarkdownV2')
        
    except Exception as e:
        logging.error(f"Error in show_history: {str(e)}")
        await update.message.reply_text(f"Error showing history: {str(e)}")

def main():
    logging.info("Starting bot...")
    try:
        logging.info("Initializing database...")
        init_db()  # Initialize database tables
        logging.info("Database initialized successfully!")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")
        raise e  # This will stop the bot if database init fails
    
    application = Application.builder().token(TOKEN).build()
    
    # Update command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("current", current_workout))
    application.add_handler(CommandHandler("plan_next", plan_next_week))  # Renamed command
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("history", show_history))
    
    application.run_polling()

if __name__ == '__main__':
    main()