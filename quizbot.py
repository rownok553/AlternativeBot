import os
import logging
from typing import Dict, List, Tuple, Optional
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    Poll, 
    InputMediaPhoto,
    BotCommand
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, 
    CallbackContext, CallbackQueryHandler, ConversationHandler,
    CommandHandler, Dispatcher
)
from PIL import Image
import pytesseract
import re
import threading
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot states
(
    MAIN_MENU, OCR_SCAN, MANUAL_INPUT, EDIT_QUESTION, 
    EDIT_OPTIONS, SELECT_ANSWER, QUIZ_ACTION, 
    USER_MANAGEMENT, QUIZ_LIST
) = range(9)

# Database to store questions and users
question_database = {}
user_sessions = {}
approved_users = set()  # In production, use persistent storage
ADMIN_USER_ID = "YOUR_TELEGRAM_USER_ID"  # Change this!
ADMIN_PASSCODE = "your_secure_passcode"  # Change this!

def setup_commands(dispatcher: Dispatcher):
    """Setup bot commands for the menu"""
    commands = [
        BotCommand('start', 'Start the bot'),
        BotCommand('newquiz', 'Create a new quiz'),
        BotCommand('quizzes', 'List all quizzes'),
        BotCommand('users', 'Manage users (admin only)')
    ]
    dispatcher.bot.set_my_commands(commands)

def start(update: Update, context: CallbackContext) -> int:
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    
    if user_id in approved_users:
        show_main_menu(update, context)
        return MAIN_MENU
    else:
        update.message.reply_text(
            "Please enter the passcode to use this bot:"
        )
        return USER_MANAGEMENT

def show_main_menu(update: Update, context: CallbackContext, message: str = "Main Menu:") -> None:
    """Show the main menu with inline buttons"""
    keyboard = [
        [InlineKeyboardButton("📝 New Quiz", callback_data='new_quiz')],
        [InlineKeyboardButton("📚 My Quizzes", callback_data='list_quizzes')],
    ]
    
    if update.effective_user.id == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("👥 Users", callback_data='manage_users')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        update.callback_query.edit_message_text(
            text=message,
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            text=message,
            reply_markup=reply_markup
        )

def new_quiz_menu(update: Update, context: CallbackContext) -> int:
    """Show new quiz creation options"""
    query = update.callback_query
    query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📸 Scan from Image (OCR)", callback_data='ocr_scan')],
        [InlineKeyboardButton("✍️ Manual Input", callback_data='manual_input')],
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text="How would you like to create a new quiz?",
        reply_markup=reply_markup
    )
    return MAIN_MENU

def start_ocr_scan(update: Update, context: CallbackContext) -> int:
    """Start the OCR scanning process"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        text="Please send me an image of the quiz question:"
    )
    return OCR_SCAN

def start_manual_input(update: Update, context: CallbackContext) -> int:
    """Start manual quiz creation"""
    query = update.callback_query
    query.answer()
    
    query.edit_message_text(
        text="Please send me the quiz question text. "
             "You can send text or a photo with caption:"
    )
    return MANUAL_INPUT

def list_quizzes(update: Update, context: CallbackContext) -> int:
    """List all available quizzes"""
    query = update.callback_query
    query.answer()
    
    if not question_database:
        query.edit_message_text("No quizzes available yet.")
        return MAIN_MENU
    
    keyboard = []
    for quiz_id, quiz_data in question_database.items():
        keyboard.append(
            [InlineKeyboardButton(
                f"📝 {quiz_data['question'][:30]}...", 
                callback_data=f'quiz_{quiz_id}'
            )]
        )
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text="Available Quizzes:",
        reply_markup=reply_markup
    )
    return QUIZ_LIST

def quiz_action_menu(update: Update, context: CallbackContext) -> int:
    """Show actions for a specific quiz"""
    query = update.callback_query
    query.answer()
    
    quiz_id = query.data.split('_')[1]
    quiz_data = question_database.get(quiz_id)
    
    if not quiz_data:
        query.edit_message_text("Quiz not found.")
        return MAIN_MENU
    
    keyboard = [
        [InlineKeyboardButton("▶️ Start Quiz", callback_data=f'start_{quiz_id}')],
        [InlineKeyboardButton("✏️ Edit Quiz", callback_data=f'edit_{quiz_id}')],
        [InlineKeyboardButton("🗑️ Delete Quiz", callback_data=f'delete_{quiz_id}')],
        [InlineKeyboardButton("🔙 Back", callback_data='list_quizzes')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text=f"Quiz: {quiz_data['question']}\n\nSelect an action:",
        reply_markup=reply_markup
    )
    return QUIZ_ACTION

def manage_users(update: Update, context: CallbackContext) -> int:
    """Show user management options (admin only)"""
    query = update.callback_query
    query.answer()
    
    if update.effective_user.id != ADMIN_USER_ID:
        query.edit_message_text("You don't have permission for this action.")
        return MAIN_MENU
    
    keyboard = []
    for user_id in approved_users:
        keyboard.append(
            [InlineKeyboardButton(
                f"👤 User {user_id}", 
                callback_data=f'user_{user_id}'
            )]
        )
    
    keyboard.append([InlineKeyboardButton("➕ Add User", callback_data='add_user')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        text="User Management:",
        reply_markup=reply_markup
    )
    return USER_MANAGEMENT

# [Previous functions like scan_image, parse_quiz_text, etc. would go here]
# [Add similar modifications to all other functions to use the new menu system]

def keep_alive():
    """Function to keep the bot alive 24/7"""
    while True:
        logger.info("Bot is alive and running...")
        time.sleep(300)  # Log every 5 minutes

def main():
    """Start the bot."""
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise ValueError("Please set the TELEGRAM_TOKEN environment variable")
    
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher
    
    # Setup commands menu
    setup_commands(dp)
    
    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(new_quiz_menu, pattern='^new_quiz$'),
                CallbackQueryHandler(list_quizzes, pattern='^list_quizzes$'),
                CallbackQueryHandler(manage_users, pattern='^manage_users$'),
                CallbackQueryHandler(show_main_menu, pattern='^main_menu$')
            ],
            OCR_SCAN: [MessageHandler(Filters.photo, scan_image)],
            MANUAL_INPUT: [MessageHandler(Filters.text | Filters.photo, manual_input_handler)],
            # [Add other states and handlers here]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    dp.add_handler(conv_handler)
    dp.add_error_handler(error)
    
    # Start the keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Start the Bot
    updater.start_polling()
    
    # For 24/7 operation on a server, consider using:
    # updater.start_webhook(listen="0.0.0.0", port=os.getenv('PORT', 5000))
    
    updater.idle()

if __name__ == '__main__':
    main()
