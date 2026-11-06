#!/bin/zsh
# Prepend a channel intro to an episode with a short crossfade (video + audio). CPU only.
# Usage: add_intro.sh <intro.mp4> <episode.mp4> <out.mp4>
# The intro is scaled to the EPISODE's resolution (never the other way round).
set -e
INTRO=$1; EP=$2; OUT=$3; XF=0.3
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$INTRO")
OFF=$(python3 -c "print(round($D - $XF, 3))")
WH=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$EP"); W=${WH%x*}; H=${WH#*x}
# an intro without sound gets silence of the same length, so the crossfade still has two audio streams
A0="[0:a]"; SILENT=()
if [[ -z $(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$INTRO") ]]; then
  SILENT=(-f lavfi -t "$D" -i anullsrc=r=48000:cl=stereo); A0="[2:a]"
fi
ffmpeg -y -loglevel error -i "$INTRO" -i "$EP" "${SILENT[@]}" -filter_complex "\
[0:v]fps=24,scale=${W}:${H}:flags=lanczos,format=yuv420p,setsar=1,settb=AVTB[v0];[1:v]fps=24,scale=${W}:${H},format=yuv420p,setsar=1,settb=AVTB[v1];\
[v0][v1]xfade=transition=fade:duration=${XF}:offset=${OFF}[v];\
${A0}aresample=48000,aformat=channel_layouts=stereo[a0];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];\
[a0][a1]acrossfade=d=${XF}[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart "$OUT" \
&& echo "wrote $OUT ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")s)"
