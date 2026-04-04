#!/usr/bin/env bash
# notify.sh — Shared Telegram notification helper
# Source this file from wrapper scripts: source "${PROJECT_DIR}/bin/notify.sh"
# Requires: TG_BOT_TOKEN, TG_CHAT_ID set in environment

_TG_API_MSG="https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage"
_TG_API_PHOTO="https://api.telegram.org/bot${TG_BOT_TOKEN}/sendPhoto"
_TG_CAPTION_LIMIT=1024
_HOSTNAME=$(hostname -s)
_HEADER_IMAGE="${PROJECT_DIR}/images/PriceTracker_01.png"

_send_telegram_text() {
    local message="$1"
    # Truncate if too long (Telegram limit 4096)
    if [ ${#message} -gt 3500 ]; then
        message="${message:0:3500}..."
    fi
    curl -s -X POST "${_TG_API_MSG}" \
        -H "Content-Type: application/json" \
        -d "$(jq -n \
            --arg chat_id "${TG_CHAT_ID}" \
            --arg text "${message}" \
            --arg parse_mode "HTML" \
            '{chat_id: $chat_id, text: $text, parse_mode: $parse_mode}')" \
        > /dev/null 2>&1 || true
}

_send_telegram_photo() {
    local caption="$1"
    local remainder="$2"
    # Caption limit is 1024 chars for photos
    if [ ${#caption} -gt ${_TG_CAPTION_LIMIT} ]; then
        # Split: send photo with truncated caption, then text with the rest
        local short="${caption:0:${_TG_CAPTION_LIMIT}}"
        remainder="${caption:${_TG_CAPTION_LIMIT}}${remainder:+
${remainder}}"
        caption="${short}"
    fi
    if [ -f "${_HEADER_IMAGE}" ]; then
        curl -s -X POST "${_TG_API_PHOTO}" \
            -F "chat_id=${TG_CHAT_ID}" \
            -F "photo=@${_HEADER_IMAGE}" \
            -F "caption=${caption}" \
            -F "parse_mode=HTML" \
            > /dev/null 2>&1 || true
        # Send remainder as follow-up text message if needed
        if [ -n "${remainder}" ]; then
            _send_telegram_text "${remainder}"
        fi
    else
        # No image available — send as plain text
        _send_telegram_text "${caption}${remainder:+
${remainder}}"
    fi
}

notify_success() {
    local pipeline="$1"
    local steps_passed="$2"
    local steps_total="$3"
    local duration="$4"
    local token_count="$5"
    local ts
    ts=$(date -u +"%Y-%m-%d %H:%M UTC")

    local caption="📊 Daily Price Update 📊

⏰ ${ts}
🖥 ${_HOSTNAME}

✅ Pipeline: ${pipeline}

🏆 Results:
• 📈 Steps: ${steps_passed}/${steps_total} passed
• 🪙 Tokens: ${token_count}
• ⏱ Duration: ${duration}

💪 Data fresh & backed up! 💎
🔥 #Crypto #Eeva #PriceTracker"

    _send_telegram_photo "${caption}" ""
}

notify_failure() {
    local pipeline="$1"
    local detail="$2"
    local ts
    ts=$(date -u +"%Y-%m-%d %H:%M UTC")

    local caption="🚨 Price Tracker Alert 🚨

⏰ ${ts}
🖥 ${_HOSTNAME}

❌ Pipeline: ${pipeline}
⚠️ Status: FAILED

${detail}

🔧 Check logs for details
🔥 #Crypto #Eeva #PriceTracker"

    _send_telegram_photo "${caption}" ""
}
