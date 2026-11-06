#!/usr/bin/env bash
# experiments/video/make_video_content.sh   (Amrutha, Day 0 + Day 1)
#
# Builds the DASH test video exactly as in the Phase 1 work distribution:
# ONE manifest.mpd, 5 video renditions + 1 audio, 4 s segments, aligned keyframes, constant bitrate.
#
#   bash experiments/video/make_video_content.sh --test   # Day 0: 10 s, 2 renditions -> /tmp/video_test
#   bash experiments/video/make_video_content.sh          # Day 1: 120 s, 5 renditions -> experiments/video/content
#
# Afterwards run:  python3 experiments/video/check_video_content.py <content-dir> --duration <120|10>
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

MODE="${1:-full}"
if [[ "$MODE" == "--test" ]]; then
    DUR=10; OUT="${2:-/tmp/video_test}"; RENDITIONS=2
else
    DUR=120; OUT="${2:-experiments/video/content}"; RENDITIONS=5
fi

command -v ffmpeg >/dev/null || { echo "ffmpeg not found"; exit 1; }
ENC="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
[[ "$ENC" == *libx264* ]] || { echo "ffmpeg has no libx264"; exit 1; }

if [[ -e "$OUT/manifest.mpd" ]]; then
    echo "STOP: $OUT/manifest.mpd already exists. Delete the folder first if you really want to rebuild."
    exit 1
fi
mkdir -p "$OUT"
SRC="$OUT/../source_${DUR}s.mp4"
[[ "$MODE" == "--test" ]] && SRC="$OUT/source_${DUR}s.mp4"   # keep the test self-contained

# 1) source video: synthetic 720p / 25 fps + 440 Hz tone
if [[ ! -f "$SRC" ]]; then
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc=duration=${DUR}:size=1280x720:rate=25" \
        -f lavfi -i "sine=frequency=440:duration=${DUR}" \
        -c:v libx264 -c:a aac "$SRC"
fi

# 2) the ladder (bitrate, buffer size, size)
RATE=(250k 500k 1000k 2500k 5000k)
BUF=(500k 1000k 2000k 5000k 10000k)
SIZE=(426x240 640x360 854x480 1280x720 1280x720)

MAPS=(); for ((i=0;i<RENDITIONS;i++)); do MAPS+=(-map 0:v); done; MAPS+=(-map 0:a)
RATEOPTS=()
for ((i=0;i<RENDITIONS;i++)); do
    RATEOPTS+=(-b:v:$i "${RATE[$i]}" -minrate:v:$i "${RATE[$i]}" -maxrate:v:$i "${RATE[$i]}"
               -bufsize:v:$i "${BUF[$i]}" -s:v:$i "${SIZE[$i]}")
done

ffmpeg -hide_banner -loglevel error -stats -y -i "$SRC" \
    "${MAPS[@]}" \
    -c:v libx264 -preset veryfast -g 100 -keyint_min 100 -sc_threshold 0 \
    -x264-params nal-hrd=cbr:force-cfr=1 -c:a aac -b:a 64k \
    "${RATEOPTS[@]}" \
    -f dash -seg_duration 4 -use_template 1 -use_timeline 1 \
    -adaptation_sets "id=0,streams=v id=1,streams=a" \
    "$OUT/manifest.mpd"

echo "Done: $OUT/manifest.mpd"
echo "Next: python3 experiments/video/check_video_content.py $OUT --duration $DUR"
