import logging
from datetime import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from config import TOKEN
from workout_calculator import calculate_next_workout
from progression_tracker import log_progression, init_db, get_db_connection

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
        "exercises": exercises
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
    message = "WORKOUT TARGETS\n\n"
    
    # Calculate max length for exercise names for proper alignment
    max_name_length = max(len(exercise['name']) for exercise in exercises)
    
    for exercise in exercises:
        # Format: bullet, space, padded name, space, colon, space, weight, space, ×, space, reps
        message += (
            f"• {exercise['name']:<{max_name_length}} : "
            f"{exercise['weight']:>5.2f} × {exercise['reps']:>2d}\n"
        )
    
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

async def next_workout(update: Update, context: ContextTypes.DEFAULT_TYPE, keep_unchanged=None, save_to_db=True):
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
    
    # Only save to database if explicitly requested
    if save_to_db:
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
        
        # Create feedback message with kept exercises
        if selected_exercises:
            kept_exercises = "\n• " + "\n• ".join(selected_exercises)
            message = f"Exercises updated! The following exercises were kept unchanged:{kept_exercises}"
        else:
            message = "All exercises were updated!"
            
        await query.edit_message_text(message)
        # Changed save_to_db to True to ensure updates are saved
        await next_workout(update, context, keep_unchanged=selected_exercises, save_to_db=True)

async def plan_next_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = await create_exercise_checklist()
    await update.message.reply_text(
        "Select exercises to keep unchanged for next week:",
        reply_markup=keyboard
    )

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
    
    application.run_polling()

if __name__ == '__main__':
    main()