# -*- coding: utf-8 -*-
import os
import discord
from discord.ext import commands
import asyncio
import traceback   # ← 이 줄 추가
from dotenv import load_dotenv

load_dotenv()

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = False

bot = commands.Bot(command_prefix="!", intents=INTENTS, help_command=None)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Loaded commands:", [c.name for c in bot.commands])  # ← 등록된 명령 확인
    await bot.change_presence(activity=discord.Game(name="!도움말"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return await ctx.send("이미 **다른 채널**에서 경매가 진행 중입니다. 같은 채널에서 사용해 주세요.")
    if isinstance(error, commands.CommandNotFound):
        return await ctx.send("알 수 없는 명령어입니다. `!도움말`을 입력해 보세요.")
    await ctx.send(f"에러: {error.__class__.__name__}: {error}")

async def main():
    try:
        await bot.load_extension("commands.auction")
        print("[OK] Loaded extension: commands.auction")
    except Exception as e:
        print("[ERR] Failed to load extension: commands.auction")
        traceback.print_exc()  # ← 실패 원인 콘솔에 출력

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN 이 설정되지 않았습니다. .env 또는 환경변수로 지정하세요.")
    await bot.start(token)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
