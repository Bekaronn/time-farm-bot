import asyncio
import hmac
import hashlib
from urllib.parse import unquote, quote

import aiohttp
import json
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestWebView
from .agents import generate_random_user_agent
from bot.config import settings
from datetime import datetime, timedelta, timezone

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers


class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None

    async def get_secret(self, userid):
        key_hash = str("adwawdasfajfklasjglrejnoierjboivrevioreboidwa").encode('utf-8')
        message = str(userid).encode('utf-8')
        hmac_obj = hmac.new(key_hash, message, hashlib.sha256)
        secret = str(hmac_obj.hexdigest())
        return secret

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            while True:
                try:
                    peer = await self.tg_client.resolve_peer('timefarmcryptobot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")

                    await asyncio.sleep(fls + 3)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://tg-tap-miniapp.laborx.io/'
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(
                    string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0]))

            self.user_id = (await self.tg_client.get_me()).id
            if (await self.tg_client.get_me()).username:
                self.username = (await self.tg_client.get_me()).username
            else:
                self.username = ''

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def get_progress(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url='https://api-clicker.pixelverse.xyz/api/mining/progress') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                current_available = data.get('currentlyAvailable')
                min_amount_for_claim = data.get('minAmountForClaim')
                next_full = data.get('nextFullRestorationDate')
                if current_available and min_amount_for_claim and next_full:
                    return (current_available,
                            min_amount_for_claim,
                            next_full)
                return None, None, None
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return None, None, None

    async def get_stats(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url='https://api-clicker.pixelverse.xyz/api/users') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                points = data.get('clicksCount')
                if points:
                    return points
                return None
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return None

    async def claim_mining(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.post(url='https://api-clicker.pixelverse.xyz/api/mining/claim') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                claimed_amount = data.get('claimedAmount')
                if claimed_amount:
                    return claimed_amount
                else:
                    return None
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return None

    async def get_all_pet_ids(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url='https://api-clicker.pixelverse.xyz/api/pets') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                pet_ids = [pet['userPet']['id'] for pet in data.get('data', [])]
                return pet_ids
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return []

    async def get_cost(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url='https://api-clicker.pixelverse.xyz/api/pets') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                return data.get('buyPrice')
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return None

    async def buy_pet(self, http_client: aiohttp.ClientSession):
        async with http_client.post(url=f'https://api-clicker.pixelverse.xyz/api/pets/buy?'
                                        f'tg-id={self.user_id}&secret=adwawdasfajfklasjglrejnoierjb'
                                        f'oivrevioreboidwa', json={}) as response:
            response_text = await response.text()
            data = json.loads(response_text)
            if data.get('pet'):
                return data.get('pet').get('name')
            elif data.get('message'):
                return data.get('message')
            else:
                return None

    async def get_pet_info(self, http_client: aiohttp.ClientSession, pet_id: str):
        async with http_client.get(url=f'https://api-clicker.pixelverse.xyz/api/pets') as response:
            response_text = await response.text()
            data = json.loads(response_text)
            for pet in data.get('data', []):
                if pet.get('userPet', {}).get('id') == pet_id:
                    return {
                        'name': pet.get('name'),
                        'levelUpPrice': pet.get('userPet', {}).get('levelUpPrice')
                    }
            return None
    
    async def level_up_pet(self, http_client: aiohttp.ClientSession, pet_id):
        try:
            async with http_client.post(url=f'https://api-clicker.pixelverse.xyz/api/pets/'
                                            f'user-pets/{pet_id}/level-up') as response:
                response_text = await response.text()
                data = json.loads(response_text)
                level = data.get('level')
                cost = data.get('levelUpPrice')
                if level and cost:
                    return (level,
                            cost)
                else:
                    return None, None
        except Exception as error:
            logger.error(f"Error happened: {error}")
            return None, None

    async def get_tasks(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url="https://api-clicker.pixelverse.xyz/api/tasks/my") as response:
                if response.status == 201 or response.status == 200:
                    return True
        except Exception:
            return False

    async def get_users(self, http_client: aiohttp.ClientSession):
        try:
            async with http_client.get(url="https://api-clicker.pixelverse.xyz/api/users") as response:
                if response.status == 201 or response.status == 200:
                    return True
        except Exception:
            return False

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")

        # async def daily_combo(self, http_client: aiohttp.ClientSession, id_pets):
        # url_current_game = "https://api-clicker.pixelverse.xyz/api/cypher-games/current"
        # try:
        #     async with http_client.get(url=f'{url_current_game}') as response:
        #         response_text = await response.text()
        #         data = json.loads(response_text)
        #         status_code = response.status
        #         if status_code == 200 and response.text:
        #             if data['status'] == "ACTIVE":
        #                 game_id = data.get('id')
        #                 url_answer = f"https://api-clicker.pixelverse.xyz/api/cypher-games/{game_id}/answer"
        #                 available_options = data.get('options', [])
        #                 pet_id_index_map = {option["optionId"]: len(available_options) - option["order"] - 1 for option in available_options}

        #                 id_pets = [pet_id.strip() for pet_id in id_pets]
        #                 payload = {pet_id: len(id_pets) - id_pets.index(pet_id) - 1 for pet_id in id_pets}
        #                 url_answer = f"https://api-clicker.pixelverse.xyz/api/cypher-games/{game_id}/answer"

        #                 async with http_client.post(url=f'{url_answer}', json=payload) as res_answer:
        #                         if res_answer.status == 200 or res_answer.status == 201:
        #                             try:
        #                                 answer_data = await res_answer.json()
        #                                 reward_amount = answer_data.get('rewardAmount', 'N/A')
        #                                 return(f'Successfully submitted the daily combo! Reward Amount: <green>{reward_amount}</green>')
        #                             except json.JSONDecodeError:
        #                                 return (f'Failed to decode JSON response from answer API.')
        #                         else:
        #                             return f'Failed to submit the daily combo. {res_answer.text}'
        #             else:
        #                 return 'Already claimed!'
        #         return 'already claimed!'
        # except Exception as error:
        #     return f"Error happened: {error}"


    async def get_access_token_and_info(self, http_client: aiohttp.ClientSession, query_data):
        url = 'https://tg-bot-tap.laborx.io/api/v1/auth/validate-init'
        try:
            async with http_client.post(url=f"{url}", data=query_data) as response:
                data = await response.json()
                response.raise_for_status()
                return data
        except Exception as e:
            print(f"279 | Request Error: {e}")
            return None
        
    async def finish_farming(self, http_client: aiohttp.ClientSession, token):
        url = 'https://tg-bot-tap.laborx.io/api/v1/farming/finish'
        http_client.headers["Authorization"] = f"Bearer {token}"
        try:
            async with http_client.post(url=f"{url}") as response:
                data = await response.json()
                return data
        except Exception as e:
            print(f"290 | Request Error: {e}")
            return None
        
    async def check_farming(self, http_client: aiohttp.ClientSession, token):
        url = 'https://tg-bot-tap.laborx.io/api/v1/farming/info'
        http_client.headers["Authorization"] = f"Bearer {token}"
        try:
            async with http_client.post(url=f"{url}") as response:
                data = await response.json()
                return data
        except Exception as e:
            print(f"301 | Request Error: {e}")
            return None
        
    async def start_farming(self, http_client: aiohttp.ClientSession, token):
        url = 'https://tg-bot-tap.laborx.io/api/v1/farming/start'
        http_client.headers["Authorization"] = f"Bearer {token}"
        try:
            async with http_client.post(url=f"{url}") as response:
                data = await response.json()
                return data
        except Exception as e:
            print(f"301 | Request Error: {e}")
            return None
        
# Auto Claim Task (Some time error from timefarm server)
# Auto Claim Farming
# Auto Start Farming
# Auto Handle Error
# Auto Get Token / Refresh Token
# Multi Account

    async def run(self, proxy: str | None) -> None:
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        tg_web_data = await self.get_tg_web_data(proxy=proxy)
        (http_client.headers
                    ["User-Agent"]) = generate_random_user_agent(device_type='android', browser_type='chrome')

        while True:
            try:
                tg_web_data_parts = tg_web_data.split('&')
                query_id = tg_web_data_parts[0].split('=')[1]
                user_data = tg_web_data_parts[1].split('=')[1]
                auth_date = tg_web_data_parts[2].split('=')[1]
                hash_value = tg_web_data_parts[3].split('=')[1]

                # Кодируем user_data
                user_data_encoded = quote(user_data)

                # Формируем init_data
                init_data = f"query_id={query_id}&user={user_data_encoded}&auth_date={auth_date}&hash={hash_value}"

                
                auth_response = await self.get_access_token_and_info(http_client=http_client, query_data = init_data)

                if auth_response is not None:
                    token = auth_response['token']

                    balance_info = auth_response['balanceInfo']
                    username = balance_info.get('user', {}).get('userInfo', {}).get('userName', "Tidak Ada Username")
                    firstname = balance_info.get('user', {}).get('userInfo', {}).get('firstName', "Tidak Ada Firstname")
                    lastname = balance_info.get('user', {}).get('userInfo', {}).get('lastName', "Tidak Ada Lastname")
                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"Balance is : <green>{int(balance_info['balance'])}</green>")

                farming_response = await self.finish_farming(http_client=http_client, token=token)

                if farming_response is not None:
                    if 'error' in farming_response:
                        if farming_response['error']['message'] == "Too early to finish farming":
                            check_farming_response = await self.check_farming(http_client=http_client, token=token)
                            if check_farming_response:
                                started_at = datetime.fromisoformat(check_farming_response['activeFarmingStartedAt'].replace('Z', '+00:00')).astimezone(timezone.utc)
                                duration_sec = check_farming_response['farmingDurationInSec']
                                end_time = started_at + timedelta(seconds=duration_sec)
                                time_now = datetime.now(timezone.utc)

                                remaining_time = end_time - time_now
                                if remaining_time.total_seconds() > 0:
                                    hours, remainder = divmod(remaining_time.total_seconds(), 3600)
                                    minutes, _ = divmod(remainder, 60)
                                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"Claim farming in {int(hours)} hours {int(minutes)} minutes")
                                else:
                                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"<green>Farming can be claimed now</green>")
                        elif farming_response['error']['message'] == "Farming didn't start":
                            await asyncio.sleep(2)
                            start_farming_response = await self.start_farming(http_client=http_client, token=token)
                            if start_farming_response is not None:
                                logger.success(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"<green>Farming started</green>")
                            else:
                                if 'error' in start_farming_response:
                                    if start_farming_response['error']['message'] == "Farming already started":
                                        logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"Farming already started")
                                else:
                                    logger.warning(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"<red>Failed to Start Farming</red>")
                        else:
                            logger.warning(f"[ Farming ] : {farming_response['error']['message']}")
                    else:
                        logger.success(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f" Claimed | Balance: "
                                       f"<green>{int(farming_response['balance']):,}</green>".replace(',', '.'))
                        await asyncio.sleep(2)
                        check_farming_response = await self.check_farming(http_client=http_client, token=token)
                        if check_farming_response is not None:
                                if check_farming_response['activeFarmingStartedAt'] is None:
                                    await asyncio.sleep(2)
                                    start_farming_response = await self.start_farming(http_client=http_client, token=token)
                                    if start_farming_response is not None:
                                        logger.success(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"<green>Farming started</green>")
                                    else:
                                        if 'error' in start_farming_response:
                                            if start_farming_response['error']['message'] == "Farming already started":
                                                logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                                f"Farming already started")
                                        else:
                                            logger.warning(f"<light-yellow>{self.session_name}</light-yellow> | "
                                       f"<red>Failed to Start Farming</red>")
                                else:
                                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | "
                                                f"Farming already started")                         
                else:
                    logger.warning("ERROR farming response")
                    continue

                logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Going sleep 1 hour")

                await asyncio.sleep(3600)

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
