# LyricsTag

[Русский](README.md) | **English**

Documentation v1.1 (lyrics_tag.py v4, plugin lyrics_tag_pp.py v3)

Automatically embeds **synchronized lyrics** (karaoke-style, line by line) into the tags of downloaded tracks. It runs entirely on Android, no PC needed: once YTDLnis has downloaded a track, the lyrics are already inside the file, and your player shows them as the song plays.

Tested with Poweramp and the opus format.

It works together with [YTDLnis](https://github.com/deniscerri/ytdlnis) (an Android front end for yt-dlp) and requires neither a PC nor root.

## How it works

1. YTDLnis downloads the audio through yt-dlp.
2. After the download, yt-dlp calls the LyricsTag plugin (an `after_move` postprocessor).
3. The plugin runs `lyrics_tag.py` inside the yt-dlp process itself (no shell, no subprocess).
4. The script fetches lyrics from:
   - **YouTube Music** via the `ytmusicapi` library (the primary source; the videoId is taken from the `purl` tag, from an `[id]` in the file name, or from a search);
   - **LRCLIB** (the fallback, used only if YouTube Music has no synchronized lyrics or could not be queried).
5. The lyrics are written into the file's tags.

Where the lyrics are stored:

| Format | Location |
|---|---|
| opus, ogg, flac | `LYRICS` tag (text in LRC format) |
| mp3 | `SYLT` (synchronized) + `USLT` (plain) |
| m4a | `©lyr` tag |

If a file already contains lyrics, it is skipped (to overwrite, use `force=1` or `--force`).

## Requirements

- An Android device with the **YTDLnis** app (it must provide a built-in terminal with Python and pip)
- A file manager
- A player that can read embedded LRC lyrics (Poweramp is tested)

Tested with: YTDLnis with bundled yt-dlp 2026.08.19, Python 3.14, ytmusicapi 1.12.3.

## Project structure

```
/storage/emulated/0/Documents/Scripts/LyricsTag/
  README.md
  README.en.md
  LICENSE
  lyrics_tag.py
  libs/                                  (ytmusicapi gets installed here; not part of the repository)
  yt_dlp_plugins/postprocessor/lyrics_tag_pp.py
```

Important:
- do not rename the `yt_dlp_plugins` and `postprocessor` folders, or yt-dlp will not find the plugin;
- do **not** add `__init__.py` files to them, they break plugin loading;
- the plugin locates `lyrics_tag.py` on its own (the path is resolved relative to the plugin), and the script adds `libs` to its import path automatically if the folder sits next to it.

## Installation

**1. Copy the project folder**

Download the repository ("Code" - "Download ZIP"), unpack it, and put the folder into `/storage/emulated/0/Documents/Scripts/` using a file manager. Name the folder `LyricsTag` (after a ZIP download it has a different name, for example `LyricsTag-main`). yt-dlp does not care about the folder name, but every path in this guide assumes `LyricsTag`.

**2. Install ytmusicapi in the YTDLnis terminal**

In YTDLnis open "More" - "Terminal" and run the command below. Use the YTDLnis terminal, not Termux: they have different Python installations.

```bash
pip install --no-deps --target /sdcard/Documents/Scripts/LyricsTag/libs ytmusicapi
```

The library is installed into the project folder rather than into the YTDLnis packages because YTDLnis may reset its own packages (for example, on update), and anything installed by hand would be lost. `--no-deps` avoids pulling in copies of `requests` and other libraries that YTDLnis already ships.

**3. Add a command template in YTDLnis**

In YTDLnis open "More" - "Command templates" and tap "New template". Pick any title (for example, "Lyrics to tags") and paste this into the "Command" field:

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --use-postprocessor "LyricsTag:when=after_move"
```

Below that, turn on the "Extra command" switch and tick "Audio" (leave "Video" unticked). Leave everything else as is and tap "Save" (when editing an existing template the button is called "Update"). From now on the command is added to every audio download.

The menu item names above are given as in the Russian version of YTDLnis and may differ slightly in other languages or versions.

The path in `--plugin-dirs` is the folder that contains `LyricsTag` (that is, `Scripts`, not `LyricsTag` itself).

## Verification

Download one track and open the log: "More" - "Logs". You need to see two things.

Near the beginning of the log:

```
[debug] Post-Processor Plugins: LyricsTagPP
```

At the end of the log:

```
[LyricsTag] <file name>
[LyricsTag]   YT Music: синхронный текст (<videoId>)
[LyricsTag]   записано: синхронный текст
```

The plugin's own messages are in Russian: "синхронный текст" means "synchronized lyrics" and "записано" means "written".

If the log shows garbled characters instead of Cyrillic (`Ð·Ð°Ð¿Ð¸ÑÐ°Ð½Ð¾`), that is only a display issue of the log viewer; the files and tags are fine.

## Plugin options

Options are appended after `when=after_move`, separated by `;`:

```
--use-postprocessor "LyricsTag:when=after_move;sidecar=1;lrc_in_uslt=1"
```

| Option | Effect |
|---|---|
| `force=1` | overwrite lyrics that are already present |
| `sidecar=1` | also save a `.lrc` file next to the track |
| `lrc_in_uslt=1` | mp3: put the LRC text into `USLT` (for players that cannot read `SYLT`) |
| `sort=1` | after writing the lyrics, move the track into a subfolder named after the main artist (see the section below) |
| `script=/path/to/lyrics_tag.py` | use the script from a different location |

## Manual run (for tracks you already have)

In the YTDLnis terminal ("More" - "Terminal"):

```bash
python /sdcard/Documents/Scripts/LyricsTag/lyrics_tag.py "/storage/emulated/0/Music/YT Music"
```

You can pass a folder or individual files. Flags: `--force`, `--sidecar`, `--lrc-in-uslt`, `--no-yt` (skip YouTube Music, use LRCLIB only), `--sort` (after the lyrics, sort tracks into artist folders), `--sort-only` (only sort into folders, leave lyrics alone, no internet needed).

It also works in Termux if `mutagen` and `ytmusicapi` are installed there:

```bash
pip install mutagen ytmusicapi
```

## Sorting into artist folders

Off by default. The track is moved into a subfolder named after the **main artist** (the first entry in the `artist` tag), and a `.lrc` file next to it moves along.

How the main artist is determined:
- `Artem Pivovarov, Klavdia Petrivna` - folder `Artem Pivovarov`
- `Artist feat. Other` - folder `Artist`
- `Some Band - Topic` - folder `Some Band`
- `Artist; Other` - folder `Artist`
- characters that are not allowed in folder names are replaced with `_` (`AC/DC` - folder `AC_DC`)
- if no artist is set, the track stays where it is

Known limitation: the list is split at commas, so `Tyler, The Creator` ends up in the folder `Tyler`.

The folder name comes from the `artist` tag. If the tag contains extra names (for example, YouTube Music added a songwriter or producer), only the first name is used for the folder, but the tag and the file name still contain the extras: this comes from yt-dlp's metadata, not from the plugin. See "Troubleshooting" for how to remove them.

**Automatically after download** (add `sort=1` to the template):

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --use-postprocessor "LyricsTag:when=after_move;sort=1"
```

The artist folder is created inside the folder where the plugin finds the track. The plugin updates the file path inside yt-dlp itself, so YTDLnis sees the track already in the artist folder (tested with YTDLnis and yt-dlp 2026.08.19: "Location", "Open file" and the download history all work). It has not been tested with other versions: if it does not work for you, remove `sort=1` and use the manual run below.

**Manually for tracks you already have** (in the YTDLnis terminal):

```bash
python /sdcard/Documents/Scripts/LyricsTag/lyrics_tag.py "/storage/emulated/0/Music" --sort-only
```

Artist subfolders are created inside the given folder and tracks are moved into them, including tracks that currently sit in other subfolders. For the first run, point it at a small folder with copies of your tracks.

## Moving to another phone

1. Copy the `LyricsTag` folder to `Documents/Scripts/` on the new phone.
2. Repeat installation step 2 (the library in `libs`).
3. Repeat installation step 3 (the template in YTDLnis).

If the folder is somewhere else, change the path in `--plugin-dirs` (it must point to the folder that contains `LyricsTag`).

## Troubleshooting

**`No module named 'ytmusicapi'` in the log**
The `libs` folder is missing or empty. Repeat installation step 2.

**`LRCLIB: ... 503` in the log**
The fallback service is temporarily unavailable. The script retries up to 3 times on its own.

**`LRCLIB: трек не найден (404)` and `текст не найден` in the log**
These mean "track not found" and "lyrics not found": neither YouTube Music nor LRCLIB has lyrics for this track. This happens with lesser-known tracks.

**Extra names in the file name and the artist tag (for example, `Artist, Songwriter Name - song.opus`)**
YouTube Music returns not only the performers but also songwriters and producers in its artist list, and YTDLnis joins the whole list with commas. The plugin is not involved. To keep only the first name, add two yt-dlp options to the command template before `--use-postprocessor`:

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --parse-metadata "%(uploader)s:^(?P<uploader>.*?)(?:(?=,\s+)|$)" --parse-metadata "%(uploader)s:%(artist)s" --use-postprocessor "LyricsTag:when=after_move;sort=1"
```

The first option cuts the artist down to the first name (which ends up in the file name), the second copies it into the `artist` tag. Tested on a single track with YTDLnis and yt-dlp 2026.08.19. Side effect: genuine collaborations (`A, B`) also become `A`, and `Tyler, The Creator` becomes `Tyler`.

**No `[LyricsTag]` lines in the log**
The plugin was not picked up. Check the `Post-Processor Plugins:` line in the log and the folder structure (see "Project structure"). Common causes: a wrong path in `--plugin-dirs`, or a stray `__init__.py`.

**No lyrics appeared, and the log says "уже есть текст, пропуск"**
That message means "lyrics already present, skipping": the file already contains lyrics. Use `force=1`.

## Limitations

- `ytmusicapi` uses an unofficial, internal YouTube Music API and may stop working if Google changes it.
- Tested on one device and one YTDLnis version, with the opus format. Writing to mp3, m4a and flac is implemented and was verified only on test files on a PC, not on a device with real tracks.
- There is no guarantee that every track has synchronized lyrics.
- Song lyrics belong to their rights holders. The script only writes what YouTube Music and LRCLIB return into the tags of your own personal files; it does not store or distribute lyrics anywhere.
- This project is not affiliated with YouTube, Google, YTDLnis, yt-dlp or LRCLIB.

## Acknowledgements

- [YTDLnis](https://github.com/deniscerri/ytdlnis) and [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ytmusicapi](https://github.com/sigma67/ytmusicapi)
- [mutagen](https://github.com/quodlibet/mutagen)
- [LRCLIB](https://lrclib.net)

## License

[MIT](LICENSE): you may freely use, modify and distribute this software, including in your own projects, as long as the license text and the author's name are kept. The software is provided "as is", without warranty of any kind.
