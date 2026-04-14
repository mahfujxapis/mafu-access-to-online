"""
Free Fire Bot API - Complete Web Dashboard + API
Real-time bot monitoring and control
"""

from flask import Flask, request, jsonify, render_template_string, redirect, url_for
import asyncio
import aiohttp
import ssl
import json
import random
import threading
import time
from datetime import datetime, timedelta
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from collections import deque
import copy

# ============================================================
# FLASK APP INIT
# ============================================================

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

OAUTH_URL = "https://100067.connect.garena.com/oauth/guest/token/grant"
CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
CLIENT_ID = "100067"

# Region-based MajorLogin URLs
REGION_URLS = {
    "IND": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "India", "flag": "🇮🇳"},
    "ME": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Middle East", "flag": "🌍"},
    "VN": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Vietnam", "flag": "🇻🇳"},
    "BD": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Bangladesh", "flag": "🇧🇩"},
    "PK": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Pakistan", "flag": "🇵🇰"},
    "SG": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Singapore", "flag": "🇸🇬"},
    "BR": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Brazil", "flag": "🇧🇷"},
    "NA": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "North America", "flag": "🇺🇸"},
    "ID": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Indonesia", "flag": "🇮🇩"},
    "RU": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Russia", "flag": "🇷🇺"},
    "TH": {"login": "https://loginbp.ggpolarbear.com/MajorLogin", "name": "Thailand", "flag": "🇹🇭"},
    "DEFAULT": {"login": "https://loginbp.ggblueshark.com/MajorLogin", "name": "Default", "flag": "🌐"}
}

AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# Store active bot instances with real-time data
active_bots = {}
bot_threads = {}
bot_logs = deque(maxlen=100)  # Store last 100 logs
total_bots_started = 0
total_successful_logins = 0

# ============================================================
# PROTOBUF SYSTEM
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
        self.connection_status = {"online": False, "chat": False}
        self.last_activity = datetime.now()
        self.login_progress = "Waiting to start..."
        self.uptime_start = None

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
        self.login_progress = "Connecting to OAuth..."
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
                        self.login_progress = "OAuth login successful!"
                        return oid, at
                    else:
                        self.login_progress = "OAuth failed: Missing credentials"
        except Exception as e:
            self.login_progress = f"OAuth error: {str(e)[:50]}"
        return None, None

    async def major_login(self, encrypted_payload: bytes, region: str):
        """MajorLogin request"""
        self.login_progress = f"Connecting to {region} server..."
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
                    self.login_progress = "MajorLogin successful!"
                    return await resp.read()
                else:
                    self.login_progress = f"MajorLogin failed: HTTP {resp.status}"
        except Exception as e:
            self.login_progress = f"MajorLogin error: {str(e)[:50]}"
        return None

    async def get_login_data(self, url: str, token: str, encrypted_payload: bytes):
        """GetLoginData request"""
        self.login_progress = "Fetching login data..."
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
                    self.login_progress = "Login data received!"
                    return await resp.read()
                else:
                    self.login_progress = f"GetLoginData failed: HTTP {resp.status}"
        except Exception as e:
            self.login_progress = f"GetLoginData error: {str(e)[:50]}"
        return None

    async def tcp_connect(self, ip: str, port: int, auth_packet: bytes, name: str):
        """TCP connection"""
        self.login_progress = f"Connecting to {name} server..."
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, int(port)),
                timeout=10
            )
            writer.write(auth_packet)
            await writer.drain()
            data = await asyncio.wait_for(reader.read(4096), timeout=10)
            if data:
                self.connection_status[name.lower()] = True
                return True, writer
        except Exception as e:
            self.connection_status[name.lower()] = False
            self.login_progress = f"{name} connection failed: {str(e)[:30]}"
        return False, None

    async def run_with_access_token(self, access_token: str, open_id: str, region: str):
        """Run bot with access token"""
        global total_successful_logins
        try:
            # Build MajorLogin
            self.login_progress = "Building login payload..."
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
                "region": login_info["region"],
                "clan_id": login_info.get("clan_id", 0)
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
                self.uptime_start = datetime.now()
                self.login_progress = "✅ Bot fully online!"
                total_successful_logins += 1
                add_log("success", f"Bot {self.account_info['account_name']} ({self.account_info['account_uid']}) is fully online!")
                return True, "Bot fully online"
            elif online_ok or chat_ok:
                self.is_running = True
                self.uptime_start = datetime.now()
                self.login_progress = "⚠️ Bot partially online"
                add_log("warning", f"Bot {self.account_info.get('account_name', 'Unknown')} partially online")
                return True, "Bot partially online"
            else:
                add_log("error", f"Bot failed to connect to TCP servers")
                return False, "Failed to connect to TCP servers"

        except Exception as e:
            add_log("error", f"Bot error: {str(e)[:100]}")
            return False, f"Error: {str(e)}"

    async def run_with_guest(self, uid: str, password: str, region: str):
        """Run bot with guest credentials"""
        # OAuth Login
        open_id, access_token = await self.oauth_login(uid, password)
        if not open_id or not access_token:
            add_log("error", f"OAuth login failed for UID: {uid}")
            return False, "OAuth login failed"

        return await self.run_with_access_token(access_token, open_id, region)

    async def keep_alive(self):
        """Keep the bot running"""
        while self.is_running and not self.stop_requested:
            self.last_activity = datetime.now()
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
        self.login_progress = "Bot stopped"
        add_log("info", f"Bot {self.account_info.get('account_name', 'Unknown')} stopped")

    def get_uptime(self):
        """Get bot uptime"""
        if self.uptime_start and self.is_running:
            delta = datetime.now() - self.uptime_start
            return str(delta).split('.')[0]
        return "N/A"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def add_log(level, message):
    """Add log entry"""
    bot_logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "message": message
    })


def run_bot_in_thread(bot_id, bot, coro_func, *args):
    """Run async bot in a separate thread"""
    global total_bots_started
    total_bots_started += 1
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def run():
        async with bot:
            success, message = await coro_func(*args)
            active_bots[bot_id]["success"] = success
            active_bots[bot_id]["message"] = message
            active_bots[bot_id]["account_info"] = bot.account_info
            if success:
                await bot.keep_alive()
            else:
                # Remove failed bot after 10 seconds
                await asyncio.sleep(10)
                if bot_id in active_bots:
                    del active_bots[bot_id]
    
    try:
        loop.run_until_complete(run())
    except Exception as e:
        add_log("error", f"Bot {bot_id} thread error: {str(e)[:50]}")
    finally:
        loop.close()
        if bot_id in bot_threads:
            del bot_threads[bot_id]


# ============================================================
# WEBSITE TEMPLATE
# ============================================================

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 Free Fire Bot Control Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            color: #fff;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        
        /* Header */
        .header {
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,107,53,0.3);
        }
        .header h1 {
            font-size: 2.5em;
            background: linear-gradient(90deg, #ff6b35, #f7931e);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 5px;
        }
        .header p { opacity: 0.8; }
        
        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s;
        }
        .stat-card:hover { transform: translateY(-3px); border-color: #ff6b35; }
        .stat-value { font-size: 2.5em; font-weight: bold; color: #ff6b35; }
        .stat-label { opacity: 0.7; margin-top: 5px; }
        
        /* Control Panel */
        .control-panel {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
            margin-bottom: 25px;
        }
        .panel {
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .panel h2 {
            margin-bottom: 20px;
            color: #ff6b35;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            opacity: 0.8;
            font-size: 0.9em;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 10px;
            color: #fff;
            font-size: 1em;
            outline: none;
            transition: border 0.3s;
        }
        .form-group input:focus, .form-group select:focus {
            border-color: #ff6b35;
        }
        .form-group select option { background: #24243e; }
        
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 10px;
            font-size: 1em;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-right: 10px;
            margin-top: 10px;
        }
        .btn-primary {
            background: linear-gradient(90deg, #ff6b35, #f7931e);
            color: #fff;
        }
        .btn-primary:hover {
            transform: scale(1.02);
            box-shadow: 0 5px 20px rgba(255,107,53,0.4);
        }
        .btn-danger {
            background: linear-gradient(90deg, #e74c3c, #c0392b);
            color: #fff;
        }
        .btn-danger:hover {
            transform: scale(1.02);
            box-shadow: 0 5px 20px rgba(231,76,60,0.4);
        }
        .btn-success {
            background: linear-gradient(90deg, #27ae60, #2ecc71);
            color: #fff;
        }
        
        /* Active Bots Table */
        .bots-section {
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .bots-section h2 {
            margin-bottom: 20px;
            color: #ff6b35;
        }
        .table-container { overflow-x: auto; }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { opacity: 0.7; font-weight: 500; }
        .status-badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .status-online { background: rgba(46,204,113,0.3); color: #2ecc71; }
        .status-offline { background: rgba(231,76,60,0.3); color: #e74c3c; }
        .status-partial { background: rgba(241,196,15,0.3); color: #f1c40f; }
        
        .action-btn {
            padding: 5px 15px;
            border-radius: 5px;
            font-size: 0.85em;
            margin: 2px;
            border: none;
            cursor: pointer;
        }
        
        /* Logs Section */
        .logs-section {
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .logs-container {
            max-height: 200px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        .log-entry {
            padding: 5px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .log-time { color: #f7931e; margin-right: 10px; }
        .log-success { color: #2ecc71; }
        .log-error { color: #e74c3c; }
        .log-warning { color: #f1c40f; }
        .log-info { color: #3498db; }
        
        /* Responsive */
        @media (max-width: 768px) {
            .control-panel { grid-template-columns: 1fr; }
            .header h1 { font-size: 1.8em; }
        }
        
        /* API Section */
        .api-section {
            margin-top: 20px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        .api-section code {
            background: rgba(255,255,255,0.1);
            padding: 2px 8px;
            border-radius: 5px;
            font-family: monospace;
        }
        
        /* Loading Animation */
        .loading {
            display: inline-block;
            width: 12px;
            height: 12px;
            border: 2px solid #ff6b35;
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 1s linear infinite;
            margin-left: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        
        .refresh-indicator { float: right; font-size: 0.8em; opacity: 0.6; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🔥 Free Fire Bot Control Panel</h1>
            <p>Real-time Bot Management & Monitoring Dashboard</p>
            <div class="api-section">
                <strong>📡 API Endpoints:</strong> 
                <code>/access?access=TOKEN&region=BD</code> | 
                <code>/mafu?uid=UID&Password=PASS&region=BD</code> |
                <code>/status</code> |
                <code>/regions</code>
            </div>
        </div>
        
        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="activeBotsCount">0</div>
                <div class="stat-label">Active Bots</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="totalBotsStarted">{{ total_started }}</div>
                <div class="stat-label">Total Started</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="successfulLogins">{{ successful_logins }}</div>
                <div class="stat-label">Successful Logins</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="uptimeDisplay">00:00:00</div>
                <div class="stat-label">Server Uptime</div>
            </div>
        </div>
        
        <!-- Control Panels -->
        <div class="control-panel">
            <!-- Guest Login Panel -->
            <div class="panel">
                <h2>👤 Guest Login (Mafu)</h2>
                <form id="mafuForm">
                    <div class="form-group">
                        <label>UID (Guest ID)</label>
                        <input type="text" id="mafuUid" placeholder="Enter UID" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="text" id="mafuPassword" placeholder="Enter Password" required>
                    </div>
                    <div class="form-group">
                        <label>Region</label>
                        <select id="mafuRegion">
                            {% for code, info in regions.items() if code != 'DEFAULT' %}
                            <option value="{{ code }}">{{ info.flag }} {{ info.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">🚀 Start Bot</button>
                    <button type="button" class="btn btn-danger" onclick="stopMafu()">🛑 Stop Bot</button>
                </form>
            </div>
            
            <!-- Access Token Panel -->
            <div class="panel">
                <h2>🔑 Access Token Login</h2>
                <form id="accessForm">
                    <div class="form-group">
                        <label>Access Token</label>
                        <input type="text" id="accessToken" placeholder="Enter Access Token" required>
                    </div>
                    <div class="form-group">
                        <label>Open ID (Optional)</label>
                        <input type="text" id="openId" placeholder="Auto-generated if empty">
                    </div>
                    <div class="form-group">
                        <label>Region</label>
                        <select id="accessRegion">
                            {% for code, info in regions.items() if code != 'DEFAULT' %}
                            <option value="{{ code }}">{{ info.flag }} {{ info.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary">🚀 Start Bot</button>
                    <button type="button" class="btn btn-danger" onclick="stopAccess()">🛑 Stop Bot</button>
                </form>
            </div>
        </div>
        
        <!-- Active Bots Table -->
        <div class="bots-section">
            <h2>
                🤖 Active Bots 
                <span class="refresh-indicator" id="refreshIndicator">Auto-refresh in <span id="countdown">5</span>s</span>
            </h2>
            <div class="table-container">
                <table id="botsTable">
                    <thead>
                        <tr>
                            <th>Bot ID</th>
                            <th>Type</th>
                            <th>Account Name</th>
                            <th>Account UID</th>
                            <th>Region</th>
                            <th>Status</th>
                            <th>Progress</th>
                            <th>Uptime</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="botsTableBody">
                        <tr><td colspan="9" style="text-align: center;">No active bots</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Logs Section -->
        <div class="logs-section">
            <h2>📋 Real-time Logs</h2>
            <div class="logs-container" id="logsContainer">
                {% for log in logs %}
                <div class="log-entry">
                    <span class="log-time">[{{ log.time }}]</span>
                    <span class="log-{{ log.level }}">{{ log.message }}</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    
    <script>
        let countdown = 5;
        let autoRefresh = true;
        
        // Update real-time data
        async function refreshData() {
            try {
                const response = await fetch('/status');
                const data = await response.json();
                
                // Update stats
                document.getElementById('activeBotsCount').textContent = data.total_bots;
                
                // Update table
                const tbody = document.getElementById('botsTableBody');
                if (data.active_bots && data.active_bots.length > 0) {
                    tbody.innerHTML = '';
                    data.active_bots.forEach(bot => {
                        const row = tbody.insertRow();
                        const accountInfo = bot.account_info || {};
                        const status = bot.is_running ? 'online' : 'offline';
                        const statusText = bot.is_running ? '🟢 Online' : '🔴 Offline';
                        const statusClass = bot.is_running ? 'status-online' : 'status-offline';
                        const progress = bot.bot?.login_progress || bot.message || 'N/A';
                        const uptime = bot.bot?.uptime_start ? getUptime(bot.bot.uptime_start) : 'N/A';
                        
                        row.innerHTML = `
                            <td><code>${bot.bot_id}</code></td>
                            <td>${bot.type === 'mafu' ? '👤 Guest' : '🔑 Token'}</td>
                            <td>${accountInfo.account_name || 'N/A'}</td>
                            <td>${accountInfo.account_uid || 'N/A'}</td>
                            <td>${bot.region || 'N/A'}</td>
                            <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                            <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${progress}</td>
                            <td>${uptime}</td>
                            <td>
                                <button class="action-btn btn-danger" onclick="stopBot('${bot.bot_id}', '${bot.type}', '${bot.uid || bot.token || ''}')">Stop</button>
                            </td>
                        `;
                    });
                } else {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center;">No active bots</td></tr>';
                }
            } catch (e) {
                console.error('Failed to refresh data:', e);
            }
            
            // Refresh logs
            try {
                const logsResponse = await fetch('/logs');
                const logsData = await logsResponse.json();
                const logsContainer = document.getElementById('logsContainer');
                logsContainer.innerHTML = '';
                logsData.logs.forEach(log => {
                    const div = document.createElement('div');
                    div.className = 'log-entry';
                    div.innerHTML = `<span class="log-time">[${log.time}]</span><span class="log-${log.level}">${log.message}</span>`;
                    logsContainer.appendChild(div);
                });
                logsContainer.scrollTop = logsContainer.scrollHeight;
            } catch (e) {
                console.error('Failed to refresh logs:', e);
            }
        }
        
        function getUptime(startTime) {
            if (!startTime) return 'N/A';
            const start = new Date(startTime);
            const now = new Date();
            const diff = Math.floor((now - start) / 1000);
            const hours = Math.floor(diff / 3600);
            const minutes = Math.floor((diff % 3600) / 60);
            const seconds = diff % 60;
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
        
        function updateCountdown() {
            document.getElementById('countdown').textContent = countdown;
            countdown--;
            if (countdown < 0) {
                refreshData();
                countdown = 5;
            }
        }
        
        // Start bot functions
        document.getElementById('mafuForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const uid = document.getElementById('mafuUid').value;
            const password = document.getElementById('mafuPassword').value;
            const region = document.getElementById('mafuRegion').value;
            
            try {
                const response = await fetch(`/mafu?uid=${uid}&Password=${password}&region=${region}`);
                const data = await response.json();
                alert(data.message || 'Bot start request sent!');
                refreshData();
            } catch (e) {
                alert('Failed to start bot: ' + e.message);
            }
        });
        
        document.getElementById('accessForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const token = document.getElementById('accessToken').value;
            const openId = document.getElementById('openId').value;
            const region = document.getElementById('accessRegion').value;
            
            let url = `/access?access=${token}&region=${region}`;
            if (openId) url += `&open_id=${openId}`;
            
            try {
                const response = await fetch(url);
                const data = await response.json();
                alert(data.message || 'Bot start request sent!');
                refreshData();
            } catch (e) {
                alert('Failed to start bot: ' + e.message);
            }
        });
        
        async function stopMafu() {
            const uid = document.getElementById('mafuUid').value;
            const password = document.getElementById('mafuPassword').value;
            if (!uid) { alert('Enter UID first'); return; }
            
            try {
                const response = await fetch(`/stopmafu?uid=${uid}&Password=${password}`);
                const data = await response.json();
                alert(data.message || 'Bot stop request sent!');
                refreshData();
            } catch (e) {
                alert('Failed to stop bot: ' + e.message);
            }
        }
        
        async function stopAccess() {
            const token = document.getElementById('accessToken').value;
            if (!token) { alert('Enter Access Token first'); return; }
            
            try {
                const response = await fetch(`/stopaccess?access=${token}`);
                const data = await response.json();
                alert(data.message || 'Bot stop request sent!');
                refreshData();
            } catch (e) {
                alert('Failed to stop bot: ' + e.message);
            }
        }
        
        async function stopBot(botId, type, identifier) {
            let url;
            if (type === 'mafu') {
                url = `/stopmafu?uid=${identifier}`;
            } else {
                url = `/stopaccess?access=${identifier}`;
            }
            
            try {
                const response = await fetch(url);
                const data = await response.json();
                alert(data.message || 'Bot stopped!');
                refreshData();
            } catch (e) {
                alert('Failed to stop bot: ' + e.message);
            }
        }
        
        // Auto-refresh
        setInterval(updateCountdown, 1000);
        refreshData(); // Initial load
        setInterval(refreshData, 5000); // Refresh every 5 seconds
    </script>
</body>
</html>
"""


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route('/')
def dashboard():
    """Main dashboard"""
    logs = list(bot_logs)
    logs.reverse()
    return render_template_string(
        DASHBOARD_TEMPLATE,
        regions=REGION_URLS,
        total_started=total_bots_started,
        successful_logins=total_successful_logins,
        logs=logs[:20]
    )


@app.route('/logs')
def get_logs():
    """Get recent logs as JSON"""
    logs = list(bot_logs)
    return jsonify({"success": True, "logs": logs})


@app.route('/access')
def access_endpoint():
    """Start bot with access token"""
    access = request.args.get('access')
    open_id = request.args.get('open_id')
    region = request.args.get('region', 'IND').upper()
    
    if not access:
        return jsonify({"success": False, "message": "Missing access token"}), 400
    
    if not open_id:
        open_id = access[:32] if len(access) >= 32 else access
    
    bot_id = f"access_{access[:16]}"
    
    if bot_id in active_bots and active_bots[bot_id]["bot"].is_running:
        return jsonify({
            "success": False,
            "message": "Bot already running with this token",
            "bot_id": bot_id
        })
    
    if region not in REGION_URLS:
        region = "DEFAULT"
    
    bot = FreeFireBot(bot_id)
    active_bots[bot_id] = {
        "bot": bot,
        "type": "access",
        "token": access,
        "region": region,
        "started_at": datetime.now().isoformat(),
        "uid": None
    }
    
    add_log("info", f"Starting access token bot in {REGION_URLS[region]['name']}")
    
    thread = threading.Thread(
        target=run_bot_in_thread,
        args=(bot_id, bot, bot.run_with_access_token, access, open_id, region),
        daemon=True
    )
    thread.start()
    bot_threads[bot_id] = thread
    
    return jsonify({
        "success": True,
        "message": "Bot started in background",
        "bot_id": bot_id,
        "region": REGION_URLS.get(region, REGION_URLS["DEFAULT"])["name"]
    })


@app.route('/mafu')
def mafu_endpoint():
    """Start bot with guest credentials"""
    uid = request.args.get('uid')
    password = request.args.get('Password')
    region = request.args.get('region', 'IND').upper()
    
    if not uid or not password:
        return jsonify({"success": False, "message": "Missing uid or password"}), 400
    
    bot_id = f"mafu_{uid}"
    
    if bot_id in active_bots and active_bots[bot_id]["bot"].is_running:
        return jsonify({
            "success": False,
            "message": "Bot already running with this UID",
            "bot_id": bot_id
        })
    
    if region not in REGION_URLS:
        region = "DEFAULT"
    
    bot = FreeFireBot(bot_id)
    active_bots[bot_id] = {
        "bot": bot,
        "type": "mafu",
        "uid": uid,
        "region": region,
        "started_at": datetime.now().isoformat(),
        "token": None
    }
    
    add_log("info", f"Starting guest bot UID: {uid} in {REGION_URLS[region]['name']}")
    
    thread = threading.Thread(
        target=run_bot_in_thread,
        args=(bot_id, bot, bot.run_with_guest, uid, password, region),
        daemon=True
    )
    thread.start()
    bot_threads[bot_id] = thread
    
    return jsonify({
        "success": True,
        "message": "Bot started in background",
        "bot_id": bot_id,
        "region": REGION_URLS.get(region, REGION_URLS["DEFAULT"])["name"]
    })


@app.route('/stopaccess')
def stopaccess_endpoint():
    """Stop bot started with access token"""
    access = request.args.get('access')
    
    if not access:
        return jsonify({"success": False, "message": "Missing access token"}), 400
    
    bot_id = f"access_{access[:16]}"
    
    if bot_id not in active_bots:
        return jsonify({
            "success": False,
            "message": "No active bot found with this token"
        })
    
    bot_data = active_bots[bot_id]
    bot = bot_data["bot"]
    
    if not bot.is_running:
        del active_bots[bot_id]
        return jsonify({
            "success": False,
            "message": "Bot was not running"
        })
    
    add_log("info", f"Stopping access token bot")
    bot.stop()
    
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bot.cleanup())
    loop.close()
    
    account_info = bot.account_info
    del active_bots[bot_id]
    
    return jsonify({
        "success": True,
        "message": "Bot stopped successfully",
        "account_info": account_info
    })


@app.route('/stopmafu')
def stopmafu_endpoint():
    """Stop bot started with guest credentials"""
    uid = request.args.get('uid')
    password = request.args.get('Password', '')
    
    if not uid:
        return jsonify({"success": False, "message": "Missing uid"}), 400
    
    bot_id = f"mafu_{uid}"
    
    if bot_id not in active_bots:
        return jsonify({
            "success": False,
            "message": "No active bot found with this UID"
        })
    
    bot_data = active_bots[bot_id]
    bot = bot_data["bot"]
    
    if not bot.is_running:
        del active_bots[bot_id]
        return jsonify({
            "success": False,
            "message": "Bot was not running"
        })
    
    add_log("info", f"Stopping guest bot UID: {uid}")
    bot.stop()
    
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bot.cleanup())
    loop.close()
    
    account_info = bot.account_info
    del active_bots[bot_id]
    
    return jsonify({
        "success": True,
        "message": "Bot stopped successfully",
        "account_info": account_info
    })


@app.route('/status')
def status_endpoint():
    """Get status of all active bots"""
    bots_status = []
    for bot_id, bot_data in active_bots.items():
        bot = bot_data["bot"]
        status_info = {
            "bot_id": bot_id,
            "type": bot_data["type"],
            "is_running": bot.is_running,
            "started_at": bot_data["started_at"],
            "region": bot_data.get("region", "N/A"),
            "uid": bot_data.get("uid"),
            "token": bot_data.get("token", "")[:20] + "..." if bot_data.get("token") else None,
            "account_info": bot.account_info,
            "message": bot_data.get("message", ""),
            "bot": {
                "login_progress": bot.login_progress,
                "uptime_start": bot.uptime_start.isoformat() if bot.uptime_start else None,
                "connection_status": bot.connection_status
            }
        }
        bots_status.append(status_info)
    
    return jsonify({
        "success": True,
        "total_bots": len(active_bots),
        "active_bots": bots_status
    })


@app.route('/regions')
def regions_endpoint():
    """List all available regions"""
    regions = []
    for code, info in REGION_URLS.items():
        if code != "DEFAULT":
            regions.append({
                "code": code,
                "name": info["name"],
                "flag": info["flag"],
                "url": info["login"]
            })
    
    return jsonify({
        "success": True,
        "regions": regions
    })


@app.route('/health')
def health_endpoint():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_bots": len(active_bots)
    })


if __name__ == '__main__':
    add_log("info", "🚀 Free Fire Bot Server Started!")
    app.run(host='0.0.0.0', port=8000, debug=False)