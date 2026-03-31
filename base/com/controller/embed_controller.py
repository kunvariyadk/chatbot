"""
Embed Controller
Handles chatbot embedding and public chat API
"""
from base import app, db
from flask import render_template, request, jsonify
import json
import time
from datetime import datetime, timezone

from base.com.vo.user_vo import User
from base.com.vo.chatbot_vo import Chatbot
from base.com.dao.chat_dao import get_chatbot_by_embed_code
from base.com.dao.session_dao import create_session, log_message
from base.com.controller.decorators import login_required


def get_avatar_url(chatbot, request):
    """Get avatar URL for chatbot"""
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
    """Enhanced fallback detection"""
    if not response:
        return True

    response_lower = response.lower()
    valid_response_indicators = [
        'hello', 'hi', 'hey', 'welcome', 'thank you', 'you\'re welcome',
        'goodbye', 'bye', 'see you', 'my name is', 'i am', 'i can help',
        'here\'s', 'here is', 'the answer', 'according to', 'based on',
        'doing great', 'functioning', 'here to help', 'glad', 'happy to'
    ]

    for indicator in valid_response_indicators:
        if indicator in response_lower:
            return False

    if confidence > 0.40:
        return False

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
        if indicator in response_lower:
            return True

    if confidence < 0.05:
        return True

    return False


def process_button_action(action_type, action_value, chatbot):
    """Handle button actions"""
    try:
        print(f"\n{'=' * 70}")
        print(f"🔘 BUTTON ACTION HANDLER")
        print(f"   Type: {action_type}")
        print(f"   Value: {action_value}")
        print(f"{'=' * 70}")

        if action_type == 'url':
            if action_value and action_value.strip():
                return f"🔗 Opening: {action_value}"
            return "❌ No URL provided."

        elif action_type == 'intent':
            print(f"   🎯 Intent Action: {action_value}")
            try:
                from base.com.utils.utils import get_response_from_kb
                response = get_response_from_kb(action_value.lower().strip(), chatbot.user_id, chatbot_id=chatbot.id)
                if response:
                    return response
                return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"
            except Exception as e:
                print(f"   ❌ Error getting KB response: {e}")
                return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"

        elif action_type == 'message':
            message_text = action_value.strip()
            if not message_text:
                return "No message provided."

            # Direct return of the bot's configured reply message
            return message_text

        else:
            return "Please select an option from the menu."

    except Exception as e:
        print(f"❌ Button handler error: {e}")
        return "I encountered an error. Please try selecting again."


# ============================================
# EMBED ROUTES
# ============================================

@app.route('/embed/<embed_code>')
# REMOVED @login_required here so the public can see the live widget!
def embed_chatbot(embed_code):
    """Embed route for public chatbot access"""
    print(f"\n{'=' * 70}")
    print(f"🔗 EMBED ROUTE CALLED")
    print(f"   Embed Code: {embed_code}")
    print(f"{'=' * 70}\n")

    chatbot = get_chatbot_by_embed_code(embed_code)

    if not chatbot:
        return render_template('embed_error.html', error="Chatbot not found",
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
        'embed.html',
        chatbot=chatbot,
        settings=chatbot_settings,
        welcome_buttons=welcome_buttons_data,
        bot_avatar_url=bot_avatar_url
    )


@app.route('/api/chat/<embed_code>', methods=['POST'])
def chat_api(embed_code):
    """Chat API for embedded chatbots"""
    start_time = time.time()

    try:
        chatbot = get_chatbot_by_embed_code(embed_code)
        if not chatbot:
            return jsonify({'error': 'Chatbot not found'}), 404

        user = User.query.get(chatbot.user_id)
        if not user or not user.subscription:
            return jsonify({'error': 'Service unavailable'}), 503

        if not user.subscription.can_send_message():
            return jsonify({'error': 'Message limit reached',
                            'message': 'The chatbot owner has reached their monthly message limit.'}), 429

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        button_action = data.get('button_action')
        is_voice = data.get('is_voice', False)

        # 🌟 NEW: Capture nested buttons if the user clicked a branch!
        next_nested_buttons = []

        if not user_message and not button_action:
            return jsonify({'error': 'Empty message'}), 400

        if not session_id:
            user_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', 'Unknown')
            session_id, session_token = create_session(chatbot_id=chatbot.id, ip=user_ip, user_agent=user_agent)
        else:
            session_token = None

        if button_action:
            action_type = button_action.get('type')
            action_value = button_action.get('value')

            # Extract the nested branches to send back to the user!
            next_nested_buttons = button_action.get('nested_buttons', [])

            bot_response = process_button_action(action_type, action_value, chatbot)
            user_message = f"[Button: {button_action.get('text', action_value)}]"
            intent = f'button_{action_type}'
            confidence = 0.95
            is_fallback = False
        else:
            try:
                from base.com.utils.utils import get_smart_response, get_intent_with_confidence

                bot_response = get_smart_response(
                    user_message, chatbot.user_id, chatbot_id=chatbot.id,
                    session_id=str(session_id), is_voice=is_voice
                )
                intent, confidence = get_intent_with_confidence(user_message, chatbot.user_id, chatbot_id=chatbot.id)
                is_fallback = detect_fallback_response(bot_response, confidence)

            except Exception as e:
                print(f"❌ Response generation error: {e}")
                bot_response = "I'm here to help! Could you please rephrase your question?"
                intent = 'unknown'
                confidence = 0.0
                is_fallback = True

        processing_time = int((time.time() - start_time) * 1000)

        try:
            log_message(session_id=session_id, sender='user', message=user_message, intent=intent or 'unknown',
                        confidence=confidence)
            log_message(session_id=session_id, sender='bot', message=bot_response, intent=intent or 'unknown',
                        confidence=confidence, is_fallback=is_fallback, processing_time=processing_time)

            if user.subscription:
                user.subscription.increment_message_count()
        except Exception as e:
            print(f"⚠️ Logging error: {e}")

        response_data = {
            'response': bot_response,
            'session_id': session_id,
            'intent': intent or 'unknown',
            'confidence': round(confidence, 2),
            'processing_time_ms': processing_time,
            'is_fallback': is_fallback,
            'chatbot_id': chatbot.id,
            'chatbot_name': chatbot.bot_name,
            'nested_buttons': next_nested_buttons  # 🌟 NEW: Sending nested options back to the frontend!
        }

        if session_token:
            response_data['session_token'] = session_token

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ CHAT API ERROR: {str(e)}")
        return jsonify(
            {'error': 'Internal server error', 'message': 'Sorry, something went wrong. Please try again.'}), 500


print("✅ Embed controller loaded successfully!")
# """
# Embed Controller
# Handles chatbot embedding and public chat API
# """
# from base import app, db
# from flask import render_template, request, jsonify
# import json
# import time
# from datetime import datetime, timezone
#
# from base.com.vo.user_vo import User
# from base.com.vo.chatbot_vo import Chatbot
# from base.com.dao.chat_dao import get_chatbot_by_embed_code
# from base.com.dao.session_dao import create_session, log_message
# from base.com.controller.decorators import login_required
#
# def get_avatar_url(chatbot, request):
#     """Get avatar URL for chatbot"""
#     if not chatbot.bot_avatar:
#         return None
#
#     avatar_path = chatbot.bot_avatar.strip()
#     base_url = request.url_root.rstrip('/')
#
#     # Case 1: Already a full URL
#     if avatar_path.startswith(('http://', 'https://')):
#         return avatar_path
#
#     # Case 2: Path starts with /data/users/
#     if avatar_path.startswith('/data/users/'):
#         return base_url + avatar_path
#
#     # Case 3: Path starts with /static/
#     if avatar_path.startswith('/static/'):
#         return base_url + avatar_path
#
#     # Case 4: Relative path
#     if not avatar_path.startswith('/'):
#         avatar_path = f"/data/users/user_{chatbot.user_id}/chatbots/chatbot_{chatbot.id}/{avatar_path}"
#
#     return base_url + avatar_path
#
#
# def detect_fallback_response(response: str, confidence: float) -> bool:
#     """Enhanced fallback detection"""
#     if not response:
#         return True
#
#     response_lower = response.lower()
#
#     # Valid response indicators
#     valid_response_indicators = [
#         'hello', 'hi', 'hey', 'welcome', 'thank you', 'you\'re welcome',
#         'goodbye', 'bye', 'see you', 'my name is', 'i am', 'i can help',
#         'here\'s', 'here is', 'the answer', 'according to', 'based on',
#         'doing great', 'functioning', 'here to help', 'glad', 'happy to'
#     ]
#
#     for indicator in valid_response_indicators:
#         if indicator in response_lower:
#             return False
#
#     if confidence > 0.40:
#         return False
#
#     # Fallback indicators
#     fallback_indicators = [
#         "didn't fully understand", "may have missed", "could you clarify",
#         "explain it differently", "could you please rephrase", "provide more context",
#         "still learning", "don't have that information", "unable to help with that",
#         "outside my current capabilities", "don't have access to that",
#         "not in my current knowledge", "try asking in another way",
#         "use simpler or more specific", "break your request into smaller",
#         "let me know what outcome", "try a different approach", "try rephrasing",
#         "couldn't process that request", "something went wrong",
#         "had trouble with that", "give it another shot", "try again",
#         "connect with a support representative", "contact our support team",
#         "reach a human agent", "reaching out to our support",
#         "didn't catch that", "please repeat", "one more time",
#         "not entirely confident", "need more information", "could you elaborate",
#         "understand your question, but don't have", "not in my current knowledge base",
#         "that topic isn't covered", "don't have details about that",
#         "rate limit exceeded", "configuration error", "chatbot id is required"
#     ]
#
#     for indicator in fallback_indicators:
#         if indicator in response_lower:
#             return True
#
#     if confidence < 0.05:
#         return True
#
#     return False
#
#
# def process_button_action(action_type, action_value, chatbot):
#     """Handle button actions"""
#     try:
#         print(f"\n{'=' * 70}")
#         print(f"🔘 BUTTON ACTION HANDLER")
#         print(f"   Type: {action_type}")
#         print(f"   Value: {action_value}")
#         print(f"{'=' * 70}")
#
#         # URL - Open external link
#         if action_type == 'url':
#             if action_value and action_value.strip():
#                 return f"🔗 Opening: {action_value}"
#             return "❌ No URL provided."
#
#         # Submenu - Show submenu options
#         elif action_type == 'submenu':
#             return "Please select an option from the menu above."
#
#         # Intent - Direct knowledge base lookup
#         elif action_type == 'intent':
#             print(f"   🎯 Intent Action: {action_value}")
#
#             try:
#                 from utils import get_response_from_kb
#                 response = get_response_from_kb(
#                     action_value.lower().strip(),
#                     chatbot.user_id,
#                     chatbot_id=chatbot.id
#                 )
#
#                 if response:
#                     return response
#
#                 return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"
#             except Exception as e:
#                 print(f"   ❌ Error getting KB response: {e}")
#                 return f"I can help you with {action_value.replace('_', ' ')}. What would you like to know?"
#
#         # Message - Smart response
#         elif action_type == 'message':
#             message_text = action_value.strip()
#
#             if not message_text:
#                 return "No message provided."
#
#             # If it's a statement/answer, return directly
#             if not any(message_text.lower().startswith(q) for q in
#                        ['what', 'who', 'when', 'where', 'why', 'how', 'is', 'are', 'can', 'do', 'does']):
#                 return message_text
#
#             # Otherwise treat as query
#             try:
#                 from utils import get_smart_response
#                 response = get_smart_response(
#                     message_text,
#                     chatbot.user_id,
#                     chatbot_id=chatbot.id,
#                     session_id=None
#                 )
#
#                 if response:
#                     return response
#             except Exception as e:
#                 print(f"   ❌ Error getting smart response: {e}")
#
#             return message_text
#
#         else:
#             return "Please select an option from the menu."
#
#     except Exception as e:
#         print(f"❌ Button handler error: {e}")
#         import traceback
#         traceback.print_exc()
#         return "I encountered an error. Please try selecting again."
#
#
# # ============================================
# # EMBED ROUTES
# # ============================================
#
# @app.route('/embed/<embed_code>')
# @login_required
# def embed_chatbot(embed_code):
#     """Embed route for public chatbot access"""
#     print(f"\n{'=' * 70}")
#     print(f"🔗 EMBED ROUTE CALLED")
#     print(f"   Embed Code: {embed_code}")
#     print(f"{'=' * 70}\n")
#
#     chatbot = get_chatbot_by_embed_code(embed_code)
#
#     if not chatbot:
#         print(f"❌ Chatbot not found: {embed_code}")
#         return render_template('embed_error.html',
#                                error="Chatbot not found",
#                                message="This chatbot may have been removed or the link is incorrect."), 404
#
#     if not chatbot.is_active:
#         print(f"❌ Chatbot not active: {chatbot.name}")
#         return render_template('embed.html',
#                                error="Chatbot unavailable",
#                                message="This chatbot is currently inactive."), 403
#
#     print(f"✅ Chatbot found: {chatbot.name} (ID: {chatbot.id})")
#
#     # Parse welcome buttons
#     welcome_buttons_data = []
#     if chatbot.welcome_buttons:
#         try:
#             welcome_buttons_data = json.loads(chatbot.welcome_buttons)
#         except json.JSONDecodeError as e:
#             print(f"⚠️ Error parsing welcome buttons: {e}")
#             welcome_buttons_data = []
#
#     # Get avatar URL
#     bot_avatar_url = get_avatar_url(chatbot, request)
#
#     # Prepare settings
#     chatbot_settings = {
#         'embedCode': chatbot.embed_code,
#         'botName': chatbot.bot_name or 'AI Assistant',
#         'welcomeMessage': chatbot.welcome_message or 'Hello! How can I help you?',
#         'themeColor': chatbot.theme_color or '#4F46E5',
#         'chatBackgroundColor': chatbot.chat_background_color or '#F7FAFC',
#         'botMessageColor': chatbot.bot_message_color or '#FFFFFF',
#         'botTextColor': chatbot.bot_text_color or '#1A202C',
#         'userMessageColor': chatbot.user_message_color or (chatbot.theme_color or '#4F46E5'),
#         'userTextColor': chatbot.user_text_color or '#FFFFFF',
#         'botAvatar': bot_avatar_url,
#         'welcomeButtons': welcome_buttons_data
#     }
#
#     return render_template(
#         'embed.html',
#         chatbot=chatbot,
#         settings=chatbot_settings,
#         welcome_buttons=welcome_buttons_data,
#         bot_avatar_url=bot_avatar_url
#     )
#
#
# @app.route('/api/chat/<embed_code>', methods=['POST'])
# @login_required
# def chat_api(embed_code):
#     """Chat API for embedded chatbots"""
#     start_time = time.time()
#
#     try:
#         # Validate chatbot
#         chatbot = get_chatbot_by_embed_code(embed_code)
#
#         if not chatbot:
#             return jsonify({'error': 'Chatbot not found'}), 404
#
#         user = User.query.get(chatbot.user_id)
#         if not user or not user.subscription:
#             return jsonify({'error': 'Service unavailable'}), 503
#
#         # Check subscription limits
#         if not user.subscription.can_send_message():
#             return jsonify({
#                 'error': 'Message limit reached',
#                 'message': 'The chatbot owner has reached their monthly message limit.'
#             }), 429
#
#         # Parse request
#         data = request.get_json()
#         if not data:
#             return jsonify({'error': 'No data provided'}), 400
#
#         user_message = data.get('message', '').strip()
#         session_id = data.get('session_id')
#         button_action = data.get('button_action')
#         is_voice = data.get('is_voice', False)
#
#         print(f"\n{'=' * 70}")
#         print(f"💬 CHAT API REQUEST")
#         print(f"   Chatbot: {chatbot.name} (ID: {chatbot.id})")
#         print(f"   User ID: {chatbot.user_id}")
#         print(f"   Message: {user_message[:50] if user_message else 'N/A'}...")
#         print(f"   Session: {session_id}")
#         print(f"{'=' * 70}\n")
#
#         if not user_message and not button_action:
#             return jsonify({'error': 'Empty message'}), 400
#
#         # Session management
#         if not session_id:
#             user_ip = request.remote_addr
#             user_agent = request.headers.get('User-Agent', 'Unknown')
#             session_id, session_token = create_session(
#                 chatbot_id=chatbot.id,
#                 ip=user_ip,
#                 user_agent=user_agent
#             )
#         else:
#             session_token = None
#
#         # Handle button action
#         if button_action:
#             action_type = button_action.get('type')
#             action_value = button_action.get('value')
#
#             bot_response = process_button_action(action_type, action_value, chatbot)
#             user_message = f"[Button: {button_action.get('text', action_value)}]"
#             intent = f'button_{action_type}'
#             confidence = 0.95
#             is_fallback = False
#         else:
#             # Get AI response
#             try:
#                 # ✅ IMPORT FROM ROOT utils.py
#                 from base.com.utils.utils import get_smart_response, get_intent_with_confidence
#
#                 print(f"   🤖 Calling get_smart_response...")
#                 print(f"      User ID: {chatbot.user_id}")
#                 print(f"      Chatbot ID: {chatbot.id}")
#
#                 bot_response = get_smart_response(
#                     user_message,
#                     chatbot.user_id,
#                     chatbot_id=chatbot.id,
#                     session_id=str(session_id),
#                     is_voice=is_voice
#                 )
#
#                 intent, confidence = get_intent_with_confidence(
#                     user_message,
#                     chatbot.user_id,
#                     chatbot_id=chatbot.id
#                 )
#
#                 print(f"   ✅ Response generated: '{bot_response[:50]}...'")
#                 print(f"   📊 Intent: {intent}, Confidence: {confidence:.2%}")
#
#                 is_fallback = detect_fallback_response(bot_response, confidence)
#
#             except Exception as e:
#                 print(f"❌ Response generation error: {e}")
#                 import traceback
#                 traceback.print_exc()
#
#                 bot_response = "I'm here to help! Could you please rephrase your question?"
#                 intent = 'unknown'
#                 confidence = 0.0
#                 is_fallback = True
#
#         # Log conversation
#         processing_time = int((time.time() - start_time) * 1000)
#
#         try:
#             log_message(
#                 session_id=session_id,
#                 sender='user',
#                 message=user_message,
#                 intent=intent or 'unknown',
#                 confidence=confidence
#             )
#
#             log_message(
#                 session_id=session_id,
#                 sender='bot',
#                 message=bot_response,
#                 intent=intent or 'unknown',
#                 confidence=confidence,
#                 is_fallback=is_fallback,
#                 processing_time=processing_time
#             )
#
#             # Increment message counter
#             if user.subscription:
#                 user.subscription.increment_message_count()
#
#         except Exception as e:
#             print(f"⚠️ Logging error: {e}")
#
#         # Return response
#         response_data = {
#             'response': bot_response,
#             'session_id': session_id,
#             'intent': intent or 'unknown',
#             'confidence': round(confidence, 2),
#             'processing_time_ms': processing_time,
#             'is_fallback': is_fallback,
#             'chatbot_id': chatbot.id,
#             'chatbot_name': chatbot.bot_name
#         }
#
#         if session_token:
#             response_data['session_token'] = session_token
#
#         print(f"✅ Response sent ({processing_time}ms)\n")
#         return jsonify(response_data)
#
#     except Exception as e:
#         print(f"❌ CHAT API ERROR: {str(e)}")
#         import traceback
#         traceback.print_exc()
#
#         return jsonify({
#             'error': 'Internal server error',
#             'message': 'Sorry, something went wrong. Please try again.'
#         }), 500
#
#
# print("✅ Embed controller loaded successfully!")