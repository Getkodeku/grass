import asyncio
import platform
import random
import traceback
import aiohttp
import time
import sys
import os
from datetime import datetime
from core import Grass
from core.autoreger import AutoReger
from core.utils import logger
from core.utils.exception import LowProxyScoreException, ProxyScoreNotFoundException, ProxyForbiddenException
from core.utils.generate.person import Person
from data.config import ACCOUNTS_FILE_PATH, PROXIES_FILE_PATH, REGISTER_ACCOUNT_ONLY, THREADS, PROXY_URL, RESTART_INTERVAL
from core.utils.global_store import mined_grass_counts, lock


async def download_proxies():
    async with aiohttp.ClientSession() as session:
        async with session.get(PROXY_URL) as response:
            if response.status == 200:
                content = await response.text()
                with open(PROXIES_FILE_PATH, "w") as file:
                    file.write(content)
                logger.info("Downloaded proxies and saved to proxies.txt.")
            else:
                logger.error("Failed to download proxies.")

async def log_total_mined_grass_every_minute():
    while True:
        await asyncio.sleep(120)  # Wait for 1 minute
        async with lock:
            total_mined = sum(mined_grass_counts.values())
        logger.opt(colors=True).info(f"<yellow>Total Mined Grass: {total_mined}</yellow>.")

async def worker_task(_id, account: str, proxy):
    consumables = account.split(":")[:2]

    if len(consumables) == 1:
        email = consumables[0]
        password = Person().random_string(8)
    else:
        email, password = consumables

    await asyncio.sleep(random.uniform(1, 1.5) * _id)
    logger.info(f"Starting No {_id} | {email} | {password} | {proxy}")

    grass = None
    try:
        grass = Grass(_id, email, password, proxy)

        if REGISTER_ACCOUNT_ONLY:
            await grass.create_account()
        else:
            await grass.start()
    except (ProxyForbiddenException, ProxyScoreNotFoundException, LowProxyScoreException) as e:
        logger.info(f"{_id} | {e}")
    except aiohttp.ClientError as e:
        log_msg = str(e) if "</html>" not in str(e) else "Html page response, 504"
        logger.error(f"{_id} | Server not responding | Error: {log_msg}")
        await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"{_id} | not handled exception | error: {e} {traceback.format_exc()}")
    finally:
        if grass:
            await grass.session.close()

async def main():
    start_time = time.time()
    
    await download_proxies()

    autoreger = AutoReger.get_accounts(
        ACCOUNTS_FILE_PATH, PROXIES_FILE_PATH,
        with_id=True
    )

    proxies = autoreger.proxies
    account = autoreger.accounts[0]

    if REGISTER_ACCOUNT_ONLY:
        msg = "Register account only mode!"
    else:
        msg = "Mining mode ON"

    threads = len(proxies)
    logger.info(f"Threads: {threads} | {msg}")
    logger.info(f"Script will restart every {RESTART_INTERVAL//3600} hour(s)")
    
    mined_grass_task = asyncio.create_task(log_total_mined_grass_every_minute())
    
    tasks = [worker_task(i, account, proxies[i % len(proxies)]) for i in range(threads)]
    
    while True:
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        
        current_time = time.time()
        if current_time - start_time >= RESTART_INTERVAL:
            logger.info("Restarting script...")
            await cleanup()
            restart_program()

async def cleanup():
    # Cleanup code here (close connections, save state, etc)
    logger.info("Performing cleanup before restart...")
    await asyncio.sleep(1)

def restart_program():
    logger.info(f"Restarting at {datetime.now()}")
    python = sys.executable
    os.execl(python, python, *sys.argv)

if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise