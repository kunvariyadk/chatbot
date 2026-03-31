"""
Analytics Controller
Handles chatbot analytics, session tracking, and conversation history
"""
from base import app
from flask import render_template, redirect, url_for, session, flash

from base.com.dao.user_dao import get_user_by_id
from base.com.dao.chat_dao import get_chatbot_by_id, get_chatbots_by_user
from base.com.dao.session_dao import (
    get_chatbot_analytics,
    get_chatbot_sessions,
    get_session_by_id,
    get_session_messages
)
from base.com.controller.decorators import subscription_required


# ============================================
# ANALYTICS ROUTES
# ============================================

@app.route('/chatbot/analytics/<int:chatbot_id>')
@subscription_required
def chatbot_analytics(chatbot_id):
    """View chatbot analytics and conversation history"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)

    # Check authorization
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # Get analytics data
    analytics_7d = get_chatbot_analytics(chatbot_id, days=7)
    analytics_30d = get_chatbot_analytics(chatbot_id, days=30)
    recent_sessions = get_chatbot_sessions(chatbot_id, limit=20)

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    return render_template(
        'analytics.html',
        chatbot=chatbot,
        analytics_7d=analytics_7d,
        analytics_30d=analytics_30d,
        recent_sessions=recent_sessions,
        chatbots=chatbots,
        user=user
    )


@app.route('/chatbot/session/<int:session_id>')
@subscription_required
def view_session(session_id):
    """View detailed conversation history for a session"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chat_session = get_session_by_id(session_id)

    if not chat_session:
        flash('Session not found', 'error')
        return redirect(url_for('dashboard'))

    chatbot = get_chatbot_by_id(chat_session['chatbot_id'])

    # Check authorization
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    messages = get_session_messages(session_id)

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    return render_template(
        'session_details.html',
        chat_session=chat_session,
        chatbot=chatbot,
        messages=messages,
        chatbots=chatbots,
        user=user
    )


print("✅ Analytics controller loaded successfully!")