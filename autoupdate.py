import os
import subprocess
import requests
import hashlib
import shutil

GITHUB_RAW_URL = "https://raw.githubusercontent.com/Excubiae2026/CMN-Linux/main/main.py"
LOCAL_FILE = "main.py"

def get_file_hash(path):
    """Return SHA256 hash of a file, or None if missing."""
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

def get_remote_hash():
    """Download remote file and return hash + content."""
    r = requests.get(GITHUB_RAW_URL, timeout=10)
    if r.status_code != 200:
        return None, None
    content = r.content
    h = hashlib.sha256(content).hexdigest()
    return h, content

def auto_update():
    print("[AUTOUPDATE] Checking for updates…")

    local_hash = get_file_hash(LOCAL_FILE)
    remote_hash, remote_content = get_remote_hash()

    if not remote_hash:
        print("[AUTOUPDATE] Could not fetch remote version.")
        return

    if local_hash == remote_hash:
        print("[AUTOUPDATE] Already up to date.")
        return

    print("[AUTOUPDATE] New version detected! Updating…")


    # 2. Backup old file
    if os.path.exists(LOCAL_FILE):
        shutil.copy(LOCAL_FILE, LOCAL_FILE + ".bak")

    # 3. Write new version
    with open(LOCAL_FILE, "wb") as f:
        f.write(remote_content)
    print("[AUTOUPDATE] main.py updated successfully.")

    # 4. Restart daemon
    print("[AUTOUPDATE] Restarting daemon…")
    try:
        os.execvp("python", ["python", LOCAL_FILE])
    except Exception as e:
        print("[AUTOUPDATE] Failed to restart:", e)

if __name__ == '__main__':
    auto_update()
