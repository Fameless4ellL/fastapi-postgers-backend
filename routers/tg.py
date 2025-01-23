import json
from fastapi import Request
from fastapi.responses import JSONResponse
from aiogram import types, filters, F
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import Role, User
from routers import public, dp, bot
from utils.signature import decrypt_credential_secret, decrypt_data
from settings import settings


@public.post("/telegram", include_in_schema=False)
async def telegram_handler(request: Request):
    """
    Handler for telegram bot - webhook
    """
    body = await request.body()
    if body:
        update = types.Update.model_validate(
            obj=await request.json(), context={"bot": bot}
        )
        await dp.feed_update(bot, update)
    return JSONResponse(status_code=200, content={"message": "OK"})


@dp.message(filters.Command("start"))
async def start_handler(message: types.Message, db: AsyncSession):
    """
    /start
    """
    # Check if the user exists
    result = await db.execute(
        select(User).filter(User.telegram_id == message.from_user.id)
    )
    user = result.scalars().first()

    if not user:
        # Create a new user if not exists

        kwargs = {}
        if message.from_user.username in settings.admins:
            kwargs['role'] = Role.ADMIN.value

        new_user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            language_code=message.from_user.language_code,
            **kwargs
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user = new_user

    await message.reply(
        f"Hello, {user.username}!\n"
        "Please provide your passport details.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(
                text="Auth",
                web_app=types.WebAppInfo(url=settings.web_app_url),
            )]],
            resize_keyboard=True,
        ),
    )


@dp.message(filters.Command("deposit"))
@dp.message(F.text == "Deposit")
async def deposit(message: types.Message):
    return await message.answer("Under construction")


@dp.message(filters.Command("withdraw"))
@dp.message(F.text == "Withdraw")
async def withdraw(message: types.Message):
    return await message.answer("Under construction")


@dp.message(F.passport_data)
async def empty(message: types.Message, db: AsyncSession):
    # Drop table
    if message.passport_data:
        credentials = message.passport_data.credentials
        credentials_secret, err = decrypt_credential_secret(credentials.secret)
        if err:
            return await message.reply("Something went wrong")
        credentials = json.loads(decrypt_data(
            credentials.data,
            credentials_secret,
            credentials.hash
        ))

        # Verify the nonce
        if credentials['nonce'] != "thisisatest":
            return await message.reply("Invalid nonce")

        user = await db.execute(
            select(User).filter(
                User.telegram_id == message.from_user.id)
            .with_for_update()
        )
        user = user.scalars().first()
        if user is None:
            return await message.reply("User not found")

        for element in message.passport_data.data:
            if element.type == "email":
                email = element.email
                user.email = email
            if element.type == "phone_number":
                user.phone_number = element.phone_number

        await db.commit()
        await db.refresh(user)

        # Process the secure data
        # secure_data = credentials['secure_data']
        # print(secure_data)

        return await message.answer(
            "Passport data received and processed",
            reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[[
                    types.KeyboardButton(text='Deposit'),
                    types.KeyboardButton(text='Withdraw')
                ]],
                resize_keyboard=True
            )
        )
    else:
        return await message.reply("I don't understand you.")
