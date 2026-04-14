"""
Free Fire Bot API Server - Pydantic v1 Compatible
Deploy on Vercel or Render
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import aiohttp
import ssl
import json
import random
import time
import uuid
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ============================================================
# FASTAPI APP INIT
# ============================================================

app = FastAPI(
    title="Free Fire Bot API",
    description="Complete Free Fire Bot API with Region Support",
    version="13.0.0"
)

# ============================================================
# CONFIGURATION
# ============================================================

OAUTH_URL = "https://100067.connect.garena.com/oauth/guest/token/grant"
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
CLIENT_ID = "100067"

# Region-based MajorLogin URLs
REGION_URLS = {
    "IND": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "India"},
    "ME": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Middle East"},
    "VN": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Vietnam"},
    "BD": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Bangladesh"},
    "PK": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Pakistan"},
    "SG": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Singapore"},
    "BR": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Brazil"},
    "NA": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "North America"},
    "ID": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Indonesia"},
    "RU": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Russia"},
    "TH": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Thailand"},
    "DEFAULT": {"login": "https://loginbp.ggblueshark.com/MajorLogin", "name": "Default"}
}

AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# Store active bot instances
active_bots: Dict[str, Dict[str, Any]] = {}

# ============================================================
# MODELS (Pydantic v1 compatible)
# ============================================================

class BotResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict] = None
    bot_id: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


# [REST OF YOUR CODE - ProtoWriter, ProtoReader, Crypto, Protocol, FreeFireBot classes]
# [Copy all the classes from the previous full code - they remain exactly the same]

# ============================================================
# PROTOBUF SYSTEM (Same as before)
# ============================================================

class ProtoWriter:
    @staticmethod
    def varint(value):
        result = []
        while value > 127:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)

    @staticmethod
    def tag(field_num, wire_type):
        return ProtoWriter.varint((field_num << 3) | wire_type)

    @staticmethod
    def write_varint(field_num, value):
        return ProtoWriter.tag(field_num, 0) + ProtoWriter.varint(value)

    @staticmethod
    def write_string(field_num, value):
        if isinstance(value, str):
            value = value.encode('utf-8')
        return ProtoWriter.tag(field_num, 2) + ProtoWriter.varint(len(value)) + value

    @staticmethod
    def write_message(field_num, data):
        if isinstance(data, dict):
            data = ProtoWriter.create_message(data)
        return ProtoWriter.tag(field_num, 2) + ProtoWriter.varint(len(data)) + data

    @staticmethod
    def create_message(fields):
        result = bytearray()
        for field_num, value in sorted(fields.items()):
            if isinstance(value, dict):
                result.extend(ProtoWriter.write_message(field_num, value))
            elif isinstance(value, int):
                result.extend(ProtoWriter.write_varint(field_num, value))
            elif isinstance(value, str):
                result.extend(ProtoWriter.write_string(field_num, value))
            elif isinstance(value, bytes):
                result.extend(ProtoWriter.write_string(field_num, value))
        return bytes(result)


class ProtoReader:
    @staticmethod
    def read_varint(data, offset=0):
        result = 0
        shift = 0
        while True:
            byte = data[offset]
            result |= (byte & 0x7F) << shift
            offset += 1
            if not (byte & 0x80):
                break
            shift += 7
        return result, offset

    @staticmethod
    def parse_message(data):
        result = {}
        offset = 0
        while offset < len(data):
            try:
                tag, offset = ProtoReader.read_varint(data, offset)
                field_num = tag >> 3
                wire_type = tag & 0x7

                if wire_type == 0:
                    value, offset = ProtoReader.read_varint(data, offset)
                    result[field_num] = value
                elif wire_type == 2:
                    length, offset = ProtoReader.read_varint(data, offset)
                    if length > len(data) - offset:
                        break
                    value = data[offset:offset+length]
                    offset += length
                    try:
                        result[field_num] = value.decode('utf-8')
                    except:
                        result[field_num] = value
                else:
                    break
            except:
                break
        return result


# ============================================================
# CRYPTOGRAPHY
# ============================================================

class Crypto:
    @staticmethod
    def encrypt(data, key=None, iv=None):
        k = key if key else AES_KEY
        i = iv if iv else AES_IV
        cipher = AES.new(k, AES.MODE_CBC, i)
        return cipher.encrypt(pad(data, AES.block_size))

    @staticmethod
    def decrypt(data, key, iv):
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(data), AES.block_size)


# ============================================================
# PROTOCOL BUILDERS
# ============================================================

class Protocol:
    @staticmethod
    def build_major_login(open_id, access_token):
        random_ip = f"223.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
        random_device = f"Google|{random.randint(10000000, 99999999)}"

        fields = {
            3: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            4: "free fire",
            5: 1,
            7: "1.123.2",
            8: "Android OS 11 / API-30 (RKQ1.200826.002/eng.root.20210607.123456)",
            9: "Handheld",
            10: "Verizon",
            11: "WIFI",
            12: 1920,
            13: 1080,
            14: "280",
            15: "ARM64 FP ASIMD AES VMH | 2865 | 4",
            16: 4096,
            17: "Adreno (TM) 640",
            18: "OpenGL ES 3.2 v1.46",
            19: random_device,
            20: random_ip,
            21: "en",
            22: open_id,
            23: "8",
            24: "Handheld",
            25: {6: 55, 8: 81},
            29: access_token,
            30: 1,
            41: "Verizon",
            42: "WIFI",
            57: "7428b253defc164018c604a1ebbfebdf",
            60: 36235,
            61: 31335,
            62: 2519,
            63: 703,
            64: 25010,
            65: 26628,
            66: 32992,
            67: 36235,
            73: 3,
            74: "/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/lib/arm64",
            76: 1,
            77: "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-YPKM8jHEwAJlhpmhDhv5MQ==/base.apk",
            78: 3,
            79: 2,
            81: "64",
            83: "2019118695",
            86: "OpenGLES2",
            87: 16383,
            88: 4,
            89: b"FwQVTgUPX1UaUllDDwcWCRBpWA0FUgsvA1snWlBaO1kFYg==",
            90: random.randint(10000, 15000),
            91: "android",
            92: "KqsHTymw5/5GB23YGniUYN2/q47GATrq7eFeRatf0NkwLKEMQ0PK5BKEk72dPflAxUlEBir6Vtey83XqF593qsl8hwY=",
            95: 110009,
            97: 1,
            98: 0,
            99: "8",
            100: "8"
        }

        return ProtoWriter.create_message(fields)

    @staticmethod
    def parse_major_login_response(data):
        parsed = ProtoReader.parse_message(data)
        return {
            "account_uid": parsed.get(1, 0),
            "region": parsed.get(2, ""),
            "token": parsed.get(8, ""),
            "url": parsed.get(10, ""),
            "timestamp": parsed.get(21, 0),
            "key": parsed.get(22, b""),
            "iv": parsed.get(23, b"")
        }

    @staticmethod
    def parse_login_data(data):
        parsed = ProtoReader.parse_message(data)
        return {
            "account_uid": parsed.get(1, 0),
            "region": parsed.get(3, ""),
            "account_name": parsed.get(4, ""),
            "online_ip_port": parsed.get(14, ""),
            "clan_id": parsed.get(20, 0),
            "account_ip_port": parsed.get(32, ""),
            "clan_compiled_data": parsed.get(55, b"")
        }

    @staticmethod
    def create_auth_packet(uid, token, timestamp, key, iv):
        uid_int = int(uid)
        uid_hex = format(uid_int, 'x')
        if len(uid_hex) % 2 == 1:
            uid_hex = '0' + uid_hex

        ts_int = int(timestamp)
        ts_hex = format(ts_int, 'x')
        if len(ts_hex) % 2 == 1:
            ts_hex = '0' + ts_hex

        cipher = AES.new(key, AES.MODE_CBC, iv)
        token_padded = pad(token.encode('utf-8'), AES.block_size)
        token_encrypted = cipher.encrypt(token_padded)
        token_enc_hex = token_encrypted.hex()

        token_len_bytes = len(token_encrypted)
        token_len_hex = format(token_len_bytes, 'x')
        if len(token_len_hex) % 2 == 1:
            token_len_hex = '0' + token_len_hex

        uid_len = len(uid_hex)
        if uid_len == 8:
            uid_header = '00000000'
        elif uid_len == 9:
            uid_header = '0000000'
        elif uid_len == 10:
            uid_header = '000000'
        elif uid_len == 7:
            uid_header = '000000000'
        else:
            target_start = 16
            uid_header_len = target_start - 4 - uid_len
            if uid_header_len < 0:
                uid_header_len = 0
            uid_header = '0' * uid_header_len

        if len(token_len_hex) % 2 == 0:
            separator = "0000"
        else:
            separator = "00000"

        packet = f"0115{uid_header}{uid_hex}{ts_hex}{separator}{token_len_hex}{token_enc_hex}"
        return bytes.fromhex(packet)


# ============================================================
# BOT CLIENT
# ============================================================

class FreeFireBot:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.session = None
        self.online_writer = None
        self.chat_writer = None
        self.is_running = False
        self.account_info = {}
        self.stop_requested = False

    async def __aenter__(self):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self

    async def __aexit__(self, *args):
        await self.cleanup()
        if self.session:
            await self.session.close()

    @staticmethod
    def generate_ua():
        versions = ['5.0.2P4', '5.1.0P1', '5.2.0B1', '5.2.5P3', '5.3.0B1']
        models = ['SM-A515F', 'Redmi 9A', 'POCO M3', 'RMX2185', 'ASUS_Z01QD']
        android = ['10', '11', '12', '13']
        return f"GarenaMSDK/{random.choice(versions)}({random.choice(models)};Android {random.choice(android)};en-US;USA;)"

    async def oauth_login(self, uid: str, password: str):
        """OAuth Login to get open_id and access_token"""
        headers = {
            "Host": "100067.connect.garena.com",
            "User-Agent": self.generate_ua(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close"
        }

        data = {
            "uid": uid,
            "password": password,
            "response_type": "token",
            "client_type": "2",
            "client_secret": CLIENT_SECRET,
            "client_id": CLIENT_ID
        }

        try:
            async with self.session.post(OAUTH_URL, headers=headers, data=data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    oid = result.get("open_id")
                    at = result.get("access_token")
                    if oid and at:
                        return oid, at
        except Exception as e:
            print(f"OAuth Error: {e}")
        return None, None

    async def major_login(self, encrypted_payload: bytes, region: str):
        """MajorLogin request"""
        url = REGION_URLS.get(region.upper(), REGION_URLS["DEFAULT"])["login"]

        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB53"
        }

        try:
            async with self.session.post(url, data=encrypted_payload, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            print(f"MajorLogin Error: {e}")
        return None

    async def get_login_data(self, url: str, token: str, encrypted_payload: bytes):
        """GetLoginData request"""
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB53",
            "Authorization": f"Bearer {token}"
        }

        try:
            async with self.session.post(f"{url}/GetLoginData", data=encrypted_payload, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            print(f"GetLoginData Error: {e}")
        return None

    async def tcp_connect(self, ip: str, port: int, auth_packet: bytes, name: str):
        """TCP connection"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, int(port)),
                timeout=10
            )
            writer.write(auth_packet)
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=10)
            if data:
                return True, writer
        except Exception as e:
            print(f"TCP {name} Error: {e}")
        return False, None

    async def run_with_access_token(self, access_token: str, open_id: str, region: str):
        """Run bot with access token"""
        try:
            # Build MajorLogin
            major_payload = Protocol.build_major_login(open_id, access_token)
            encrypted_payload = Crypto.encrypt(major_payload)

            # MajorLogin
            major_response = await self.major_login(encrypted_payload, region)
            if not major_response:
                return False, "MajorLogin failed"

            # Parse MajorLogin
            major_data = Protocol.parse_major_login_response(major_response)
            if not major_data.get("account_uid"):
                return False, "Failed to parse MajorLogin response"

            # GetLoginData
            login_response = await self.get_login_data(
                major_data["url"],
                major_data["token"],
                encrypted_payload
            )
            if not login_response:
                return False, "GetLoginData failed"

            # Parse LoginData
            login_info = Protocol.parse_login_data(login_response)
            if not login_info:
                return False, "Failed to parse LoginData"

            self.account_info = {
                "account_uid": major_data["account_uid"],
                "account_name": login_info["account_name"],
                "region": login_info["region"]
            }

            # Create Auth Packet
            auth_packet = Protocol.create_auth_packet(
                major_data["account_uid"],
                major_data["token"],
                major_data["timestamp"],
                major_data["key"],
                major_data["iv"]
            )

            # Parse IPs
            online_ip, online_port = login_info["online_ip_port"].split(":")
            chat_ip, chat_port = login_info["account_ip_port"].split(":")

            # TCP Connect
            online_ok, self.online_writer = await self.tcp_connect(
                online_ip, int(online_port), auth_packet, "Online"
            )
            chat_ok, self.chat_writer = await self.tcp_connect(
                chat_ip, int(chat_port), auth_packet, "Chat"
            )

            if online_ok and chat_ok:
                self.is_running = True
                return True, "Bot fully online"
            elif online_ok or chat_ok:
                self.is_running = True
                return True, "Bot partially online"
            else:
                return False, "Failed to connect to TCP servers"

        except Exception as e:
            return False, f"Error: {str(e)}"

    async def run_with_guest(self, uid: str, password: str, region: str):
        """Run bot with guest credentials"""
        # OAuth Login
        open_id, access_token = await self.oauth_login(uid, password)
        if not open_id or not access_token:
            return False, "OAuth login failed"

        return await self.run_with_access_token(access_token, open_id, region)

    async def keep_alive(self):
        """Keep the bot running"""
        while self.is_running and not self.stop_requested:
            await asyncio.sleep(30)

    async def cleanup(self):
        """Cleanup connections"""
        self.is_running = False
        if self.online_writer:
            self.online_writer.close()
            await self.online_writer.wait_closed()
        if self.chat_writer:
            self.chat_writer.close()
            await self.chat_writer.wait_closed()

    def stop(self):
        """Stop the bot"""
        self.stop_requested = True
        self.is_running = False


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home():
    """Home page with API documentation"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Free Fire Bot API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #0a0a0a; color: #fff; }
            h1 { color: #ff6b35; }
            .endpoint { background: #1a1a1a; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid #ff6b35; }
            code { background: #333; padding: 2px 6px; border-radius: 4px; }
            .method { color: #4ec9b0; font-weight: bold; }
            .status { color: #4ec9b0; }
        </style>
    </head>
    <body>
        <h1>🎮 Free Fire Bot API v13.0</h1>
        <p>Status: <span class="status">✅ Online</span></p>
        
        <h2>📌 Endpoints</h2>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /access</h3>
            <code>/access?access={token}&open_id={open_id}&region={region}</code>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /mafu</h3>
            <code>/mafu?uid={uid}&Password={password}&region={region}</code>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /stopaccess</h3>
            <code>/stopaccess?access={token}</code>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /stopmafu</h3>
            <code>/stopmafu?uid={uid}&Password={password}</code>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /status</h3>
            <code>/status</code>
        </div>
        
        <div class="endpoint">
            <h3><span class="method">GET</span> /regions</h3>
            <code>/regions</code>
        </div>
    </body>
    </html>
    """


@app.get("/access")
async def access_endpoint(
    background_tasks: BackgroundTasks,
    access: str = Query(..., description="Access token"),
    open_id: str = Query(None, description="Open ID"),
    region: str = Query("IND", description="Region code")
):
    """Start bot with access token"""
    if not open_id:
        open_id = access[:32] if len(access) >= 32 else access
    
    bot_id = f"access_{access[:16]}"
    if bot_id in active_bots and active_bots[bot_id]["bot"].is_running:
        return JSONResponse({
            "success": False,
            "message": "Bot already running with this token",
            "bot_id": bot_id
        })
    
    region = region.upper()
    if region not in REGION_URLS:
        region = "DEFAULT"
    
    bot = FreeFireBot(bot_id)
    active_bots[bot_id] = {
        "bot": bot,
        "type": "access",
        "token": access,
        "region": region,
        "started_at": datetime.now().isoformat()
    }
    
    async def run_bot():
        async with bot:
            success, message = await bot.run_with_access_token(access, open_id, region)
            active_bots[bot_id]["success"] = success
            active_bots[bot_id]["message"] = message
            active_bots[bot_id]["account_info"] = bot.account_info
            if success:
                await bot.keep_alive()
    
    background_tasks.add_task(asyncio.create_task, run_bot())
    
    return JSONResponse({
        "success": True,
        "message": "Bot started in background",
        "bot_id": bot_id,
        "region": REGION_URLS.get(region, REGION_URLS["DEFAULT"])["name"]
    })


@app.get("/mafu")
async def mafu_endpoint(
    background_tasks: BackgroundTasks,
    uid: str = Query(..., description="Guest UID"),
    Password: str = Query(..., description="Guest Password"),
    region: str = Query("IND", description="Region code")
):
    """Start bot with guest credentials"""
    bot_id = f"mafu_{uid}"
    if bot_id in active_bots and active_bots[bot_id]["bot"].is_running:
        return JSONResponse({
            "success": False,
            "message": "Bot already running with this UID",
            "bot_id": bot_id
        })
    
    region = region.upper()
    if region not in REGION_URLS:
        region = "DEFAULT"
    
    bot = FreeFireBot(bot_id)
    active_bots[bot_id] = {
        "bot": bot,
        "type": "mafu",
        "uid": uid,
        "region": region,
        "started_at": datetime.now().isoformat()
    }
    
    async def run_bot():
        async with bot:
            success, message = await bot.run_with_guest(uid, Password, region)
            active_bots[bot_id]["success"] = success
            active_bots[bot_id]["message"] = message
            active_bots[bot_id]["account_info"] = bot.account_info
            if success:
                await bot.keep_alive()
    
    background_tasks.add_task(asyncio.create_task, run_bot())
    
    return JSONResponse({
        "success": True,
        "message": "Bot started in background",
        "bot_id": bot_id,
        "region": REGION_URLS.get(region, REGION_URLS["DEFAULT"])["name"]
    })


@app.get("/stopaccess")
async def stopaccess_endpoint(
    access: str = Query(..., description="Access token to stop")
):
    """Stop bot started with access token"""
    bot_id = f"access_{access[:16]}"
    
    if bot_id not in active_bots:
        return JSONResponse({
            "success": False,
            "message": "No active bot found with this token"
        })
    
    bot_data = active_bots[bot_id]
    bot = bot_data["bot"]
    
    if not bot.is_running:
        del active_bots[bot_id]
        return JSONResponse({
            "success": False,
            "message": "Bot was not running"
        })
    
    bot.stop()
    await bot.cleanup()
    del active_bots[bot_id]
    
    return JSONResponse({
        "success": True,
        "message": "Bot stopped successfully",
        "account_info": bot.account_info
    })


@app.get("/stopmafu")
async def stopmafu_endpoint(
    uid: str = Query(..., description="Guest UID to stop"),
    Password: str = Query("", description="Password (optional)")
):
    """Stop bot started with guest credentials"""
    bot_id = f"mafu_{uid}"
    
    if bot_id not in active_bots:
        return JSONResponse({
            "success": False,
            "message": "No active bot found with this UID"
        })
    
    bot_data = active_bots[bot_id]
    bot = bot_data["bot"]
    
    if not bot.is_running:
        del active_bots[bot_id]
        return JSONResponse({
            "success": False,
            "message": "Bot was not running"
        })
    
    bot.stop()
    await bot.cleanup()
    del active_bots[bot_id]
    
    return JSONResponse({
        "success": True,
        "message": "Bot stopped successfully",
        "account_info": bot.account_info
    })


@app.get("/status")
async def status_endpoint():
    """Get status of all active bots"""
    bots_status = []
    for bot_id, bot_data in active_bots.items():
        bot = bot_data["bot"]
        status_info = {
            "bot_id": bot_id,
            "type": bot_data["type"],
            "is_running": bot.is_running,
            "started_at": bot_data["started_at"],
            "region": bot_data.get("region", "N/A")
        }
        if bot.account_info:
            status_info["account_info"] = bot.account_info
        if "uid" in bot_data:
            status_info["uid"] = bot_data["uid"]
        bots_status.append(status_info)
    
    return JSONResponse({
        "success": True,
        "total_bots": len(active_bots),
        "active_bots": bots_status
    })


@app.get("/regions")
async def regions_endpoint():
    """List all available regions"""
    regions = []
    for code, info in REGION_URLS.items():
        if code != "DEFAULT":
            regions.append({
                "code": code,
                "name": info["name"],
                "url": info["login"]
            })
    
    return JSONResponse({
        "success": True,
        "regions": regions
    })


@app.get("/health")
async def health_endpoint():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)