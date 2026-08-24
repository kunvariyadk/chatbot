"""
Live Chat Controller
====================
Place this file at:  base/com/controller/live_chat_controller.py

Then add this import to base/com/controller/__init__.py:
    from base.com.controller import live_chat_controller

Requires
--------
    pip install flask-socketio flask-mail eventlet

What this file provides
-----------------------
  HTTP Routes
    GET  /live-chat                       – owner dashboard (list of active requests)
    GET  /live-chat/session/<session_id>  – owner chat window for one session
    POST /live-chat/end/<session_id>      – owner ends the live session → bot resumes
    GET  /live-chat/history/<session_id>  – AJAX: JSON message history
    GET  /live-chat/unread-count          – AJAX: badge count for sidebar

  SocketIO Events (server-side handlers)
    join_live_room   – user/owner joins a Socket room keyed by session_id
    owner_message    – owner sends a message → broadcast to user widget
    user_message_live – user sends a message during live mode → broadcast to owner

  Helper
    send_live_chat_email() – fires the notification email to the chatbot owner
"""
import smtplib

from base import app, db, mail, socketio
from flask import render_template, request, jsonify, session, redirect, url_for
from flask_mail import Message
from flask_socketio import emit, join_room, leave_room
from datetime import datetime, timezone
from base.com.controller.decorators import login_required, premium_required
from base.com.vo.session_vo import ChatSession
from base.com.vo.live_chat_vo import LiveChatMessage
from base.com.vo.chatbot_vo import Chatbot
from base.com.vo.user_vo import User
from base.com.dao.user_dao import get_user_by_id
from base.com.controller.decorators import login_required
from email.message import EmailMessage


# ═══════════════════════════════════════════════════════════════════
#  HELPER — Email notification
# ═══════════════════════════════════════════════════════════════════

def send_live_chat_email(owner, chatbot, session_id):
    """
    Send an HTML email to the chatbot owner using standard Python smtplib.
    Now includes the Visitor's actual Name and Contact info!
    """
    from base.com.vo.session_vo import ChatSession

    # 1. Fetch the session to grab the newly saved name and contact
    chat_session = ChatSession.query.get(session_id)
    visitor_name = chat_session.visitor_name if chat_session and chat_session.visitor_name else "A visitor"
    visitor_contact = chat_session.visitor_contact if chat_session and chat_session.visitor_contact else "Not provided"

    dashboard_url = url_for(
        'live_chat_session',
        session_id=session_id,
        _external=True
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: Inter, Arial, sans-serif; background: #f7fafc; margin: 0; padding: 0; }}
        .wrap {{ max-width: 580px; margin: 40px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #4F46E5, #7C3AED); color: #fff; padding: 32px 36px; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
        .header p  {{ margin: 6px 0 0; opacity: 0.85; font-size: 14px; }}
        .body {{ padding: 32px 36px; }}
        .badge {{ display: inline-block; background: #fef3c7; color: #92400e; border-radius: 6px; padding: 4px 12px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }}
        .info-row {{ display: flex; gap: 12px; margin-bottom: 12px; font-size: 14px; color: #4a5568; }}
        .label {{ font-weight: 600; color: #1a202c; min-width: 80px; }}
        .cta {{ display: block; margin: 28px 0 0; text-align: center; }}
        .btn  {{ background: #4F46E5; color: #fff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 15px; display: inline-block; }}
        .footer {{ padding: 20px 36px; background: #f7fafc; font-size: 12px; color: #a0aec0; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="header">
          <h1>🔔 Live Chat Request</h1>
          <p>{visitor_name} is waiting for you</p>
        </div>
        <div class="body">
          <div class="badge">⚡ Needs Immediate Attention</div>

          <div class="info-row"><span class="label">Name:</span><span><strong>{visitor_name}</strong></span></div>
          <div class="info-row"><span class="label">Contact:</span><span>{visitor_contact}</span></div>
          <div class="info-row"><span class="label">Chatbot:</span><span>{chatbot.bot_name}</span></div>

          <p style="color:#4a5568; font-size:14px; margin-top:20px;">
            The AI has been paused. Please join the chat to assist them.
          </p>
          <div class="cta"><a href="{dashboard_url}" class="btn">Reply to {visitor_name} →</a></div>
        </div>
        <div class="footer">ChatBot Builder · You are receiving this because you own this chatbot.</div>
      </div>
    </body>
    </html>
    """
    try:
        import os
        import smtplib
        from email.message import EmailMessage
        from base import app

        sender_email = app.config.get('MAIL_USERNAME') or os.getenv('MAIL_USERNAME', 'kunvariya.dk@gmail.com')
        app_password = "cwpctdztwwohcjhe"

        if not app_password:
            print("⚠️ CRITICAL: The email password is blank!")
            return

        msg = EmailMessage()
        # 👇 Subject line now includes their name!
        msg['Subject'] = f"🔔 {visitor_name} requested Live Chat — {chatbot.bot_name}"
        msg['From'] = sender_email
        msg['To'] = owner.email

        msg.set_content(f"{visitor_name} needs your help! Please open your dashboard.")
        msg.add_alternative(html_body, subtype='html')

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()

        print(f"✅ Live-chat email for {visitor_name} sent successfully!")

    except Exception as e:
        print(f"⚠️ Live-chat email failed: {e}")


# ═══════════════════════════════════════════════════════════════════
#  HTTP ROUTES — Owner Dashboard
# ═══════════════════════════════════════════════════════════════════

@app.route('/live-chat')
@login_required
@premium_required
def live_chat_dashboard():
    """
    Owner-only page: lists ALL active live-chat sessions across
    all chatbots belonging to this owner.
    """
    user = get_user_by_id(session['user_id'])

    # Collect all chatbot ids owned by this user
    chatbot_ids = [c.id for c in user.chatbots]

    # Sessions that are currently in live mode (not yet ended)
    active_sessions = (
        ChatSession.query
        .filter(
            ChatSession.chatbot_id.in_(chatbot_ids),
            ChatSession.is_live == True,  # noqa: E712
            ChatSession.status != 'ended'
        )
        .order_by(ChatSession.last_activity.desc())
        .all()
    )

    # Attach unread count to each session for the badge
    sessions_data = []
    for s in active_sessions:
        unread = LiveChatMessage.query.filter_by(
            session_id=s.id,
            sender_role='user',
            is_read=False
        ).count()

        chatbot = Chatbot.query.get(s.chatbot_id)
        sessions_data.append({
            'session': s,
            'chatbot': chatbot,
            'unread': unread,
        })

    return render_template(
        'live_chat.html',
        user=user,
        sessions_data=sessions_data,
    )


@app.route('/live-chat/session/<int:session_id>')
@premium_required
@login_required
def live_chat_session(session_id):
    """
    Owner chat window. Shows the full conversation history and
    provides the real-time message input.
    """
    user = get_user_by_id(session['user_id'])
    chat_session = ChatSession.query.get_or_404(session_id)
    chatbot = Chatbot.query.get_or_404(chat_session.chatbot_id)

    # Security: only the owner of this chatbot can view the session
    if chatbot.user_id != user.id:
        return redirect(url_for('live_chat_dashboard'))

    # Mark all user messages in this session as read
    LiveChatMessage.query.filter_by(
        session_id=session_id,
        sender_role='user',
        is_read=False
    ).update({'is_read': True})
    db.session.commit()

    # Load existing live messages for history
    messages = (
        LiveChatMessage.query
        .filter_by(session_id=session_id)
        .order_by(LiveChatMessage.timestamp.asc())
        .all()
    )

    return render_template(
        'live_chat_session.html',
        user=user,
        chat_session=chat_session,
        chatbot=chatbot,
        messages=messages,
    )


@app.route('/live-chat/end/<int:session_id>', methods=['POST'])
@premium_required
@login_required
def end_live_chat(session_id):
    """
    Owner clicks "End Live Chat" → bot mode resumes.
    Broadcasts a SocketIO event so the user widget knows immediately.
    """
    user = get_user_by_id(session['user_id'])
    chat_session = ChatSession.query.get_or_404(session_id)
    chatbot = Chatbot.query.get_or_404(chat_session.chatbot_id)

    if chatbot.user_id != user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    chat_session.is_live = False
    chat_session.status = 'bot'
    db.session.commit()

    # Tell the user widget that the human has disconnected
    socketio.emit(
        'live_chat_ended',
        {'message': 'The representative has ended the session. The AI assistant is back!'},
        room=f'session_{session_id}'
    )

    return jsonify({'success': True})


@app.route('/live-chat/history/<int:session_id>')
@premium_required
@login_required
def live_chat_history(session_id):
    """
    AJAX endpoint — returns JSON history of all LiveChatMessages
    for a session. Polled by the owner dashboard as a fallback
    when SocketIO is not connected.
    """
    user = get_user_by_id(session['user_id'])
    chat_session = ChatSession.query.get_or_404(session_id)
    chatbot = Chatbot.query.get_or_404(chat_session.chatbot_id)

    if chatbot.user_id != user.id:
        return jsonify({'success': False}), 403

    messages = (
        LiveChatMessage.query
        .filter_by(session_id=session_id)
        .order_by(LiveChatMessage.timestamp.asc())
        .all()
    )

    return jsonify({
        'success': True,
        'messages': [m.to_dict() for m in messages],
        'is_live': chat_session.is_live,
    })


@app.route('/live-chat/unread-count')
@premium_required
@login_required
def live_chat_unread_count():
    """
    AJAX endpoint — returns total unread messages across all live
    sessions for this owner. Used to drive the sidebar badge.
    """
    user = get_user_by_id(session['user_id'])
    chatbot_ids = [c.id for c in user.chatbots]

    active_session_ids = [
        s.id for s in ChatSession.query
        .filter(
            ChatSession.chatbot_id.in_(chatbot_ids),
            ChatSession.is_live == True  # noqa: E712
        ).all()
    ]

    total_unread = LiveChatMessage.query.filter(
        LiveChatMessage.session_id.in_(active_session_ids),
        LiveChatMessage.sender_role == 'user',
        LiveChatMessage.is_read == False  # noqa: E712
    ).count()

    return jsonify({'unread': total_unread})


# ═══════════════════════════════════════════════════════════════════
#  SOCKETIO EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════════

@socketio.on('join_live_room')
def handle_join_live_room(data):
    """
    Both the user widget AND the owner dashboard call this when they
    connect. They join the same room keyed by session_id so messages
    broadcast to that room reach both sides instantly.

    Expected payload:  { "session_id": 42 }
    """
    sid = data.get('session_id')
    if sid:
        room = f'session_{sid}'
        join_room(room)
        emit('room_joined', {'room': room, 'session_id': sid})
        print(f"🔌 Client joined room: {room}")


@socketio.on('leave_live_room')
def handle_leave_live_room(data):
    sid = data.get('session_id')
    if sid:
        leave_room(f'session_{sid}')


@socketio.on('owner_message')
def handle_owner_message(data):
    """
    Owner types a message in the dashboard → save to DB → push to user.

    Expected payload:
        {
            "session_id": 42,
            "message":    "Hello, how can I help you today?",
            "owner_name": "Raj"        # optional display name
        }
    """
    sid = data.get('session_id')
    text = (data.get('message') or '').strip()
    owner_nm = data.get('owner_name', 'Support')

    if not sid or not text:
        return

    # Persist to DB
    lm = LiveChatMessage(
        session_id=sid,
        sender_role='owner',
        message=text,
    )
    db.session.add(lm)
    db.session.commit()

    # Broadcast to everyone in the room (owner window + user widget)
    emit(
        'new_live_message',
        {
            'sender_role': 'owner',
            'sender_name': owner_nm,
            'message': text,
            'timestamp': lm.timestamp.strftime('%H:%M'),
        },
        room=f'session_{sid}'
    )


@socketio.on('user_message_live')
def handle_user_message_live(data):
    """
    User sends a message WHILE in live-chat mode.
    The embed widget calls this INSTEAD of the REST API so the message
    reaches the owner in real time.

    Expected payload:
        {
            "session_id": 42,
            "message":    "I need help with my order"
        }
    """
    sid = data.get('session_id')
    text = (data.get('message') or '').strip()

    if not sid or not text:
        return

    # Validate the session is actually in live mode
    chat_session = ChatSession.query.get(sid)
    if not chat_session or not chat_session.is_live:
        return

    # Persist to DB (is_read=False so the owner badge lights up)
    lm = LiveChatMessage(
        session_id=sid,
        sender_role='user',
        message=text,
        is_read=False,
    )
    db.session.add(lm)
    db.session.commit()

    # Broadcast to everyone in the session room
    emit(
        'new_live_message',
        {
            'sender_role': 'user',
            'sender_name': 'Visitor',
            'message': text,
            'timestamp': lm.timestamp.strftime('%H:%M'),
        },
        room=f'session_{sid}'
    )


@socketio.on('owner_typing')
def handle_owner_typing(data):
    """Broadcasts a typing indicator from the owner to the user."""
    sid = data.get('session_id')
    if sid:
        emit('owner_typing', {}, room=f'session_{sid}', include_self=False)


@socketio.on('owner_stopped_typing')
def handle_owner_stopped_typing(data):
    sid = data.get('session_id')
    if sid:
        emit('owner_stopped_typing', {}, room=f'session_{sid}', include_self=False)


print("✅ Live Chat controller loaded.")
