import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from db import SQLiteDB

# Configure logging
logging.basicConfig(level=logging.INFO)

# Bot token
API_TOKEN = config.TOKEN
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Group and channel IDs
ADMIN_GROUP_ID = config.ADMIN_CHAT_ID  # Replace with your admin group chat ID
CHANNEL_ID = config.CHANNEL_CHAT_ID  # Replace with your public channel ID

# Database instance (DI principle)
db = SQLiteDB()  # Injecting the SQLiteDB class instance


# Define FSM states for collecting lost/found item info
class FormStates(StatesGroup):
    waiting_for_item_type = State()
    waiting_for_description = State()
    waiting_for_location = State()
    waiting_for_image = State()
    waiting_for_contact = State()


# Helper to create the main menu buttons (Report Lost Item, Report Found Item)
def get_main_menu_buttons():
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Сообщить об утере", callback_data="lost"))
    buttons.add(InlineKeyboardButton(text="Сообщить о находке", callback_data="found"))
    return buttons


# Helper to create a cancel button
def get_cancel_button():
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    return buttons


# Handler for /start command
@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    # Save the user data only if they are new
    db.save_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Create the buttons for Lost and Found
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Сообщить об утере", callback_data="lost"))
    buttons.add(InlineKeyboardButton(text="Сообщить о находке", callback_data="found"))

    await message.answer(
        "Добро пожаловать в бот SDU Lost and Found! Пожалуйста, выберите один из вариантов:",
        reply_markup=buttons.as_markup()
    )


# Handler for item type (lost or found)
@dp.callback_query(lambda query: query.data in ["lost", "found"])
async def handle_item_type_choice(callback_query: types.CallbackQuery, state: FSMContext):
    item_type = callback_query.data  # either 'lost' or 'found'

    # Save the item type in the state
    await state.update_data(item_type=item_type)

    # Send a message asking for the item description, with the cancel button
    await bot.send_message(
        callback_query.from_user.id,
        "Пожалуйста, дайте краткое описание предмета.",
        reply_markup=get_cancel_button().as_markup()
    )

    # Transition to the next state in the FSM
    await state.set_state(FormStates.waiting_for_description)
    await callback_query.answer()


# Handler for item description
@dp.message(FormStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Где Вы нашли или потеряли предмет и в какое время?",
                         reply_markup=get_cancel_button().as_markup())
    await state.set_state(FormStates.waiting_for_location)


# Handler for item location
@dp.message(FormStates.waiting_for_location)
async def process_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text)

    # Ask if the user wants to upload an image
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Да", callback_data="upload_image"))
    buttons.add(InlineKeyboardButton(text="Нет", callback_data="skip_image"))
    buttons.add(InlineKeyboardButton(text="Отмена", callback_data="cancel"))  # Add cancel button here

    await message.answer("Хотите загрузить изображение предмета?", reply_markup=buttons.as_markup())
    await state.set_state(FormStates.waiting_for_image)


# Handler for image upload decision
@dp.callback_query(lambda query: query.data in ["upload_image", "skip_image"])
async def handle_image_choice(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == "upload_image":
        # Ask the user to send an image
        await bot.send_message(callback_query.from_user.id, "Пожалуйста, загрузите изображение предмета.")
        await callback_query.answer()
    else:
        # If user skips the image, proceed to contact information
        await bot.send_message(callback_query.from_user.id,
                               "Пожалуйста, предоставьте ваши контактные данные (номер телефона или электронную почту).")
        await state.set_state(FormStates.waiting_for_contact)
        await callback_query.answer()


# Handler for receiving the image
@dp.message(FormStates.waiting_for_image, F.photo)
async def process_image(message: types.Message, state: FSMContext):
    # Save the image file_id in the state
    file_id = message.photo[-1].file_id
    await state.update_data(image_url=file_id)

    # Ask for contact information
    await message.answer("Оставьте пожалуста свои контакты или куда можно обратиться.",
                         reply_markup=get_cancel_button().as_markup())
    await state.set_state(FormStates.waiting_for_contact)


# Handler for user contact information
@dp.message(FormStates.waiting_for_contact)
async def process_contact(message: types.Message, state: FSMContext):
    # Retrieve the user data from the state
    user_data = await state.get_data()

    # Save the form data in the database, including the image if provided
    application_id = db.save_application(
        user_id=message.from_user.id,
        item_type=user_data['item_type'],
        description=user_data['description'],
        location=user_data['location'],
        contact=message.text,
        image_url=user_data.get('image_url')  # If image was uploaded, it will be here; otherwise, None
    )

    # Send the application for admin confirmation
    await send_to_admin_group(application_id)

    # Send a "thank you" message with start buttons
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Сообщить об утере", callback_data="lost"))
    buttons.add(InlineKeyboardButton(text="Сообщить о находке", callback_data="found"))

    await message.answer(
        "Спасибо за Вашу заявку! Хотите отправить еще одну заявку?",
        reply_markup=buttons.as_markup()
    )

    # Clear the state after submission
    await state.clear()


# Send application to the admin group for approval
async def send_to_admin_group(application_id: int):
    # Fetch the application from the database
    item = db.get_application_by_id(application_id)

    if item:
        # Create a message with inline buttons for approve/reject
        buttons = InlineKeyboardBuilder()
        buttons.add(InlineKeyboardButton(text="Принять", callback_data=f"approve:{application_id}"))
        buttons.add(InlineKeyboardButton(text="Отклонить", callback_data=f"reject:{application_id}"))

        # Prepare the message with or without an image
        message_text = (
            f"Новая {item['item_type'].upper()} предмета:\n\n"
            f"Описание: {item['description']}\n"
            f"Локация и Время: {item['location']}\n"
            f"Контакты: {item['contact']}\n\n"
            "Примите или отклоните эту заявку:"
        )

        if item['image_url']:
            # Send image and message to the admin group
            await bot.send_photo(
                ADMIN_GROUP_ID,
                photo=item['image_url'],
                caption=message_text,
                reply_markup=buttons.as_markup()
            )
        else:
            # Send only the message to the admin group
            await bot.send_message(
                ADMIN_GROUP_ID,
                message_text,
                reply_markup=buttons.as_markup()
            )


# Handler for admin decision (approve/reject)
@dp.callback_query(lambda query: query.data.startswith(("approve", "reject")))
async def handle_admin_decision(callback_query: types.CallbackQuery):
    action, application_id = callback_query.data.split(':')
    application_id = int(application_id)

    # Retrieve the application from the database
    item = db.get_application_by_id(application_id)

    if item:
        if item['status'] in ['approved', 'rejected']:
            await callback_query.answer(f"Заявление уже {item['status']} и не может быть изменено.")
            return

        # Perform approval or rejection
        if action == "approve":
            db.update_application_status(application_id, "approved")

            # Prepare the message text with application details
            message_text = (
                f"{item['item_type'].upper()} предмет:\n\n"
                f"Описание: {item['description']}\n"
                f"Местоположение и Время: {item['location']}\n"
                f"Контакт: {item['contact']}"
            )

            # Send the approved application to the public channel
            if item['image_url']:
                await bot.send_photo(
                    CHANNEL_ID,
                    photo=item['image_url'],
                    caption=message_text
                )
            else:
                await bot.send_message(CHANNEL_ID, message_text)

            await bot.send_message(item['user_id'], "Ваше заявление было одобрено и отправлено в публичный канал!")

        elif action == "reject":
            db.update_application_status(application_id, "rejected")
            await bot.send_message(item['user_id'], "Ваше заявление было отклонено администраторами.")

        # Remove the inline buttons from the original message
        await bot.edit_message_reply_markup(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            reply_markup=None  # This removes the buttons
        )

        # Inform the admin that the action has been processed
        await callback_query.answer(f"Заявление {action}d.")
    else:
        await callback_query.answer("Заявление не найдено.")


# Handler for canceling the process
@dp.callback_query(lambda query: query.data == "cancel")
async def cancel_application(callback_query: types.CallbackQuery, state: FSMContext):
    # Clear the state to reset the user's application process
    await state.clear()

    # Send the cancel confirmation message with main menu buttons
    await bot.send_message(
        callback_query.from_user.id,
        "Заявка отменена. Если хотите, начните снова.",
        reply_markup=get_main_menu_buttons().as_markup()
    )

    # Acknowledge the cancel button press
    await callback_query.answer()



# Main function to start the bot
async def main():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
