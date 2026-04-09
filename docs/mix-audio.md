# mix-audio

Mixes multiple audio tracks from a media file into a single combined track. Preserves video streams when present. Auto-detects the number of audio streams.

**Source:** `scripts/media/mix-audio.sh`
**After install:** `mix-audio`

## Usage

```
mix-audio [options] <file|dir> [file|dir ...]
```

Output is written alongside the original: `<name>_mixed.<ext>`.

## Options

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | Show full ffmpeg output instead of progress line only |
| `-h`, `--help` | Show usage |

## Behavior

- Skips files with 0 or 1 audio streams (nothing to mix)
- Skips files whose name already ends in `_mixed`
- Skips if the output file already exists
- When given a directory, processes media files one level deep (non-recursive)
- Volume normalization is off (`normalize=0`); original levels are preserved

## Requirements

- `ffmpeg` and `ffprobe`

## Scenarios

**Mix a screen recording with separate mic and system audio tracks:**
```
mix-audio recording.mp4
# produces recording_mixed.mp4
```

**Process all recordings in a folder:**
```
mix-audio ~/recordings/
```

**Wildcard:**
```
mix-audio session_*.mp4
```

**Debug a failed mix:**
```
mix-audio -v recording.mp4
```

Typical use case: mixing mic and system audio from a screen or meeting recording before sending to MacWhisper for transcription.
