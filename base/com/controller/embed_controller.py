"""
Embed Controller
Handles chatbot embedding and public chat API
"""
from sqlalchemy.sql.functions import user

from base import app, db
from flask import render_template, request, jsonify
import json
import time
from datetime import datetime, timezone
from base.com.dao.user_dao import get_user_by_id

from base.com.vo.user_vo import User
from base.com.vo.chatbot_vo import Chatbot
from base.com.dao.chat_dao import get_chatbot_by_embed_code
from base.com.dao.session_dao import create_session, log_message
from base.com.controller.decorators import login_required
from base.com.controller.live_chat_controller import send_live_chat_email
from base.com.vo.live_chat_vo import LiveChatMessage
# 🌟 UPGRADE: Import ChatSession to manage live state
from base.com.vo.session_vo import ChatSession


def get_avatar_url(chatbot, request):
    if not chatbot.bot_avatar:
        return None
    avatar_path = chatbot.bot_avatar.strip()
    base_url = request.url_root.rstrip('/')
    if avatar_path.startswith(('http://', 'https://')):
        return avatar_path
    if avatar_path.startswith('/data/users/'):
        return base_url + avatar_path
    if avatar_path.startswith('/static/'):
        return base_url + avatar_path
    if not avatar_path.startswith('/'):
        avatar_path = f"/data/users/user_{chatbot.user_id}/chatbots/chatbot_{chatbot.id}/{avatar_path}"
    return base_url + avatar_path


def detect_fallback_response(response: str, confidence: float) -> bool:
    if not response: return True
    response_lower = response.lower()
    valid_response_indicators = [
        'hello', 'hi', 'hey', 'welcome', 'thank you', 'you\'re welcome',
        'goodbye', 'bye', 'see you', 'my name is', 'i am', 'i can help',
        'here\'s', 'here is', 'the answer', 'according to', 'based on',
        'doing great', 'functioning', 'here to help', 'glad', 'happy to'
    ]
    for indicator in valid_response_indicators:
        if indicator in response_lower: return False
    if confidence > 0.40: return False

    fallback_indicators = [
        "didn't fully understand", "may have missed", "could you clarify",
        "explain it differently", "could you please rephrase", "provide more context",
        "still learning", "don't have that information", "unable to help with that",
        "outside my current capabilities", "don't have access to that",
        "not in my current knowledge", "try asking in another way",
        "use simpler or more specific", "break your request into smaller",
        "let me know what outcome", "try a different approach", "try rephrasing",
        "couldn't process that request", "something went wrong",
        "had trouble with that", "give it another shot", "try again",
        "connect with a support representative", "contact our support team",
        "reach a human agent", "reaching out to our support",
        "didn't catch that", "please repeat", "one more time",
        "not entirely confident", "need more information", "could you elaborate",
        "understand your question, but don't have", "not in my current knowledge base",
        "that topic isn't covered", "don't have details about that",
        "rate limit exceeded", "configuration error", "chatbot id is required"
    ]
    for indicator in fallback_indicators:
        if indicator in response_lower: return True
    if confidence < 0.05: return True
    return False


def process_button_action(action_type, action_value, chatbot):
    try:
        if action_type == 'url':
            if action_value and action_value.strip(): return f"🔗 Opening: {action_value}"
            return "❌ No URL provided."
        elif action_type == 'intent':
            try:
                from base.com.utils.utils import get_response_from_kb
                response = get_response_from_kb(action_value.lower().strip(), chatbot.user_id, chatbot_id=chatbot.id)
                if response: return response
                return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"
            except Exception as e:
                return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"
        elif action_type == 'message':
            message_text = action_value.strip()
            if not message_text: return "No message provided."
            return message_text
        else:
            return "Please select an option from the menu."
    except Exception as e:
        return "I encountered an error. Please try selecting again."


@app.route('/embed/<embed_code>')
def embed_chatbot(embed_code):
    chatbot = get_chatbot_by_embed_code(embed_code)
    if not chatbot:
        return render_template('embed.html', error="Chatbot not found",
                               message="This chatbot may have been removed."), 404
    if not chatbot.is_active:
        return render_template('embed.html', error="Chatbot unavailable",
                               message="This chatbot is currently inactive."), 403

    welcome_buttons_data = []
    if chatbot.welcome_buttons:
        try:
            welcome_buttons_data = json.loads(chatbot.welcome_buttons)
        except json.JSONDecodeError:
            welcome_buttons_data = []

    bot_avatar_url = get_avatar_url(chatbot, request)
    chatbot_settings = {
        'embedCode': chatbot.embed_code,
        'botName': chatbot.bot_name or 'AI Assistant',
        'welcomeMessage': chatbot.welcome_message or 'Hello! How can I help you?',
        'themeColor': chatbot.theme_color or '#4F46E5',
        'chatBackgroundColor': chatbot.chat_background_color or '#F7FAFC',
        'botMessageColor': chatbot.bot_message_color or '#FFFFFF',
        'botTextColor': chatbot.bot_text_color or '#1A202C',
        'userMessageColor': chatbot.user_message_color or (chatbot.theme_color or '#4F46E5'),
        'userTextColor': chatbot.user_text_color or '#FFFFFF',
        'botAvatar': bot_avatar_url,
        'welcomeButtons': welcome_buttons_data
    }

    return render_template(
        'embed.html', chatbot=chatbot, settings=chatbot_settings,
        welcome_buttons=welcome_buttons_data, bot_avatar_url=bot_avatar_url
    )


@app.route('/api/chat/<embed_code>', methods=['POST'])
def chat_api(embed_code):
    import time
    start_time = time.time()
    try:
        chatbot = get_chatbot_by_embed_code(embed_code)
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404

        user = User.query.get(chatbot.user_id)
        if not user or not user.subscription:
            return jsonify({'error': 'Service unavailable'}), 503

        if not user.subscription.can_send_message():
            return jsonify({
                'error': 'Message limit reached',
                'message': 'The chatbot owner has reached their monthly message limit.'
            }), 429

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        button_action = data.get('button_action')
        is_voice = data.get('is_voice', False)
        next_nested_buttons = []

        if not user_message and not button_action:
            return jsonify({'error': 'Empty message'}), 400

        # ── Session management ─────────────────────────────────────
        if not session_id:
            user_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', 'Unknown')
            session_id, session_token = create_session(
                chatbot_id=chatbot.id, ip=user_ip, user_agent=user_agent
            )
        else:
            session_token = None

        chat_session = ChatSession.query.get(session_id)
        is_live_mode = getattr(chat_session, 'is_live', False) if chat_session else False

        # ★ NEW: INTERCEPT VISITOR DETAILS FROM THE FORM ★
        # We catch it, save it directly to MySQL, and let the code keep running!
        if user_message.startswith('[Visitor Details]'):
            try:
                clean_str = user_message.replace('[Visitor Details]', '').strip()
                parts = clean_str.split('|')

                extracted_name = parts[0].replace('Name:', '').strip()
                extracted_contact = parts[1].replace('Contact:', '').strip()

                if chat_session:
                    chat_session.visitor_name = extracted_name
                    chat_session.visitor_contact = extracted_contact
                    db.session.commit()
                    print(f"✅ Saved Lead: {extracted_name} - {extracted_contact}")
            except Exception as e:
                print(f"⚠️ Error parsing lead data: {e}")

        # ── Button actions ─────────────────────────────────────────
        if button_action:
            action_type = button_action.get('type')
            action_value = button_action.get('value')
            next_nested_buttons = button_action.get('nested_buttons', [])

            # ★ LIVE CHAT ESCALATION ★
            if action_type == 'live_chat':
                # 1. Grab the owner of this specific chatbot
                owner = get_user_by_id(chatbot.user_id)

                # 2. Check if the owner is paying for premium features
                is_premium = owner.subscription and owner.subscription.plan and 'free' not in owner.subscription.plan.name.lower()

                if is_premium:
                    # ALLOW: Turn on Live Chat
                    if chat_session:
                        chat_session.is_live = True
                        chat_session.status = 'human'
                        db.session.commit()
                        is_live_mode = True

                    send_live_chat_email(owner=owner, chatbot=chatbot, session_id=session_id)
                    seed_msg = LiveChatMessage(session_id=session_id, sender_role='user',
                                               message=' User requested live support ', is_read=False)
                    db.session.add(seed_msg)
                    db.session.commit()

                    bot_response = action_value if action_value else "Please hold on — connecting you to a live representative."
                else:
                    # DENY: The owner is on a free plan. Block the connection.
                    bot_response = "I'm sorry, but live agent support is currently unavailable for this chat."
                    is_live_mode = False

                user_message = "Requested Live Chat"  # Overwrites the ugly system message so it logs cleanly
                intent = 'live_chat_request'
                confidence = 1.0
                is_fallback = False

            # ★ USER ENDS LIVE CHAT ★
            elif action_type == 'end_live_chat':
                if chat_session:
                    chat_session.is_live = False
                    chat_session.status = 'bot'
                    db.session.commit()
                    is_live_mode = False

                bot_response = "Live chat ended. The AI assistant has resumed. How else can I help you today?"
                user_message = "User ended live chat"
                intent = 'end_live_chat'
                confidence = 1.0
                is_fallback = False

            # Normal Button Action
            else:
                bot_response = process_button_action(action_type, action_value, chatbot)
                user_message = f"[Button: {button_action.get('text', action_value)}]"
                intent = f'button_{action_type}'
                confidence = 0.95
                is_fallback = False

        # ── Free-text message ──────────────────────────────────────
        else:
            if is_live_mode:
                bot_response = ""
                intent = 'live_chat_ongoing'
                confidence = 1.0
                is_fallback = False
            else:
                try:
                    from base.com.utils.utils import get_smart_response, get_intent_with_confidence
                    bot_response = get_smart_response(
                        user_message, chatbot.user_id,
                        chatbot_id=chatbot.id,
                        session_id=str(session_id),
                        is_voice=is_voice
                    )
                    intent, confidence = get_intent_with_confidence(
                        user_message, chatbot.user_id, chatbot_id=chatbot.id
                    )
                    is_fallback = detect_fallback_response(bot_response, confidence)
                except Exception as e:
                    bot_response = "I'm here to help! Could you please rephrase your question?"
                    intent = 'unknown'
                    confidence = 0.0
                    is_fallback = True

        processing_time = int((time.time() - start_time) * 1000)

        # ── Persist analytics messages ─────────────────────────────
        try:
            log_message(
                session_id=session_id, sender='user',
                message=user_message, intent=intent or 'unknown',
                confidence=confidence
            )
            if bot_response:
                log_message(
                    session_id=session_id, sender='bot',
                    message=bot_response, intent=intent or 'unknown',
                    confidence=confidence, is_fallback=is_fallback,
                    processing_time=processing_time
                )
            if user.subscription:
                user.subscription.increment_message_count()
        except Exception as e:
            print(f"⚠️ Logging error: {e}")

        # ── Response ───────────────────────────────────────────────
        response_data = {
            'response': bot_response,
            'session_id': session_id,
            'intent': intent or 'unknown',
            'confidence': round(confidence, 2),
            'processing_time_ms': processing_time,
            'is_fallback': is_fallback,
            'chatbot_id': chatbot.id,
            'chatbot_name': chatbot.bot_name,
            'nested_buttons': next_nested_buttons,
            'is_live': is_live_mode,
        }

        if session_token:
            response_data['session_token'] = session_token

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ chat_api error: {e}")
        return jsonify({
            'error': 'Internal server error',
            'message': 'Sorry, something went wrong. Please try again.'
        }), 500

@app.route('/api/chat/<embed_code>/history', methods=['GET'])
def get_chat_history(embed_code):
    """Fetches the past chat history for a widget session when the page reloads."""
    from datetime import timezone

    def to_epoch(dt):
        if not dt:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    try:
        chatbot = get_chatbot_by_embed_code(embed_code)
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404

        session_id = request.args.get('session_id')
        if not session_id or session_id == 'null':
            return jsonify({'messages': [], 'is_live': False})

        chat_session = ChatSession.query.get(session_id)
        if not chat_session:
            return jsonify({'messages': [], 'is_live': False})

        from base.com.vo.session_vo import ChatMessage
        from base.com.vo.live_chat_vo import LiveChatMessage

        ai_msgs = ChatMessage.query.filter_by(session_id=session_id).all()
        live_msgs = LiveChatMessage.query.filter_by(session_id=session_id).all()

        history = []

        # 1. Grab AI / Standard messages
        for m in ai_msgs:
            history.append({
                'sender': m.sender,
                'message': m.message,
                'timestamp': to_epoch(m.timestamp)
            })

        # 2. Grab Live Chat messages
        for m in live_msgs:
            # Tell the widget the owner is the "bot" so it aligns on the left side
            sender = 'bot' if m.sender_role == 'owner' else 'user'
            history.append({
                'sender': sender,
                'message': m.message,
                'timestamp': to_epoch(m.timestamp)
            })

        # Sort all messages chronologically
        history.sort(key=lambda x: x['timestamp'])

        # Remove duplicate user messages (since they log in both tables during transition)
        deduped_history = []
        for msg in history:
            if deduped_history and deduped_history[-1]['sender'] == 'user' and msg['sender'] == 'user' and \
                    deduped_history[-1]['message'] == msg['message']:
                continue
            deduped_history.append(msg)

        return jsonify({
            'messages': deduped_history,
            'is_live': getattr(chat_session, 'is_live', False)
        })

    except Exception as e:
        print(f"❌ Error fetching chat history: {e}")
        return jsonify({'messages': [], 'is_live': False})