#!/usr/bin/env python3
"""
lyrics_tag.py (v7) - добавляет текст песни (синхронный или обычный) в теги mp3/opus/ogg/flac/m4a
и (по желанию) раскладывает треки по папкам основного исполнителя.

Источники по порядку:
  1. YouTube Music (ytmusicapi): сначала videoId из тега purl/comment или имени файла [id];
     поиск выполняется только если по этому id нет синхронного текста (или id неизвестен)
  2. LRCLIB (только stdlib), по artist/title/duration

Зависимости: pip install mutagen ytmusicapi
Использование:
  python lyrics_tag.py PATH [PATH ...] [--force] [--sidecar] [--lrc-in-uslt] [--no-yt] [--sort | --sort-only]
  --sort       после текста переложить трек в ПАПКА_PATH/<основной исполнитель>/
  --sort-only  только разложить по папкам, текст не трогать (сеть не нужна)
"""
import argparse
import json
import os
import re
import shutil
import ssl
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

# папка libs рядом со скриптом: туда ставится ytmusicapi (переживает сброс пакетов YTDLnis)
_LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.append(_LIBS)

import mutagen
from mutagen.id3 import ID3, ID3NoHeaderError, SYLT, USLT

EXTS = {".mp3", ".opus", ".ogg", ".flac", ".m4a"}
ID_RE = re.compile(r"(?:v=|youtu\.be/|/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
NAME_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
UA = "LyricsTag/7 (https://github.com/ParadigmX-Lab/YTDLnis-LyricsTag)"  # LRCLIB просит указывать проект
LRC_RE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|;|\sfeat\.?\s|\sft\.?\s|\sfeaturing\s)\s*", re.I)
BAD_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ---------- чтение метаданных файла ----------

def first(v):
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else ""
    return str(v) if v is not None else ""


def read_info(path):
    """Возвращает dict: artist, title, duration, video_id, has_lyrics."""
    ext = os.path.splitext(path)[1].lower()
    f = mutagen.File(path)
    if f is None:
        raise ValueError("формат не распознан")
    info = {"artist": "", "title": "", "duration": f.info.length, "video_id": None,
            "has_lyrics": False}
    candidates = []
    if ext == ".mp3":
        try:
            t = ID3(path)
        except ID3NoHeaderError:
            t = ID3()
        info["artist"] = first(t.get("TPE1")) if t.get("TPE1") else ""
        info["title"] = first(t.get("TIT2")) if t.get("TIT2") else ""
        info["has_lyrics"] = bool(t.getall("USLT") or t.getall("SYLT"))
        for key in t.keys():
            if key.startswith("TXXX:purl") or key.startswith("COMM") or key.startswith("WXXX"):
                candidates.append(first(getattr(t[key], "text", getattr(t[key], "url", ""))))
    elif ext == ".m4a":
        t = f.tags or {}
        info["artist"] = first(t.get("\xa9ART"))
        info["title"] = first(t.get("\xa9nam"))
        info["has_lyrics"] = bool(t.get("\xa9lyr"))
        candidates += [first(t.get("\xa9cmt")), first(t.get("purl"))]
    else:  # vorbis comments: opus/ogg/flac
        t = f.tags or {}
        info["artist"] = first(t.get("artist"))
        info["title"] = first(t.get("title"))
        info["has_lyrics"] = bool(t.get("lyrics") or t.get("unsyncedlyrics"))
        candidates += [first(t.get("purl")), first(t.get("comment")), first(t.get("description"))]
    for c in candidates:
        m = ID_RE.search(c or "")
        if m and ("youtu" in c):
            info["video_id"] = m.group(1)
            break
    if not info["video_id"]:
        m = NAME_ID_RE.search(os.path.basename(path))
        if m:
            info["video_id"] = m.group(1)
    if not info["title"]:
        info["title"] = os.path.splitext(os.path.basename(path))[0]
    return info


# ---------- источники текста ----------
# Результат: (lines, plain) где lines = [(ms, text), ...] или None, plain = str или None

def parse_lrc(lrc):
    out = []
    for raw in lrc.splitlines():
        m = LRC_RE.match(raw.strip())
        if m:
            out.append((int((int(m.group(1)) * 60 + float(m.group(2))) * 1000), m.group(3).strip()))
    return out


def _norm(s):
    s = re.sub(r"[(\[].*?[)\]]", " ", s or "")  # убрать (feat. ...), [Remix] и т.п.
    return re.sub(r"[\W_]+", "", s.casefold())


def _same_track(info, r):
    """Результат поиска YT Music должен совпасть по названию и (если известен) по исполнителю."""
    t, rt = _norm(info["title"]), _norm(r.get("title"))
    if not t or not rt or not (t == rt or (min(len(t), len(rt)) >= 4 and (t in rt or rt in t))):
        return False
    wanted = [_norm(a) for a in ARTIST_SPLIT_RE.split(info["artist"] or "") if _norm(a)]
    if not wanted:
        return True
    have = [_norm(a.get("name")) for a in (r.get("artists") or []) if isinstance(a, dict)]
    return any(w == h or (min(len(w), len(h)) >= 3 and (w in h or h in w))
               for w in wanted for h in have)


def from_ytmusic(info, log):
    try:
        from ytmusicapi import YTMusic
    except Exception as e:  # noqa: BLE001  (ImportError и любые ошибки при импорте)
        log(f"  YT Music пропущен: не импортируется ytmusicapi: {type(e).__name__}: {e}")
        log("  mutagen из: " + str(getattr(mutagen, "__file__", "?")))
        log("  sys.path: " + " | ".join(sys.path))
        for tb_line in traceback.format_exc().splitlines()[-8:]:
            log("  " + tb_line)
        return None
    yt = YTMusic()
    tried = set()
    plain_fallback = None

    def fetch(vid):
        """(lines, plain) для одного videoId: lines=None - только обычный текст; None - текста нет."""
        try:
            browse_id = yt.get_watch_playlist(videoId=vid).get("lyrics")
            if not browse_id:
                return None
            data = yt.get_lyrics(browse_id, timestamps=True)
        except Exception as e:  # noqa: BLE001
            log(f"  {vid}: ошибка {e}")
            return None
        if not data:
            return None
        if data.get("hasTimestamps"):
            lines = []
            for l in data["lyrics"]:
                text = l["text"] if isinstance(l, dict) else l.text
                start = l["start_time"] if isinstance(l, dict) else l.start_time
                lines.append((int(start), text))
            log(f"  YT Music: синхронный текст ({vid})")
            return lines, "\n".join(t for _, t in lines)
        if data.get("lyrics"):
            return None, data["lyrics"]
        return None

    def try_ids(ids):
        """Первый синхронный результат; обычный текст запоминается как запасной."""
        nonlocal plain_fallback
        for vid in ids:
            if vid in tried:
                continue
            tried.add(vid)
            res = fetch(vid)
            if res is None:
                continue
            if res[0] is not None:
                return res
            if plain_fallback is None:
                plain_fallback = res
        return None

    # 1. videoId из тегов/имени файла: если по нему есть синхронный текст, поиск не нужен
    if info["video_id"]:
        res = try_ids([info["video_id"]])
        if res:
            return res
    # 2. поиск: только когда по известному id синхронного текста нет (или id неизвестен)
    ids = []
    q = f'{info["artist"]} {info["title"]}'.strip()
    try:
        for r in yt.search(q, filter="songs", limit=5):
            vid = r.get("videoId")
            d = r.get("duration_seconds")
            if not vid or vid in ids or vid == info["video_id"]:
                continue
            if d is not None and abs(d - info["duration"]) > 4:
                continue
            if not _same_track(info, r):
                log(f"  поиск: пропущен {vid} ({r.get('title')}) - не совпадает название/исполнитель")
                continue
            ids.append(vid)
    except Exception as e:  # noqa: BLE001
        log(f"  поиск YT Music не удался: {e}")
    res = try_ids(ids)
    if res:
        return res
    if plain_fallback:
        log("  YT Music: только обычный текст")
    return plain_fallback


def _ssl_context():
    """Контекст TLS с CA-списком certifi.
    Python в YTDLnis (Android) не находит системное хранилище сертификатов, и urllib падает с
    CERTIFICATE_VERIFY_FAILED; certifi (он есть в окружении yt-dlp) решает это без отключения проверки."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001  (нет certifi - используем стандартное поведение)
        return None


def from_lrclib(info, log):
    params = {"artist_name": info["artist"], "track_name": info["title"],
              "duration": int(round(info["duration"]))}
    url = "https://lrclib.net/api/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    d = None
    ctx = _ssl_context()
    for attempt in range(3):  # LRCLIB иногда отвечает 5xx, пробуем еще раз
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log("  LRCLIB: трек не найден (404)")
                return None
            log(f"  LRCLIB: {e} (попытка {attempt + 1}/3)")
        except Exception as e:  # noqa: BLE001
            if isinstance(getattr(e, "reason", e), ssl.SSLError):  # повторы не помогут
                log(f"  LRCLIB: ошибка проверки сертификата, источник пропущен: {e}")
                return None
            log(f"  LRCLIB: {type(e).__name__}: {e} (попытка {attempt + 1}/3)")
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    if d is None:
        return None
    if d.get("instrumental"):
        log("  LRCLIB: инструментал")
        return None
    if d.get("syncedLyrics"):
        lines = parse_lrc(d["syncedLyrics"])
        if lines:
            log("  LRCLIB: синхронный текст")
            return lines, "\n".join(t for _, t in lines)
    if d.get("plainLyrics"):
        log("  LRCLIB: только обычный текст")
        return None, d["plainLyrics"]
    return None


# ---------- запись тегов ----------

def to_lrc(lines):
    out = []
    for ms, text in lines:
        cs = int(round(ms / 10.0))  # сотые доли секунды; так не получится "59.996" -> "60.00"
        m, rem = divmod(cs, 6000)
        out.append(f"[{m:02d}:{rem // 100:02d}.{rem % 100:02d}] {text}")
    return "\n".join(out)


def write_tags(path, lines, plain, lrc_in_uslt):
    ext = os.path.splitext(path)[1].lower()
    lrc = to_lrc(lines) if lines else None
    if ext == ".mp3":
        try:
            t = ID3(path)
        except ID3NoHeaderError:
            t = ID3()
        t.delall("USLT")
        t.delall("SYLT")
        t.add(USLT(encoding=3, lang="XXX", desc="", text=lrc if (lrc and lrc_in_uslt) else plain))
        if lines:
            t.add(SYLT(encoding=3, lang="XXX", format=2, type=1, desc="",
                       text=[(text, ms) for ms, text in lines]))
        t.save(path, v2_version=3)
    elif ext == ".m4a":
        f = mutagen.File(path)
        f["\xa9lyr"] = [lrc or plain]
        f.save()
    else:  # opus/ogg/flac: Vorbis comment, LRC-текст внутри LYRICS (его понимает большинство плееров)
        f = mutagen.File(path)
        f["lyrics"] = [lrc or plain]
        f.save()


def add_lyrics(path, args, log):
    log(f"{os.path.basename(path)}")
    info = read_info(path)
    if info["has_lyrics"] and not args.force:
        log("  уже есть текст, пропуск (--force чтобы перезаписать)")
        return False
    res = None
    if not args.no_yt:
        res = from_ytmusic(info, log)
    if res is None or res[0] is None:  # нет синхро в YT Music - пробуем LRCLIB
        alt = from_lrclib(info, log)
        if alt and (res is None or alt[0] is not None):
            res = alt
    if res is None:
        log("  текст не найден")
        return False
    lines, plain = res
    write_tags(path, lines, plain, args.lrc_in_uslt)
    if args.sidecar and lines:
        with open(os.path.splitext(path)[0] + ".lrc", "w", encoding="utf-8") as fh:
            fh.write(to_lrc(lines) + "\n")
    log("  записано: " + ("синхронный" if lines else "обычный") + " текст")
    return True


# ---------- сортировка по папкам исполнителя ----------

def main_artist(artist):
    """Основной исполнитель: первый из списка 'A, B feat. C' (без ' - Topic')."""
    a = re.sub(r"\s*-\s*Topic$", "", artist or "", flags=re.I).strip()
    return ARTIST_SPLIT_RE.split(a)[0].strip()


def safe_dirname(name):
    n = BAD_CHARS_RE.sub("_", name).strip(" .")
    return n[:80].rstrip(" .")


def sort_into_artist_dir(path, root, log):
    """Переносит файл (и .lrc рядом) в root/<основной исполнитель>/. Возвращает новый путь."""
    artist = safe_dirname(main_artist(read_info(path)["artist"]))
    if not artist:
        log("  сортировка: исполнитель не указан, пропуск")
        return path
    dest_dir = os.path.join(root, artist)
    if os.path.basename(os.path.dirname(os.path.abspath(path))).casefold() == artist.casefold():
        return path  # уже лежит в папке исполнителя (не создавать Исполнитель/Исполнитель)
    if os.path.abspath(os.path.dirname(path)) == os.path.abspath(dest_dir):
        return path
    dest = os.path.join(dest_dir, os.path.basename(path))
    if os.path.exists(dest):
        log(f"  сортировка: {artist}/{os.path.basename(path)} уже существует, пропуск")
        return path
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(path, dest)
    lrc = os.path.splitext(path)[0] + ".lrc"
    if os.path.isfile(lrc):
        shutil.move(lrc, os.path.join(dest_dir, os.path.basename(lrc)))
    log(f"  перемещено в: {artist}/")
    return dest


def process(path, args, log, root=None):
    """Возвращает (текст_записан, итоговый_путь). root - папка, внутри которой создаются папки исполнителей."""
    sort_only = getattr(args, "sort_only", False)
    wrote = False
    if sort_only:
        log(f"{os.path.basename(path)}")
    else:
        wrote = add_lyrics(path, args, log)
    new_path = path
    if sort_only or getattr(args, "sort", False):
        new_path = sort_into_artist_dir(path, root or os.path.dirname(os.path.abspath(path)), log)
    return wrote, new_path


def iter_files(paths):
    """Отдает (файл, корневая папка для сортировки)."""
    for p in paths:
        if os.path.isdir(p):
            for r, _, files in os.walk(p):
                for n in sorted(files):
                    if os.path.splitext(n)[1].lower() in EXTS:
                        yield os.path.join(r, n), p
        elif os.path.splitext(p)[1].lower() in EXTS:
            yield p, os.path.dirname(os.path.abspath(p))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--force", action="store_true", help="перезаписать существующий текст")
    ap.add_argument("--sidecar", action="store_true", help="дополнительно сохранить .lrc рядом с файлом")
    ap.add_argument("--lrc-in-uslt", action="store_true",
                    help="mp3: класть LRC-текст в USLT (для плееров, не читающих SYLT)")
    ap.add_argument("--no-yt", action="store_true", help="не использовать YT Music, только LRCLIB")
    ap.add_argument("--sort", action="store_true", help="переложить трек в папку основного исполнителя")
    ap.add_argument("--sort-only", action="store_true", help="только сортировка по папкам, без текста")
    args = ap.parse_args()
    log = lambda s: print(s, flush=True)  # noqa: E731
    ok = moved = total = 0
    for f, root in list(iter_files(args.paths)):
        total += 1
        try:
            wrote, new = process(f, args, log, root)
            ok += bool(wrote)
            moved += new != f
        except Exception as e:  # noqa: BLE001
            log(f"  ОШИБКА: {e}")
    if args.sort or args.sort_only:
        log(f"Готово: текст {ok}/{total}, перемещено {moved}")
    else:
        log(f"Готово: {ok}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
