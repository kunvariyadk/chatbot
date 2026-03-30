"""
Session Data Access Object
Database operations for chat sessions and messages
"""
import json
import secrets
from base import db
from base.com.vo.session_vo import ChatSession, ChatMessage
from datetime import datetime, timezone, timedelta


def create_session(chatbot_id=None, name=None, email=None, ip=None, user_agent=None):
    """Create a new chat session with analytics"""
    session_token = secrets.token_urlsafe(32)

    new_session = ChatSession(
        chatbot_id=chatbot_id,
        session_token=session_token,
        user_name=name,
        user_email=email,
        user_ip=ip,
        user_agent=user_agent
    )
    db.session.add(new_session)
    db.session.commit()
    return new_session.id, session_token


def get_session_by_id(session_id):
    """Get session by ID"""
    return ChatSession.query.get(session_id)


def get_session_by_token(session_token):
    """Get session by token"""
    return ChatSession.query.filter_by(session_token=session_token).first()


def log_message(session_id, sender, message, intent=None, confidence=None,
                is_fallback=False, processing_time=None, extra=None):
    """Log a chat message with analytics"""
    msg = ChatMessage(
        session_id=session_id,
        sender=sender,
        message=message,
        intent=intent,
        confidence=confidence,
        is_fallback=is_fallback,
        processing_time_ms=processing_time,
        extra_data=json.dumps(extra or {})
    )
    db.session.add(msg)

    # Update session analytics
    session = ChatSession.query.get(session_id)
    if session:
        session.increment_message_count()

        if is_fallback:
            session.fallback_count = (session.fallback_count or 0) + 1

        # Update average confidence
        if confidence and sender == 'bot':
            if session.avg_confidence == 0:
                session.avg_confidence = confidence
            else:
                # Running average
                session.avg_confidence = (session.avg_confidence + confidence) / 2

    db.session.commit()
    return msg.id


def end_session(session_id):
    """End a chat session"""
    session = ChatSession.query.get(session_id)
    if session:
        session.ended_at = datetime.now(timezone.utc)
        db.session.commit()
        return True
    return False


def get_session_messages(session_id):
    """Get all messages from a session"""
    return ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp).all()


def get_chatbot_sessions(chatbot_id, limit=50):
    """Get recent sessions for a chatbot"""
    return ChatSession.query.filter_by(chatbot_id=chatbot_id).order_by(
        ChatSession.started_at.desc()
    ).limit(limit).all()


def get_chatbot_analytics(chatbot_id, days=30):
    """Get analytics for a chatbot"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    sessions = ChatSession.query.filter(
        ChatSession.chatbot_id == chatbot_id,
        ChatSession.started_at >= since
    ).all()

    total_sessions = len(sessions)
    total_messages = sum(s.message_count for s in sessions)
    avg_confidence = sum(s.avg_confidence for s in sessions if s.avg_confidence) / max(1, total_sessions)
    total_fallbacks = sum(s.fallback_count or 0 for s in sessions)

    return {
        'total_sessions': total_sessions,
        'total_messages': total_messages,
        'avg_messages_per_session': total_messages / max(1, total_sessions),
        'avg_confidence': avg_confidence,
        'total_fallbacks': total_fallbacks,
        'fallback_rate': total_fallbacks / max(1, total_messages)
    }


def get_active_sessions(chatbot_id, timeout_minutes=30):
    """Get currently active sessions for a chatbot"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

    return ChatSession.query.filter(
        ChatSession.chatbot_id == chatbot_id,
        ChatSession.last_activity >= cutoff,
        ChatSession.ended_at.is_(None)
    ).all()