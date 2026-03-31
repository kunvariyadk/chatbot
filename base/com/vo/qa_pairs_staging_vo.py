"""
QA Pair Staging Value Object (Model)
Staging table for testing new Q&A training pairs before merging into production
"""
from base import db
from datetime import datetime, timezone


class QAPairStaging(db.Model):
    __tablename__ = 'qa_pairs_staging'

    id = db.Column(db.Integer, primary_key=True)
    chatbot_id = db.Column(db.Integer, db.ForeignKey('chatbot.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    tag = db.Column(db.String(100))

    # Staging specific columns
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.Enum('pending', 'approved', 'rejected'), default='pending', nullable=False)
    review_note = db.Column(db.Text, nullable=True)

    tested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    merged_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    chatbot = db.relationship('Chatbot', backref='staging_pairs', lazy=True)
    added_by_user = db.relationship('User', backref='staging_pairs', lazy=True)

    def approve(self):
        """Mark this staging pair as approved"""
        self.status = 'approved'
        self.updated_at = datetime.now(timezone.utc)

    def reject(self, note=None):
        """Mark this staging pair as rejected with optional note"""
        self.status = 'rejected'
        self.review_note = note
        self.updated_at = datetime.now(timezone.utc)

    def mark_tested(self):
        """Mark this staging pair as tested/previewed"""
        self.tested_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def mark_merged(self):
        """Mark this staging pair as merged into production"""
        self.merged_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def to_qa_pair(self):
        """Convert staging pair to a production QAPair object (use before merging)"""
        from qa_pair import QAPair  # local import to avoid circular import
        return QAPair(
            chatbot_id=self.chatbot_id,
            question=self.question,
            answer=self.answer,
            tag=self.tag
        )

    def to_dict(self):
        """Convert staging QA pair to dictionary"""
        def format_datetime(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        return {
            'id': self.id,
            'chatbot_id': self.chatbot_id,
            'question': self.question,
            'answer': self.answer,
            'tag': self.tag,
            'added_by': self.added_by,
            'status': self.status,
            'review_note': self.review_note,
            'tested_at': format_datetime(self.tested_at),
            'merged_at': format_datetime(self.merged_at),
            'created_at': format_datetime(self.created_at),
            'updated_at': format_datetime(self.updated_at)
        }

    def __repr__(self):
        return f'<QAPairStaging {self.id} - Chatbot {self.chatbot_id} - Status {self.status}>'