"""
Live Chat Value Objects (Database Models)
==========================================
Place this file at:  base/com/vo/live_chat_vo.py

These models extend your existing ChatSession with a proper LiveChatMessage
table so owners can send messages back to users in real time.

Your existing ChatSession VO already has:
    - is_live   (Boolean)  — set to True when live mode is active
    - status    (String)   — "bot" | "human"

We add one new table: LiveChatMessage
"""

from base import db
from datetime import datetime, timezone


class LiveChatMessage(db.Model):
    """
    Stores real-time messages exchanged during a live-chat session.
    Separate from ChatMessage so we never pollute the bot-analytics table.

    Columns
    -------
    id            – primary key
    session_id    – FK → chat_session.id  (your existing ChatSession table)
    sender_role   – 'user' | 'owner'
    message       – the text content
    timestamp     – UTC creation time
    is_read       – owner has seen it (used for unread badge)
    """
    __tablename__ = 'live_chat_message'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'),
                           nullable=False, index=True)
    sender_role = db.Column(db.String(10), nullable=False)  # 'user' | 'owner'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime,
                          default=lambda: datetime.now(timezone.utc),
                          nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    # ── relationship back to the session ──────────────────────────
    session = db.relationship('ChatSession', backref='live_messages',
                              lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'sender_role': self.sender_role,
            'message': self.message,
            'timestamp': self.timestamp.strftime('%H:%M'),
            'is_read': self.is_read,
        }
