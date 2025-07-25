from dotenv import load_dotenv
load_dotenv()

import os
import re
import sqlite3
import tempfile
from flask import Flask, abort, request
from linebot import LineBotApi, WebhookHandler
# ユーザーの「どこから」来たかを判断するために、Source情報をインポートします
from linebot.models import (
    ImageMessage, MessageEvent, TextMessage, TextSendMessage,
    SourceUser, SourceGroup, SourceRoom
)
from linebot.exceptions import InvalidSignatureError
from PIL import Image
import pytesseract

KEYWORDS = ["不採用", "お祈り", "残念ながら", "難しい", "申し訳ございません", "添えず", "できかねる", "ご期待"]

DB_PATH = "counts.db"

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

if not (LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN):
    raise RuntimeError("Environment variables LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN must be set.")

app = Flask(__name__)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
# データベースに表示名(display_name)を保存する列を追加します
cur.execute("CREATE TABLE IF NOT EXISTS counts (user_id TEXT PRIMARY KEY, display_name TEXT, count INTEGER)")
conn.commit()

def get_display_name(event_source):
    """メッセージの送信元に応じて、ユーザーの表示名を取得する関数"""
    user_id = event_source.user_id
    if isinstance(event_source, SourceGroup):
        # グループからのメッセージの場合
        profile = line_bot_api.get_group_member_profile(event_source.group_id, user_id)
    elif isinstance(event_source, SourceRoom):
        # 複数人チャットからのメッセージの場合
        profile = line_bot_api.get_room_member_profile(event_source.room_id, user_id)
    else:
        # 1対1のチャットからのメッセージの場合
        profile = line_bot_api.get_profile(user_id)
    return profile.display_name

def increment(user_id: str, display_name: str) -> int:
    """カウントを増やし、表示名を更新する関数"""
    # ユーザーが存在しない場合は、新しい行を作成
    cur.execute("INSERT OR IGNORE INTO counts VALUES (?, ?, 0)", (user_id, display_name))
    # カウントを1増やし、表示名を最新のものに更新
    cur.execute("UPDATE counts SET count = count + 1, display_name = ? WHERE user_id = ?", (display_name, user_id))
    conn.commit()
    cur.execute("SELECT count FROM counts WHERE user_id = ?", (user_id,))
    return cur.fetchone()[0]

def contains_rejection(text: str) -> bool:
    return any(re.search(k, text) for k in KEYWORDS)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=ImageMessage)
def on_image(event: MessageEvent):
    message_id = event.message.id
    content = line_bot_api.get_message_content(message_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
        for chunk in content.iter_content():
            tf.write(chunk)
        temp_path = tf.name

    text = pytesseract.image_to_string(Image.open(temp_path), lang="jpn")
    if contains_rejection(text):
        try:
            # 送信者の表示名を取得
            display_name = get_display_name(event.source)
        except Exception:
            # もし何らかの理由で名前が取れなければ「名無しさん」にする
            display_name = "名無しさん"

        total = increment(event.source.user_id, display_name)
        # 返信メッセージに名前を入れる
        reply = f"📩 {display_name}さん、落選メールを検出しました！\nあなたはこれで {total} 件目です😭"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@handler.add(MessageEvent, message=TextMessage)
def on_text(event: MessageEvent):
    msg = event.message.text.strip().lower()
    if msg in {"ランキング", "rank", "stats", "stat"}:
        # データベースから表示名とカウントを取得
        cur.execute("SELECT display_name, count FROM counts WHERE count > 0 ORDER BY count DESC LIMIT 10")
        rows = cur.fetchall()
        if not rows:
            reply = "まだ誰も落選メールを共有していません！✨"
        else:
            lines = ["🏆 落選メールカウント ランキング 🏆"]
            medals = ["🥇", "🥈", "🥉"]
            # ランキングにユーザーIDの代わりに表示名を表示
            for i, (name, cnt) in enumerate(rows, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                lines.append(f"{medal} {name}さん: {cnt} 件")
            reply = "\n".join(lines)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)