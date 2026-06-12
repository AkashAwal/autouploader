import base64
import json
import os
import re
import struct
import time

import requests as _requests
from Crypto.Cipher import AES
from mega import Mega

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}
_SEQ = int(time.time()) % 100000


# --- Crypto helpers (own impl to avoid mega.crypto quirks) ---

def _b64d(s):
    s = str(s) + '=='
    return base64.b64decode(s.translate(str.maketrans('-_', '+/')))


def _b64e(b):
    return base64.b64encode(b).translate(str.maketrans('+/', '-_')).decode().rstrip('=')


def _to_a32(b):
    if isinstance(b, str):
        b = b.encode('latin-1')
    b += b'\0' * (-len(b) % 4)
    return struct.unpack('>%dI' % (len(b) // 4), b)


def _to_bytes(a):
    return struct.pack('>%dI' % len(a), *a)


def _xor(a, b):
    return tuple(x ^ y for x, y in zip(a, b))


def _decrypt_attr(data: str, key: tuple) -> dict:
    k = _to_bytes(key[:4])
    raw = _b64d(data)
    cipher = AES.new(k, AES.MODE_CBC, b'\0' * 16)
    decrypted = cipher.decrypt(raw)
    match = re.search(rb'\{.+\}', decrypted)
    return json.loads(match.group().decode('utf-8'))


def _file_key(k_str: str, folder_key: tuple) -> tuple:
    if ':' in k_str:
        k_str = k_str.split(':')[1]
    enc = _to_a32(_b64d(k_str))
    # Repeat folder key to match encrypted key length
    fk = (folder_key * ((len(enc) // len(folder_key)) + 1))[:len(enc)]
    node_key = _xor(enc, fk)
    if len(node_key) >= 8:
        return (
            node_key[0] ^ node_key[4],
            node_key[1] ^ node_key[5],
            node_key[2] ^ node_key[6],
            node_key[3] ^ node_key[7],
        )
    return node_key[:4]


# --- Mega public folder API ---

def _parse_url(folder_url: str):
    root_match = re.search(r"/folder/([^/#?]+)#([^/]+)", folder_url)
    if not root_match:
        raise ValueError(f"Invalid Mega folder URL: {folder_url}")
    root_handle = root_match.group(1)
    key_b64 = root_match.group(2)
    sub_match = re.search(r"#[^/]+/folder/([^/#?]+)", folder_url)
    subfolder_handle = sub_match.group(1) if sub_match else None
    return root_handle, key_b64, subfolder_handle


def _fetch_nodes(root_handle: str) -> list:
    url = f"https://g.api.mega.co.nz/cs?id={_SEQ}&n={root_handle}"
    resp = _requests.post(url, json=[{"a": "f", "c": 1, "ca": 1, "r": 1}], timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if isinstance(result, int):
        raise RuntimeError(f"Mega API error: {result}")
    return result[0].get("f", [])


def list_videos(folder_url: str) -> list:
    root_handle, key_b64, subfolder_handle = _parse_url(folder_url)
    nodes = _fetch_nodes(root_handle)
    folder_key = _to_a32(_b64d(key_b64))
    target_parent = subfolder_handle or root_handle

    videos = []
    for node in nodes:
        if node.get("t") != 0 or node.get("p") != target_parent:
            continue
        try:
            fk = _file_key(node["k"], folder_key)
            name = _decrypt_attr(node["a"], fk).get("n", "")
        except Exception:
            continue
        if os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
            videos.append({"id": node["h"], "name": name})

    return videos


def download_video(folder_url: str, node_id: str, dest_path: str):
    root_handle, key_b64, _ = _parse_url(folder_url)
    nodes = _fetch_nodes(root_handle)
    folder_key = _to_a32(_b64d(key_b64))

    node = next((n for n in nodes if n["h"] == node_id), None)
    if not node:
        raise RuntimeError(f"Node {node_id} not found in Mega folder.")

    fk = _file_key(node["k"], folder_key)
    file_url = f"https://mega.nz/file/{node_id}#{_b64e(_to_bytes(fk))}"

    m = Mega()
    m.login_anonymous()
    m.download_url(file_url, dest_path=os.path.dirname(dest_path), dest_filename=os.path.basename(dest_path))
