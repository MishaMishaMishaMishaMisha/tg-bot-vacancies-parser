import asyncio

from src.tg_bot_interface.run import run_bot


if __name__ == "__main__":
    print("<main-file>")
    
    try:
        asyncio.run(run_bot())
        
    except KeyboardInterrupt:
        print("exit")
        
        
# launch command
# watchfiles "uv run python -m src.main"