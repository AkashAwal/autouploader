import os
import re
import shutil

from mega import Mega

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}


def _login(email: str, password: str):
    return Mega().login(email, password)


def _parse_folder_node(folder_url: str) -> str:
    # Extract the subfolder node ID from URLs like:
    # https://mega.nz/folder/XXXXXXXX#KEY/folder/NODEID
    match = re.search(r"/folder/([^/#?]+)$", folder_url)
    if match:
        return match.group(1)
    # Fall back to root folder ID
    match = re.search(r"/folder/([^/#?]+)", folder_url)
    return match.group(1) if match else None


def list_videos(email: str, password: str, folder_url: str) -> list:
    m = _login(email, password)
    folder_node = _parse_folder_node(folder_url)
    all_files = m.get_files()

    videos = []
    for node_id, node in all_files.items():
        if node.get("t") != 0:  # t=0 is a file
            continue
        if node.get("p") != folder_node:
            continue
        attrs = node.get("a") or {}
        name = attrs.get("n", "")
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            videos.append({"id": node_id, "name": name})

    return videos


def download_video(email: str, password: str, node_id: str, dest_path: str):
    m = _login(email, password)
    all_files = m.get_files()
    node = all_files.get(node_id)
    if not node:
        raise RuntimeError(f"Mega node {node_id} not found.")

    dest_dir = os.path.dirname(dest_path)
    dest_filename = os.path.basename(dest_path)
    downloaded = m.download(node, dest_path=dest_dir, dest_filename=dest_filename)
    return downloaded
