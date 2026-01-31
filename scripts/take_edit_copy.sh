#!/usr/bin/env bash

# ─── CONFIG ─────────────────────────────────────────────────────────────────────

if [ -z "$XDG_PICTURES_DIR" ]; then
    XDG_PICTURES_DIR="$HOME/Pictures"
fi

SAVE_DIR="${XDG_PICTURES_DIR}/Screenshots"
mkdir -p "$SAVE_DIR"

DATE=$(date +"%Y-%m-%d_%H-%M-%S")
FILE_NAME="Screenshot_$DATE.png"
FILE_PATH="$SAVE_DIR/$FILE_NAME"
EDITED_PATH="${FILE_PATH%.*}_edited.png"
LOG_FILE="$SAVE_DIR/screenshot_log.txt"

# Watermark/Font Config
WATERMARK_TEXT="    blazepwn  "
FONT_NAME="Hack-Nerd-Font-Regular"
FONT_SIZE=30
FONT_COLOR="#6791c9"
BORDER_COLOR="#343637"

# ─── FUNCTIONS ──────────────────────────────────────────────────────────────────

log() {
    echo "$(date +"%Y-%m-%d %H:%M:%S"): $1" >> "$LOG_FILE"
}

print_help() {
    echo "Usage: $0 [full|region]"
    exit 1
}

# ─── CAPTURE ────────────────────────────────────────────────────────────────────

case "$1" in
    full)
        CAPTURE_CMD="grim"
        ;;
    region)
        CAPTURE_CMD="grim -g \"$(slurp)\""
        if [ -z "$CAPTURE_CMD" ]; then
            log "Region selection cancelled"
            exit 1
        fi
        ;;
    *)
        print_help
        ;;
esac

# Execute Capture
eval $CAPTURE_CMD "$FILE_PATH" && log "Captured: $FILE_PATH" || {
    log "Error capturing screenshot"
    notify-send -a "Ax-Shell" "Screenshot Failed" "Could not capture screen."
    exit 1
}

# ─── PROCESSING ─────────────────────────────────────────────────────────────────

# Get dimensions
WIDTH=$(identify -format "%w" "$FILE_PATH")
HEIGHT=$(identify -format "%h" "$FILE_PATH")

# Defaults (Normal/Large)
RADIUS=20
SHADOW_GEOMETRY='100x40+0+16'
FONT_SIZE=30
ADD_WATERMARK=true

# Adaptive Logic
if [ "$WIDTH" -lt 150 ] || [ "$HEIGHT" -lt 150 ]; then
    # Tiny (Icon size)
    RADIUS=5
    SHADOW_GEOMETRY='40x10+0+20'
    ADD_WATERMARK=true
    FONT_SIZE=12
elif [ "$WIDTH" -lt 500 ] || [ "$HEIGHT" -lt 400 ]; then
    # Compact (Dialog/Small Window)
    RADIUS=10
    SHADOW_GEOMETRY='60x20+0+20'
    FONT_SIZE=15
    ADD_WATERMARK=true
fi

log "Dimensions: ${WIDTH}x${HEIGHT} -> Radius: $RADIUS, Shadow: $SHADOW_GEOMETRY, Watermark: $ADD_WATERMARK"

# 1. Round corners + Shadow effect
magick "$FILE_PATH" \
    \( +clone -alpha extract \
       -draw "fill black polygon 0,0 0,$RADIUS $RADIUS,0 fill white circle $RADIUS,$RADIUS $RADIUS,0" \
       \( +clone -flip \) -compose Multiply -composite \
       \( +clone -flop \) -compose Multiply -composite \
    \) -alpha off -compose CopyOpacity -composite \
    "$EDITED_PATH"

# 2. Add Depth Shadow
magick "$EDITED_PATH" \
    \( +clone -background black -shadow "$SHADOW_GEOMETRY" \) +swap \
    -background none -layers merge +repage \
    "$EDITED_PATH"

# 3. Add Border
magick "$EDITED_PATH" -bordercolor "$BORDER_COLOR" -border 0 "$EDITED_PATH"

# 4. Add Watermark (Functional)
if [ "$ADD_WATERMARK" = true ]; then
    # Ensure minimum width to prevent watermark cut-off
    CUR_W=$(identify -format "%w" "$EDITED_PATH")
    if [ "$CUR_W" -lt 150 ]; then
        magick "$EDITED_PATH" -background none -gravity south -extent 150x%[h] "$EDITED_PATH"
    fi

    echo -en "$WATERMARK_TEXT" | magick "$EDITED_PATH" -gravity South \
        -pointsize "$FONT_SIZE" -fill "$FONT_COLOR" -undercolor none \
        -font "$FONT_NAME" -annotate +0+15 @- \
        "$EDITED_PATH"
fi

log "Edited image saved: $EDITED_PATH"

# ─── CLIPBOARD ──────────────────────────────────────────────────────────────────

if command -v wl-copy >/dev/null 2>&1; then
    wl-copy < "$EDITED_PATH" && log "Copied to clipboard"
elif command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard -t image/png < "$EDITED_PATH" && log "Copied to clipboard"
else
    log "Clipboard tool not found"
fi

# ─── NOTIFICATION ───────────────────────────────────────────────────────────────

ACTION=$(notify-send -a "Ax-Shell" -i "$EDITED_PATH" "Screenshot Processed" "Saved to $EDITED_PATH" \
    -A "view=View" -A "edit=Edit" -A "open=Open Folder")

case "$ACTION" in
    view)
        xdg-open "$EDITED_PATH"
        ;;
    edit)
        if command -v swappy >/dev/null 2>&1; then
            swappy -f "$EDITED_PATH"
        else
            xdg-open "$EDITED_PATH"
        fi
        ;;
    open)
        xdg-open "$SAVE_DIR"
        ;;
esac

log "Process completed"
