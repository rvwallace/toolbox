#!/usr/bin/env bash
#
# Mix multiple audio tracks from media files into a single track.
# Preserves video streams when present. Auto-detects stream count.
#
# Usage: mix-audio [options] <file|dir> [file|dir ...]

set -euo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
readonly MEDIA_EXTENSIONS=(mp4 mov mkv avi m4v m4a mp3 aac flac wav ogg webm)

VERBOSE=false

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options] <file|dir> [file|dir ...]

Mix multiple audio tracks from media files into a single combined track.
Preserves video streams when present. Auto-detects number of audio streams.
Skips files with fewer than 2 audio streams or already-mixed output files.

Arguments:
  file    Input audio or video file
  dir     Directory of media files (non-recursive)

Options:
  -v, --verbose    Show full ffmpeg output
  -h, --help       Show this help

Output:
  <name>_mixed.<ext> alongside the original file.

Examples:
  ${SCRIPT_NAME} recording.mp4
  ${SCRIPT_NAME} *.mp4
  ${SCRIPT_NAME} ~/recordings/
EOF
}

err() {
  echo "error: $*" >&2
}

check_dependencies() {
  local missing=()
  command -v ffmpeg  &>/dev/null || missing+=(ffmpeg)
  command -v ffprobe &>/dev/null || missing+=(ffprobe)
  if [[ ${#missing[@]} -gt 0 ]]; then
    err "missing required tools: ${missing[*]}"
    exit 1
  fi
}

is_media_file() {
  local file="$1"
  local ext="${file##*.}"
  ext="${ext,,}"
  local e
  for e in "${MEDIA_EXTENSIONS[@]}"; do
    [[ "$e" == "$ext" ]] && return 0
  done
  return 1
}

collect_files() {
  local item
  for item in "$@"; do
    if [[ -d "$item" ]]; then
      local f
      while IFS= read -r -d '' f; do
        is_media_file "$f" && printf '%s\n' "$f"
      done < <(find "$item" -maxdepth 1 -type f -print0 | sort -z)
    elif [[ -f "$item" ]]; then
      printf '%s\n' "$item"
    else
      err "not found: '$item'"
    fi
  done
}

mix_file() {
  local input="$1"
  local index="$2"
  local total="$3"
  local prefix="[${index}/${total}]"

  local filename ext base dir output
  filename="$(basename -- "$input")"
  ext="${filename##*.}"
  base="${filename%.*}"
  dir="$(dirname "$input")"
  output="${dir}/${base}_mixed.${ext}"

  # Skip already-mixed files
  if [[ "$base" == *_mixed ]]; then
    echo "${prefix} skip (already mixed): ${filename}"
    return 0
  fi

  # Skip if output already exists
  if [[ -f "$output" ]]; then
    echo "${prefix} skip (output exists): $(basename "$output")"
    return 0
  fi

  # Count audio streams
  local stream_count
  stream_count=$(ffprobe -v error -select_streams a \
    -show_entries stream=index -of csv=p=0 "$input" 2>/dev/null | wc -l | xargs)

  if [[ -z "$stream_count" || "$stream_count" -eq 0 ]]; then
    echo "${prefix} skip (no audio): ${filename}"
    return 0
  fi

  if [[ "$stream_count" -le 1 ]]; then
    echo "${prefix} skip (only 1 audio track): ${filename}"
    return 0
  fi

  # Check for video streams
  local video_count
  video_count=$(ffprobe -v error -select_streams v \
    -show_entries stream=index -of csv=p=0 "$input" 2>/dev/null | wc -l | xargs)

  echo "${prefix} mixing: ${filename} (${stream_count} audio streams)"

  # Build amix filter input labels
  local filter_inputs=""
  local i
  for (( i=0; i<stream_count; i++ )); do
    filter_inputs+="[0:a:${i}]"
  done

  local ffmpeg_args=(-i "$input"
    -filter_complex "${filter_inputs}amix=inputs=${stream_count}:duration=longest:normalize=0"
  )

  if [[ "$video_count" -gt 0 ]]; then
    ffmpeg_args+=(-c:v copy)
  fi

  ffmpeg_args+=("$output")

  if [[ "$VERBOSE" == true ]]; then
    ffmpeg "${ffmpeg_args[@]}"
  else
    ffmpeg -v quiet -stats "${ffmpeg_args[@]}"
  fi

  echo "${prefix} done: $(basename "$output")"
}

main() {
  [[ $# -eq 0 ]] && { usage; exit 0; }

  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -v|--verbose) VERBOSE=true ;;
      -h|--help)    usage; exit 0 ;;
      -*)           err "unknown option: $1"; exit 1 ;;
      *)            inputs+=("$1") ;;
    esac
    shift
  done

  [[ ${#inputs[@]} -eq 0 ]] && { err "no inputs specified"; exit 1; }

  check_dependencies

  local files=()
  while IFS= read -r f; do
    [[ -n "$f" ]] && files+=("$f")
  done < <(collect_files "${inputs[@]}")

  local total="${#files[@]}"
  if [[ "$total" -eq 0 ]]; then
    err "no media files found"
    exit 1
  fi

  echo "Found ${total} file(s)"

  local i
  for (( i=0; i<total; i++ )); do
    mix_file "${files[$i]}" "$((i+1))" "$total"
  done

  echo "Done."
}

main "$@"
