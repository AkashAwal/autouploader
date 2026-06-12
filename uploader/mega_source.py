import base64
import json
import os
import re
import struct
import time

import requests as _requests
from Crypto.Cipher import AES
from Crypto.Util import Counter

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}
_SEQ = int(time.time()) % 100000


def _b64d(s):
    s = str(s) + '=='
    return base64.b64decode(s.translate(str.maketrans('-_', '+/')))


def _to_a32(b):
    if isinstance(b, str):
        b = b.encode('latin-1')
    b += b'\0' * (-len(b) % 4)
    return struct.unpack('>%dI' % (len(b) // 4), b)


def _to_bytes(a):
    return struct.pack('>%dI' % len(a), *a)


def _decrypt_attr(data: str, key: tuple) -> dict:
    k = _to_bytes(key[:4])
    raw = _b64d(data)
    cipher = AES.new(k, AES.MODE_CBC, b'\0' * 16)
    decrypted = cipher.decrypt(raw)
    match = re.search(rb'\{.+\}', decrypted)
    return json.loads(match.group().decode('utf-8'))


def _ecb_decrypt(data: bytes, key: bytes) -> bytes:
    out = b''
    cipher = AES.new(key, AES.MODE_ECB)
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        if len(block) == 16:
            out += cipher.decrypt(block)
    return out


def _decode_node_key(k_str: str, folder_key: tuple) -> tuple:
    if ':' in k_str:
        k_str = k_str.split(':')[1]
    dec = _to_a32(_ecb_decrypt(_b64d(k_str), _to_bytes(folder_key)))
    return dec


def _file_key(k_str: str, folder_key: tuple) -> tuple:
    dec = _decode_node_key(k_str, folder_key)
    if len(dec) >= 8:
        return (dec[0] ^ dec[4], dec[1] ^ dec[5], dec[2] ^ dec[6], dec[3] ^ dec[7])
    return dec[:4]


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

    candidates = [n for n in nodes if n.get("t") == 0 and n.get("p") == target_parent]

    videos = []
    for node in candidates:
        try:
            fk = _file_key(node["k"], folder_key)
            name = _decrypt_attr(node["a"], fk).get("n", "")
        except Exception:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            videos.append({"id": node["h"], "name": name})

    return videos


def download_video(folder_url: str, node_id: str, dest_path: str):
    root_handle, key_b64, _ = _parse_url(folder_url)
    nodes = _fetch_nodes(root_handle)
    folder_key = _to_a32(_b64d(key_b64))

    node = next((n for n in nodes if n["h"] == node_id), None)
    if not node:
        raise RuntimeError(f"Node {node_id} not found in Mega folder.")

    dec = _decode_node_key(node["k"], folder_key)
    if len(dec) < 8:
        raise RuntimeError("File key too short")

    aes_key = _to_bytes((dec[0]^dec[4], dec[1]^dec[5], dec[2]^dec[6], dec[3]^dec[7]))
    iv_int = int.from_bytes(_to_bytes((dec[4], dec[5], 0, 0)), 'big')

    # Get download URL from Mega API
    url_api = f"https://g.api.mega.co.nz/cs?id={_SEQ}&n={root_handle}"
    resp = _requests.post(url_api, json=[{"a": "g", "g": 1, "n": node_id}], timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if isinstance(result, int):
        raise RuntimeError(f"Mega API error: {result}")
    if isinstance(result[0], int):
        raise RuntimeError(f"Mega download error: {result[0]}")
    dl_url = result[0]["g"]

    # Stream download with AES-128-CTR decryption
    ctr = Counter.new(128, initial_value=iv_int)
    cipher = AES.new(aes_key, AES.MODE_CTR, counter=ctr)

    with _requests.get(dl_url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(cipher.decrypt(chunk))
