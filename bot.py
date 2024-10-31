import logging
from datetime import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, JobQueue
import pytz
from config import TOKEN, CHAT_ID, TIMEZONE
from workout_calculator import calculate_next_workout

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

def format_workout_message(exercises, title):
    message = f"*{title}*\n\n"
    message += "`Exercise         Weight  Reps`\n"
    message += "`───────────────────────────`\n"
    
    for exercise in exercises:
        message += f"`{exercise['name']:<15} {exercise['weight']:>5.1f}kg {exercise['reps']:>2d}`\n"
    
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your workout progression bot.\n"
        "Use /current to see current weights\n"
        "Use /next to see next workout targets"
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
        name, weight, reps, _ = result
        next_exercises.append({
            'name': name,
            'weight': weight,
            'reps': reps,
            'sets': exercise['sets']
        })
    
    message = format_workout_message(next_exercises, "Next workout targets:")
    await update.message.reply_text(message, parse_mode='MarkdownV2')

async def friday_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data='update_all'),
            InlineKeyboardButton("Select exercises", callback_data='select_exercises')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=context.job.data,
        text="Would you like to update all exercises for next week?",
        reply_markup=reply_markup
    )

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

async def select_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = await create_exercise_checklist()
    await update.message.reply_text(
        "Select exercises to keep unchanged:",
        reply_markup=keyboard
    )

async def reset_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    save_data(initial_data)
    await update.message.reply_text("Exercise data has been reset to initial values!")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("current", current_workout))
    application.add_handler(CommandHandler("next", next_workout))
    
    # Add new command handler
    application.add_handler(CommandHandler("select", select_exercises))
    
    # Callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Schedule Friday reminder
    job_queue = application.job_queue
    
    # Schedule for every Friday at 5 PM (17:00)
    target_time = datetime.now(pytz.timezone(TIMEZONE)).replace(
        hour=17, minute=0, second=0, microsecond=0
    )
    
    job_queue.run_daily(
        friday_reminder,
        days=(4,),  # 4 is Friday (Monday is 0)
        time=target_time.time(),
        data=CHAT_ID  # You'll need to add your chat ID here
    )
    
    application.add_handler(CommandHandler("reset", reset_exercises))
    
    application.run_polling()

if __name__ == '__main__':
    main()
