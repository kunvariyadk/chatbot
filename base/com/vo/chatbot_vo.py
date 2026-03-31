"""
Chatbot Value Object (Model)
Chatbot configuration and settings
"""
import json
import re
from base import db
from datetime import datetime, timezone


class Chatbot(db.Model):
    __tablename__ = 'chatbot'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    embed_code = db.Column(db.String(500), unique=True)
    is_active = db.Column(db.Boolean, default=False)
    training_data = db.Column(db.Text)
    training_file = db.Column(db.String(200))
    theme_color = db.Column(db.String(7), default='#4F46E5')
    welcome_message = db.Column(db.String(200), default='Hello! How can I help you?')
    bot_name = db.Column(db.String(100), default='AI Assistant')
    use_ml_model = db.Column(db.Boolean, default=False)
    intents_path = db.Column(db.String(255))
    trained_folder = db.Column(db.String(255))
    is_trained = db.Column(db.Boolean, default=False)

    # Avatar and styling
    bot_avatar = db.Column(db.String(500))
    welcome_button_text = db.Column(db.String(100))
    welcome_button_url = db.Column(db.String(500))
    flow_data = db.Column(db.Text, nullable=True, default='[]')
    chat_background_color = db.Column(db.String(7), default='#F7FAFC')
    user_message_color = db.Column(db.String(7))
    bot_message_color = db.Column(db.String(7), default='#FFFFFF')
    user_text_color = db.Column(db.String(7), default='#FFFFFF')
    bot_text_color = db.Column(db.String(7), default='#1A202C')

    # Welcome buttons with submenu support
    welcome_buttons = db.Column(db.Text, comment='JSON data for welcome buttons with submenu support')

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relationships
    qa_pairs = db.relationship('QAPair', backref='chatbot', lazy=True,
                               cascade='all, delete-orphan')
    chat_sessions = db.relationship('ChatSession', backref='chatbot', lazy=True,
                                    cascade='all, delete-orphan')

    def get_welcome_buttons_dict(self):
        """Parse and return welcome_buttons as a Python list"""
        if not self.welcome_buttons:
            return []

        try:
            buttons = json.loads(self.welcome_buttons)
            return buttons if isinstance(buttons, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_welcome_buttons_dict(self, buttons_list):
        """
        Set welcome_buttons from a Python list.
        Supports infinite recursive branching (nested_buttons) and
        automatically migrates legacy 'submenu_items'.
        """
        if not isinstance(buttons_list, list):
            self.welcome_buttons = '[]'
            return False

        valid_types = ['url', 'intent', 'message']

        def clean_node(btn):
            if not isinstance(btn, dict):
                return None

            text = str(btn.get('text', '')).strip()
            if not text:
                return None

            b_type = str(btn.get('type', 'message')).strip()
            if b_type not in valid_types:
                b_type = 'message'

            cleaned = {
                'id': str(btn.get('id', '')),
                'text': text,
                'type': b_type,
                'value': str(btn.get('value', '')).strip(),
                'nested_buttons': []
            }

            # 1. Gracefully migrate legacy 'submenu_items' if they exist
            legacy_subs = btn.get('submenu_items', [])
            if isinstance(legacy_subs, list):
                for sub in legacy_subs:
                    if isinstance(sub, dict) and str(sub.get('text', '')).strip():
                        s_type = str(sub.get('type', 'url')).strip()
                        if s_type not in valid_types:
                            s_type = 'url'

                        cleaned['nested_buttons'].append({
                            'id': str(sub.get('id', '')),
                            'text': str(sub.get('text', '')).strip(),
                            'type': s_type,
                            'value': str(sub.get('value', '')).strip(),
                            'nested_buttons': []
                        })

            # 2. Process infinite nested_buttons recursively
            nested = btn.get('nested_buttons', [])
            if isinstance(nested, list):
                for n_btn in nested:
                    valid_nested = clean_node(n_btn)  # Recursive call
                    if valid_nested:
                        cleaned['nested_buttons'].append(valid_nested)

            return cleaned

        # Process all top-level buttons
        validated_buttons = []
        for button in buttons_list:
            valid_btn = clean_node(button)
            if valid_btn:
                validated_buttons.append(valid_btn)

        self.welcome_buttons = json.dumps(validated_buttons)
        return True

    def preprocess(self, text: str) -> str:
        """Dynamic preprocessing"""
        if not text:
            return ""

        text = text.lower().strip()
        text = re.sub(r"[^a-zA-Z0-9\s]", "", text)

        if self.training_file and 'faq' in (self.training_file or "").lower():
            text = text.replace('?', '')

        return text

    def __repr__(self):
        return f'<Chatbot {self.name} (user_id={self.user_id})>'