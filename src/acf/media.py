from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path

VIDEO_EXTS = {".mp4",".mov",".mkv",".avi",".webm",".m4v"}
AUDIO_EXTS = {".wav",".mp3",".m4a",".aac",".flac",".ogg"}

def binary(env_name, default):
    return os.getenv(env_name) or shutil.which(default) or default

def discover(root):
    if root.is_file():
        return [root]
    allowed = VIDEO_EXTS | AUDIO_EXTS
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed)

def probe(path):
    cmd=[binary("FFPROBE_BIN","ffprobe"),"-v","error","-show_format","-show_streams","-of","json",str(path)]
    try:
        return json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True).stdout)
    except Exception as exc:
        return {"error":str(exc)}

def write_manifest(files,destination):
    manifest={"version":1,"files":[]}
    for path in files:
        manifest["files"].append({"path":str(path.resolve()),"name":path.name,"extension":path.suffix.lower(),"probe":probe(path)})
    destination.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest

def extract_audio(source,destination):
    cmd=[binary("FFMPEG_BIN","ffmpeg"),"-y","-i",str(source),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(destination)]
    try:
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        return True
    except Exception:
        return False

def make_proxy(source,destination,width=1280):
    cmd=[binary("FFMPEG_BIN","ffmpeg"),"-y","-i",str(source),"-vf",f"scale={width}:-2","-c:v","libx264","-preset","veryfast","-crf","28","-an",str(destination)]
    try:
        subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        return True
    except Exception:
        return False
