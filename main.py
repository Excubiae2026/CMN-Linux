#!/usr/bin/env python3
import os
import json
import sqlite3
import subprocess
import threading
import re
import random
import time
import argparse
from datetime import datetime
from ecdsa import SECP256k1, SigningKey
import requests
from flask import Flask, jsonify
import socket

# ==============================
# CONFIG
# ==============================
DATA_DIR = os.path.expanduser("~/.cmn")
PUZZLE_FILE = os.path.join(DATA_DIR, "puzzle77.json")
DB_PATH = os.path.join(DATA_DIR, "chunk_progress.db")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
PRIVKEY_FILE = os.path.join(DATA_DIR, "privkey.txt")
LOCAL_VERSION = "1.0.0"
VERSION_URL = "https://raw.githubusercontent.com/Excubiae2026/CMN-Linux/main/version.txt"

os.makedirs(DATA_DIR, exist_ok=True)

# ==============================
# Version check
# ==============================
def check_version():
    try:
        r = requests.get(VERSION_URL, timeout=5)
        r.raise_for_status()
        latest_version = r.text.strip()
        if LOCAL_VERSION != latest_version:
            print(f"[{datetime.now()}] ⚠️ New version available: {latest_version} (local: {LOCAL_VERSION})")
        else:
            print(f"[{datetime.now()}] ✅ Daemon is up to date (version {LOCAL_VERSION})")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Failed to check version: {e}")

# ==============================
# JSON helpers
# ==============================
def load_local_json(path=PUZZLE_FILE):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def save_local_json(data, path=PUZZLE_FILE):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

# ==============================
# DB init
# ==============================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunk_progress (
            chunk_id INTEGER PRIMARY KEY,
            current_hex TEXT,
            end_hex TEXT,
            completed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# ==============================
# Keys
# ==============================
def generate_keys():
    if not os.path.exists(PRIVKEY_FILE):
        sk = SigningKey.generate(curve=SECP256k1)
        privkey_hex = sk.to_string().hex()
        with open(PRIVKEY_FILE, "w") as f:
            f.write(privkey_hex)
        print(f"🔑 Private key saved to {PRIVKEY_FILE}")
    else:
        with open(PRIVKEY_FILE, "r") as f:
            privkey_hex = f.read().strip()

    sk = SigningKey.from_string(bytes.fromhex(privkey_hex), curve=SECP256k1)
    vk = sk.get_verifying_key()
    pubkey_hex = "04" + vk.to_string().hex()
    print(f"📡 Public key: {pubkey_hex[:16]}...{pubkey_hex[-16:]}")
    return pubkey_hex

# ==============================
# Accounts
# ==============================
def get_balance_for_pubkey(pubkey):
    if not os.path.exists(ACCOUNTS_FILE):
        return 0.0
    try:
        accounts = load_local_json(ACCOUNTS_FILE)
        for acc in accounts:
            key = acc.get("pubkey") or acc.get("pub_key")
            if key == pubkey:
                return float(acc.get("balance", 0.0))
    except Exception as e:
        print(f"[{datetime.now()}] Failed reading accounts.json: {e}")
    return 0.0

def update_local_balance(pubkey, amount):
    accounts = load_local_json(ACCOUNTS_FILE)
    updated = False
    for acc in accounts:
        key = acc.get("pubkey") or acc.get("pub_key")
        if key == pubkey:
            acc["balance"] = round(acc.get("balance", 0.0) + amount, 8)
            updated = True
            break
    if not updated:
        accounts.append({"pubkey": pubkey, "balance": amount})
    save_local_json(accounts, ACCOUNTS_FILE)

# ==============================
# HTTP Server (VPN-friendly)
# ==============================
def start_server():
    app = Flask(__name__)

    @app.route("/current.json", methods=["GET"])
    def current():
        puzzle = load_local_json()
        return jsonify(puzzle)

    def run_flask():
        app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)

    threading.Thread(target=run_flask, daemon=True).start()

    # Print all accessible IPs
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"[{datetime.now()}] 🌐 Server started at http://{local_ip}:8000/current.json")
    except:
        print(f"[{datetime.now()}] 🌐 Server started at 0.0.0.0:8000 (check your VPN/firewall)")
    print(f"[{datetime.now()}] 🌐 Also accessible via http://localhost:8000/current.json")

# ==============================
# Mining
# ==============================
def mine_chunk(chunk_id, device_id=None, pubkey=None):
    print(f"[{datetime.now()}] Starting chunk {chunk_id} on device {device_id}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT current_hex, end_hex, completed FROM chunk_progress WHERE chunk_id=?", (chunk_id,))
    row = cur.fetchone()
    conn.close()
    if not row or row[2]:
        print(f"[Chunk {chunk_id}] Skipped (missing or completed)")
        return

    current_hex, end_hex, _ = row
    current = int(current_hex, 16)
    end = int(end_hex, 16)

    miner = "./bitcrack/cuBitcrack.exe" if os.name == "nt" else "./bitcrack/cuBitcrack"
    cmd = [miner, "--keyspace", f"{current:x}:{end:x}", "--compression", "BOTH", "-f", "--out", "foundkey.txt", "--in", "addresses.txt"]
    if device_id is not None:
        cmd.extend(["-d", str(device_id)])

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    cm_per_min = 1.5
    last_time = time.time()
    earned_cm = 0.0

    for line in process.stdout:
        line = line.strip()
        print(f"[Chunk {chunk_id}] {line}")

        m = re.search(r"\(([\d,]+) total\)", line)
        if m:
            mined = int(m.group(1).replace(",", ""))
            current = min(current + mined, end)
            current_hex = f"{current:064x}"

            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE chunk_progress SET current_hex=? WHERE chunk_id=?", (current_hex, chunk_id))
            conn.commit()
            conn.close()

            puzzle_json = load_local_json()
            for c in puzzle_json:
                if c["chunk_id"] == chunk_id:
                    c["current_hex"] = current_hex
                    break
            save_local_json(puzzle_json)

        now = time.time()
        if now - last_time >= 60 and pubkey:
            earned_cm += cm_per_min
            last_time = now
            update_local_balance(pubkey, cm_per_min)
            print(f"[Chunk {chunk_id}] 💰 Earned {cm_per_min} CM → total {earned_cm:.2f} CM")

        if "FOUND" in line.upper():
            print(f"[Chunk {chunk_id}] ✅ KEY FOUND")
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE chunk_progress SET completed=1 WHERE chunk_id=?", (chunk_id,))
            conn.commit()
            conn.close()

            puzzle_json = load_local_json()
            for c in puzzle_json:
                if c["chunk_id"] == chunk_id:
                    c["completed"] = 1
                    break
            save_local_json(puzzle_json)

            try: os.remove("foundkey.txt")
            except: pass
            process.kill()
            return

    process.wait()
    if current >= end:
        print(f"[Chunk {chunk_id}] ✅ COMPLETED")
        print(f"[Chunk {chunk_id}] 💰 Total CM earned: {earned_cm:.2f}")

# ==============================
# GPU detection
# ==============================
def detect_gpus():
    try:
        import torch
        return torch.cuda.device_count()
    except Exception:
        return 0

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--devices", action="store_true", help="Use GPUs (1 chunk per GPU)")
    args = parser.parse_args()

    print("🚀 CryptoMesh Daemon Starting")

    # Version check
    check_version()

    init_db()
    pubkey = generate_keys()

    # Start VPN-friendly HTTP server
    start_server()

    puzzle = load_local_json()
    if not puzzle:
        print("❌ puzzle77.json missing")
        exit(1)

    conn = sqlite3.connect(DB_PATH)
    for c in puzzle:
        conn.execute(
            "INSERT OR IGNORE INTO chunk_progress(chunk_id, current_hex, end_hex, completed) VALUES (?, ?, ?, ?)",
            (c["chunk_id"], c["current_hex"], c["end_hex"], int(c.get("completed", False)))
        )
    conn.commit()
    conn.close()

    gpu_count = detect_gpus() if args.devices else 1
    print(f"🔧 Using {gpu_count} device(s)")

    available_chunks = [c["chunk_id"] for c in puzzle if not c.get("completed", False)]
    random.shuffle(available_chunks)

    threads = []
    for i in range(min(gpu_count, len(available_chunks))):
        t = threading.Thread(target=mine_chunk, args=(available_chunks[i], i if args.devices else None, pubkey), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Daemon stopped")
