# LyricsTag

[Русский](README.md) | **English**

Documentation v1.4 (lyrics_tag.py v6, plugin lyrics_tag_pp.py v3)

Automatically embeds **synchronized lyrics** (karaoke-style, line by line) into the tags of downloaded tracks. It runs entirely on Android, no PC needed: once YTDLnis has downloaded a track, the lyrics are already inside the file, and your player shows them as the song plays.

Tested with Poweramp. The opus and mp3 (320 kbps) formats are verified on a device: lyrics, tags, cover art and sorting into folders all work.

It works together with [YTDLnis](https://github.com/deniscerri/ytdlnis) (an Android front end for yt-dlp) and requires neither a PC nor root.

## How it works

1. YTDLnis downloads the audio through yt-dlp.
2. After the download, yt-dlp calls the LyricsTag plugin (an `after_move` postprocessor).
3. The plugin runs `lyrics_tag.py` inside the yt-dlp process itself (no shell, no subprocess).
4. The script fetches lyrics from:
   - **YouTube Music** via the `ytmusicapi` library (the primary source; it first uses the videoId from the `purl` tag or from an `[id]` in the file name; if that id has no synchronized lyrics or is unknown, it runs a search, whose results are checked against the title and artist);
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

Tested with: YTDLnis 1.9.1.1 (arm64) with bundled yt-dlp 2026.08.19, Python 3.14, ytmusicapi 1.12.3.

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

In YTDLnis open "More" - "Command templates" and tap "New template". Pick any title (for example, "Lyrics to tags") and paste one of the three templates below into the "Command" field. Choose by the description; you can switch to another one later by replacing the text.

**Template 1. Lyrics only.** The simplest option: after a download, synchronized lyrics are written into the tags.

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --use-postprocessor "LyricsTag:when=after_move"
```

**Template 2. Lyrics and sorting into folders.** The same, plus the track is automatically moved into a folder named after the artist (see "Sorting into artist folders").

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --use-postprocessor "LyricsTag:when=after_move;sort=1"
```

**Template 3. Lyrics, sorting and clean artist names.** The same, plus only the first artist is kept in the file name and the tag: it removes songwriters and producers that YouTube Music adds to `artist` separated by commas (for example, `Artist, Songwriter Name` becomes `Artist`). Downside: genuine collaborations (`A, B`) also become `A` (details in "Troubleshooting").

```
-v --plugin-dirs "/sdcard/Documents/Scripts" --parse-metadata "%(uploader)s:^(?P<uploader>.*?)(?:(?=,\s+)|$)" --parse-metadata "%(uploader)s:%(artist)s" --use-postprocessor "LyricsTag:when=after_move;sort=1"
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

## mp3 and quality

YouTube serves only Opus and AAC; it has no ready-made mp3. When the mp3 container is selected in YTDLnis, the app downloads the original stream and converts it with ffmpeg (`--audio-format mp3`). The conversion happens before the plugin runs, so the plugin receives a finished mp3 and writes the lyrics into it (`SYLT` + `USLT`). Tags and cover art are preserved.

The mp3 bitrate is set separately. On the download card, in the "Audio settings" block, there is a "Bitrate" button (the row of buttons may be cut off on the right, so scroll it). Choose 320 kbps. If you leave the default, YTDLnis does not pass `--audio-quality`, and ffmpeg encodes the mp3 at its own default bitrate. Judging by the file size this is about 128 kbps, and the sound is noticeably worse than the original Opus.

You can set the same thing with a command in the template (`--audio-quality 0` gives VBR V0, about 245 kbps; `--audio-quality 320K` gives CBR 320).

Opus to mp3 is a lossy-to-lossy re-encode, so even a 320 kbps mp3 is not better than the source, and the file is larger (on the verified track 11.0 MB versus 8.8 MB for opus). Choose mp3 only if your player or device cannot read opus.

Verified on a device (YTDLnis 1.9.1.1): mp3 at 320 kbps CBR, 48 kHz, one `SYLT` (synchronized lyrics) and one `USLT` (plain), cover art and tags in place, sorting into folders works. Minor things you may notice are not caused by the plugin: a `COMM:ID3v1 Comment` with a truncated link (ID3v1 is limited to 30 bytes and yt-dlp writes it) and empty track and disc numbers (yt-dlp does not supply them).

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

**The mp3 sounds bad**
Most likely no bitrate was selected, so ffmpeg encodes the mp3 at about 128 kbps. Use the "Bitrate" button and pick 320 kbps (see "mp3 and quality").

**No `[LyricsTag]` lines in the log**
The plugin was not picked up. Check the `Post-Processor Plugins:` line in the log and the folder structure (see "Project structure"). Common causes: a wrong path in `--plugin-dirs`, or a stray `__init__.py`.

**No lyrics appeared, and the log says "уже есть текст, пропуск"**
That message means "lyrics already present, skipping": the file already contains lyrics. Use `force=1`.

## Limitations

- `ytmusicapi` uses an unofficial, internal YouTube Music API and may stop working if Google changes it.
- Tested on one device and one YTDLnis version, with the opus and mp3 formats. Writing to m4a and flac is implemented and was verified only on test files on a PC, not on a device with real tracks.
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
