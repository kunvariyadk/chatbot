"""
Chatbot Data Access Object
Database operations for Chatbot model
"""
from base import db
from base.com.vo.chatbot_vo import Chatbot
from datetime import datetime, timezone


def get_chatbot_by_id(chatbot_id):
    """Get chatbot by ID"""
    return db.session.get(Chatbot, chatbot_id)


def get_chatbot_by_embed_code(embed_code):
    """Get chatbot by embed code"""
    return Chatbot.query.filter_by(embed_code=embed_code).first()


def get_chatbots_by_user(user_id):
    """Get all chatbots for a user"""
    return Chatbot.query.filter_by(user_id=user_id).order_by(Chatbot.created_at.desc()).all()


def get_active_chatbots_by_user(user_id):
    """Get active chatbots for a user"""
    return Chatbot.query.filter_by(user_id=user_id, is_active=True).all()


def create_chatbot(user_id, name, **kwargs):
    """Create new chatbot"""
    chatbot = Chatbot(
        user_id=user_id,
        name=name,
        **kwargs
    )

    db.session.add(chatbot)
    db.session.commit()

    return chatbot


def update_chatbot(chatbot_id, **kwargs):
    """Update chatbot fields"""
    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot:
        return None

    for key, value in kwargs.items():
        if hasattr(chatbot, key):
            setattr(chatbot, key, value)

    chatbot.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return chatbot


def delete_chatbot(chatbot_id):
    """Delete chatbot"""
    chatbot = get_chatbot_by_id(chatbot_id)
    if chatbot:
        db.session.delete(chatbot)
        db.session.commit()
        return True
    return False


def toggle_chatbot_status(chatbot_id):
    """Toggle chatbot active status"""
    chatbot = get_chatbot_by_id(chatbot_id)
    if chatbot:
        chatbot.is_active = not chatbot.is_active
        db.session.commit()
        return chatbot.is_active
    return None


def count_chatbots_by_user(user_id):
    """Count total chatbots for a user"""
    return Chatbot.query.filter_by(user_id=user_id).count()