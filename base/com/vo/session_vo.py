"""
Session Value Objects (Models)
Chat sessions and messages with analytics
"""
import json
from base import db
from datetime import datetime, timezone


class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'

    id = db.Column(db.Integer, primary_key=True)
    chatbot_id = db.Column(db.Integer, db.ForeignKey('chatbot.id'), nullable=True)
    session_token = db.Column(db.String(100), unique=True)
    is_live = db.Column(db.Boolean, default=False)
    # Add this inside your ChatSession class
    status = db.Column(db.String(20), default='bot')
    # User identification
    user_name = db.Column(db.String(100))
    user_email = db.Column(db.String(120))
    user_ip = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    visitor_name = db.Column(db.String(150), nullable=True)
    visitor_contact = db.Column(db.String(150), nullable=True)
    # Session timing
    started_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime(timezone=True))
    last_activity = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Analytics
    message_count = db.Column(db.Integer, default=0)
    avg_confidence = db.Column(db.Float, default=0.0)
    fallback_count = db.Column(db.Integer, default=0)
    satisfaction_rating = db.Column(db.Integer)

    # Relationships
    messages = db.relationship('ChatMessage', backref='session', lazy=True,
                               cascade='all, delete-orphan')

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now(timezone.utc)
        db.session.commit()

    def increment_message_count(self):
        """Increment message counter"""
        self.message_count += 1
        self.update_activity()

    def is_active(self, timeout_minutes=30):
        """Check if session is still active"""
        if not self.last_activity:
            return False

        now = datetime.now(timezone.utc)
        if self.last_activity.tzinfo is None:
            last_activity = self.last_activity.replace(tzinfo=timezone.utc)
        else:
            last_activity = self.last_activity

        return (now - last_activity).total_seconds() < (timeout_minutes * 60)

    def get_duration(self):
        """Get session duration in seconds"""
        if not self.started_at:
            return 0

        end = self.ended_at if self.ended_at else datetime.now(timezone.utc)

        start = self.started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        return (end - start).total_seconds()

    def __repr__(self):
        return f'<ChatSession {self.id} for Chatbot {self.chatbot_id}>'


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False)

    # Message content
    sender = db.Column(db.Enum('user', 'bot', 'owner')) # 'user' or 'bot'
    message = db.Column(db.Text)

    # AI Analytics
    intent = db.Column(db.String(100))
    confidence = db.Column(db.Float)
    is_fallback = db.Column(db.Boolean, default=False)
    processing_time_ms = db.Column(db.Integer)

    # Context
    extra_data = db.Column(db.Text)  # JSON data
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert message to dictionary"""
        return {
            'id': self.id,
            'sender': self.sender,
            'message': self.message,
            'intent': self.intent,
            'confidence': self.confidence,
            'is_fallback': self.is_fallback,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self):
        return f'<ChatMessage {self.id} from {self.sender}>'