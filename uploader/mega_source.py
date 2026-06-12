import os
import re

from mega import Mega
from mega.crypto import a32_to_base64, base64_to_a32, decrypt_attr, decrypt_key

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}


def _parse_url(folder_url: str):
    # https://mega.nz/folder/ROOTHANDLE#KEY/folder/SUBHANDLE
    root_match = re.search(r"/folder/([^/#?]+)#([^/]+)", folder_url)
    if not root_match:
        raise ValueError(f"Invalid Mega folder URL: {folder_url}")
    root_handle = root_match.group(1)
    key_b64 = root_match.group(2)
    sub_match = re.search(r"#[^/]+/folder/([^/#?]+)", folder_url)
    subfolder_handle = sub_match.group(1) if sub_match else None
    return root_handle, key_b64, subfolder_handle


def _get_nodes(m: Mega, root_handle: str):
    return m._api_request([{"a": "f", "c": 1, "ca": 1, "r": 1}], root_handle)


def _node_file_key(node: dict, folder_key: tuple) -> tuple:
    k = node.get("k", "")
    if ":" in k:
        k = k.split(":")[1]
    enc_key = base64_to_a32(k)
    node_key = decrypt_key(enc_key, folder_key)
    if len(node_key) == 8:
        return (
            node_key[0] ^ node_key[4],
            node_key[1] ^ node_key[5],
            node_key[2] ^ node_key[6],
            node_key[3] ^ node_key[7],
        )
    return node_key[:4]


def list_videos(folder_url: str) -> list:
    root_handle, key_b64, subfolder_handle = _parse_url(folder_url)
    m = Mega().login_anonymous()
    response = _get_nodes(m, root_handle)
    folder_key = base64_to_a32(key_b64)
    target_parent = subfolder_handle or root_handle

    videos = []
    for node in response.get("f", []):
        if node.get("t") != 0 or node.get("p") != target_parent:
            continue
        try:
            file_key = _node_file_key(node, folder_key)
            attrs = decrypt_attr(node["a"], file_key)
            name = attrs.get("n", "")
        except Exception:
            continue
        if os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
            videos.append({"id": node["h"], "name": name})

    return videos


def download_video(folder_url: str, node_id: str, dest_path: str):
    root_handle, key_b64, _ = _parse_url(folder_url)
    m = Mega().login_anonymous()
    response = _get_nodes(m, root_handle)
    folder_key = base64_to_a32(key_b64)

    node = next((n for n in response.get("f", []) if n["h"] == node_id), None)
    if not node:
        raise RuntimeError(f"Node {node_id} not found in Mega folder.")

    file_key = _node_file_key(node, folder_key)
    file_key_b64 = a32_to_base64(file_key)
    file_url = f"https://mega.nz/file/{node_id}#{file_key_b64}"

    dest_dir = os.path.dirname(dest_path)
    dest_filename = os.path.basename(dest_path)
    m.download_url(file_url, dest_path=dest_dir, dest_filename=dest_filename)
