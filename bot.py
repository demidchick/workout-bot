import logging
from datetime import datetime
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, JobQueue
import pytz
from config import TOKEN, CHAT_ID, TIMEZONE

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"exercises": [], "last_update": None}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)

def format_workout_message(exercises, title):
    message = f"*{title}*\n\n"
    message += "`Exercise               Weight  Reps`\n"
    message += "`────────────────────────────────`\n"
    
    for exercise in exercises:
        message += f"`{exercise['name']:<20} {exercise['weight']:>5.1f}kg {exercise['reps']:>2d}`\n"
    
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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'update_all':
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
    
    elif query.data == 'select_exercises':
        # Add exercise selection logic here
        await query.edit_message_text("Feature coming soon!")

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("current", current_workout))
    application.add_handler(CommandHandler("next", next_workout))
    
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
    
    application.run_polling()

if __name__ == '__main__':
    main()
