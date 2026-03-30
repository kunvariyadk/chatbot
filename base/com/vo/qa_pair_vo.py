"""
QA Pair Value Object (Model)
Question-Answer training pairs
"""
from base import db
from datetime import datetime, timezone


class QAPair(db.Model):
    __tablename__ = 'qa_pairs'

    id = db.Column(db.Integer, primary_key=True)
    chatbot_id = db.Column(db.Integer, db.ForeignKey('chatbot.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    tag = db.Column(db.String(100))

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        """Convert QA pair to dictionary"""
        def format_datetime(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        return {
            'id': self.id,
            'question': self.question,
            'answer': self.answer,
            'tag': self.tag,
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }

    def __repr__(self):
        return f'<QAPair {self.id} - Chatbot {self.chatbot_id}>'