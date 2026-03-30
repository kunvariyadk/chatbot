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
        """Set welcome_buttons from a Python list"""
        if not isinstance(buttons_list, list):
            self.welcome_buttons = '[]'
            return False

        valid_types = ['url', 'intent', 'message', 'submenu']
        validated_buttons = []

        for button in buttons_list:
            if not isinstance(button, dict):
                continue

            button_data = {
                'text': button.get('text', '').strip(),
                'type': button.get('type', 'url').strip(),
                'value': button.get('value', '').strip(),
                'has_submenu': button.get('has_submenu', False),
                'submenu_items': []
            }

            if button_data['type'] not in valid_types:
                button_data['type'] = 'url'

            if button_data['has_submenu'] and 'submenu_items' in button:
                submenu_items = button.get('submenu_items', [])
                if isinstance(submenu_items, list):
                    for sub_item in submenu_items:
                        if isinstance(sub_item, dict) and sub_item.get('text', '').strip():
                            sub_type = sub_item.get('type', 'url').strip()
                            if sub_type not in valid_types:
                                sub_type = 'url'

                            button_data['submenu_items'].append({
                                'text': sub_item.get('text', '').strip(),
                                'type': sub_type,
                                'value': sub_item.get('value', '').strip()
                            })

            if button_data['text']:
                validated_buttons.append(button_data)

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