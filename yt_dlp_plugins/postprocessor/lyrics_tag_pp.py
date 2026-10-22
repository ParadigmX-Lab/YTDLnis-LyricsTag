"""
yt-dlp плагин-постпроцессор LyricsTag (v4).
Вызывает lyrics_tag.py прямо внутри процесса yt-dlp (без shell и subprocess, поэтому
работает там, где --exec падает).

Структура проекта (путь к lyrics_tag.py вычисляется от места плагина, переносить можно куда угодно):
  LyricsTag/
    lyrics_tag.py
    libs/                                   (ytmusicapi)
    yt_dlp_plugins/postprocessor/lyrics_tag_pp.py   (этот файл, без __init__.py)

Использование (доп. команда в YTDLnis, папка Scripts - родитель LyricsTag):
  --plugin-dirs "/sdcard/Documents/Scripts" --use-postprocessor "LyricsTag:when=after_move"
Необязательные параметры через ';' (включаются значением 1, true, yes или on):
  script=/путь/к/lyrics_tag.py  lrc_in_uslt=1  sidecar=1  force=1  sort=1
  sort=1 - после записи текста переложить трек в подпапку основного исполнителя
Неизвестный параметр (опечатка) не ломает загрузку: он игнорируется с предупреждением в логе.
"""
import importlib.util
import os
from argparse import Namespace

from yt_dlp.postprocessor.common import PostProcessor

# LyricsTag/yt_dlp_plugins/postprocessor/<этот файл> -> LyricsTag/lyrics_tag.py
DEFAULT_SCRIPT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'lyrics_tag.py'))


def _flag(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class LyricsTagPP(PostProcessor):
    def __init__(self, downloader=None, script=DEFAULT_SCRIPT, lrc_in_uslt='0', sidecar='0', force='0', sort='0',
                 **unknown):
        # **unknown: без него опечатка в параметре (например sotr=1) роняет весь yt-dlp с TypeError
        super().__init__(downloader)
        self._script = script
        self._unknown = sorted(unknown)
        self._mod = None  # скрипт загружается один раз на запуск yt-dlp
        self._args = Namespace(force=_flag(force), sidecar=_flag(sidecar),
                               lrc_in_uslt=_flag(lrc_in_uslt), no_yt=False,
                               sort=_flag(sort), sort_only=False)

    def _load(self):
        if self._mod is None:
            spec = importlib.util.spec_from_file_location('lyrics_tag_script', self._script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._mod = mod
        return self._mod

    def run(self, info):
        if self._unknown:
            self.report_warning('неизвестные параметры игнорируются: ' + ', '.join(self._unknown))
            self._unknown = []  # предупредить один раз
        # Любая ошибка здесь не должна ломать загрузку
        try:
            path = info.get('filepath') or info.get('_filename')
            if not path or not os.path.isfile(path):
                self.report_warning(f'файл не найден: {path}')
                return [], info
            mod = self._load()
            if os.path.splitext(path)[1].lower() not in mod.EXTS:
                self.to_screen('формат не поддерживается, пропуск')
                return [], info
            _, new_path = mod.process(path, self._args, self.to_screen)
            if new_path != path:
                info['filepath'] = new_path
        except Exception as e:  # noqa: BLE001
            self.report_warning(f'ошибка: {type(e).__name__}: {e}')
        return [], info
