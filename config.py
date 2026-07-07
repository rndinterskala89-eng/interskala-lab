"""
MHB-832SD Dashboard - Configuration
"""

import os
from pathlib import Path

def load_env_file():
    """Membaca file .env secara manual"""
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️ .env file not found, using defaults")
        return {}
    
    env_vars = {}
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

# Load .env
env_vars = load_env_file()

# ThingSpeak
THINGSPEAK_API_KEY = env_vars.get('THINGSPEAK_API_KEY', '5V62ZN3IG985VJUA')
THINGSPEAK_CHANNEL_ID = int(env_vars.get('THINGSPEAK_CHANNEL_ID', 3419249))

# Server
SERVER_HOST = env_vars.get('SERVER_HOST', '127.0.0.1')
SERVER_PORT = int(env_vars.get('SERVER_PORT', 5000))
DEBUG_MODE = env_vars.get('DEBUG_MODE', 'True').lower() == 'true'

# Thresholds
SUHU_MIN = float(env_vars.get('SUHU_MIN', 18))
SUHU_MAX = float(env_vars.get('SUHU_MAX', 26))
KELEMBABAN_MIN = float(env_vars.get('KELEMBABAN_MIN', 20))
KELEMBABAN_MAX = float(env_vars.get('KELEMBABAN_MAX', 60))

# History
SAVE_INTERVAL_MINUTES = int(env_vars.get('SAVE_INTERVAL_MINUTES', 60))

# Login
DEFAULT_USERNAME = env_vars.get('DEFAULT_USERNAME', 'admin')
DEFAULT_PASSWORD = env_vars.get('DEFAULT_PASSWORD', 'admin123')

def print_config():
    print("\n" + "="*50)
    print("📋 MHB-832SD CONFIGURATION")
    print("="*50)
    print(f"📡 Channel ID: {THINGSPEAK_CHANNEL_ID}")
    print(f"🔑 API Key: {THINGSPEAK_API_KEY[:4]}...{THINGSPEAK_API_KEY[-4:]}")
    print(f"🌐 Server: {SERVER_HOST}:{SERVER_PORT}")
    print(f"🌡️ Suhu: {SUHU_MIN}°C - {SUHU_MAX}°C")
    print(f"💧 Kelembaban: {KELEMBABAN_MIN}% - {KELEMBABAN_MAX}%")
    print("="*50)

if __name__ == "__main__":
    print_config()