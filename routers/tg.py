import json
from fastapi import Request
from fastapi.responses import JSONResponse
from aiogram import types, filters
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from routers import router, dp, bot
from utils.signature import decrypt_credential_secret, decrypt_data


@router.post("/telegram")
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
    print(message.passport_data)
    # Check if the user exists
    result = await db.execute(
        select(User).filter(User.telegram_id == message.from_user.id)
    )
    user = result.scalars().first()

    if not user:
        # Create a new user if not exists
        new_user = User(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user = new_user
    await message.reply(
        f"Hello, {user.first_name} {user.last_name}!\n"
        "Please provide your passport details.",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(
                text="Auth",
                web_app=types.WebAppInfo(
                    url="https://webhook.site/4f4f47fa-a71b-476d-ba89-298d23ba45ad"
                ),
            )]],
            resize_keyboard=True,
        ),
    )


@dp.message()
async def empty(message: types.Message, db: AsyncSession):
    if message.passport_data:
        credentials = message.passport_data.credentials
        credentials_secret = decrypt_credential_secret(credentials.secret)
        credentials = json.loads(decrypt_data(
            credentials.data,
            credentials_secret,
            credentials.hash
        ))

        # Verify the nonce
        if credentials['nonce'] != "thisisatest":
            return await message.reply("Invalid nonce")

        for element in message.passport_data.data:
            if element.type == "email":
                async with db.begin():
                    user = await db.execute(
                        select(User).filter(User.telegram_id == message.from_user.id)
                    )
                    user = user.scalars().first()
                    user.email = element.email
                    await db.commit()
                    await db.refresh(user)
                    return await message.reply("Email received and saved")

        # Process the secure data
        # secure_data = credentials['secure_data']
        # print(secure_data)

        return await message.reply("Passport data received and processed")
    else:
        return await message.reply("I don't understand you.")
