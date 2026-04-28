"""
Chatbot Controller — FIXED VERSION
Fixes:
  1. bot_detail redirect now passes chatbot_id  (was crashing on create)
  2. Added /data/users/<path> route to serve avatar images from disk
  3. Avatar path stored as /data/users/... matching the new serve route
  4. edit_chatbot_route redirects to bot_detail with chatbot_id after save
  5. _validate_buttons is now RECURSIVE to support infinite Nested Flow Builder
  6. Added 'live_chat' to valid_types to allow Live Agent transfers!
"""
from base import app, db
from flask import (render_template, request, redirect, url_for,
                   session, flash, jsonify, send_from_directory, abort)
from datetime import datetime, timezone
import secrets, json, os, time, base64, io, shutil
from PIL import Image
from base.com.controller.decorators import login_required
from base.com.vo.chatbot_vo import Chatbot
from base.com.vo.user_vo import User
from base.com.dao.user_dao import get_user_by_id
from base.com.dao.chat_dao import (
    get_chatbot_by_id, get_chatbots_by_user, create_chatbot,
    update_chatbot, delete_chatbot as delete_chatbot_dao,
    toggle_chatbot_status, count_chatbots_by_user, get_chatbot_by_embed_code
)
from base.com.service.file_service import get_chatbot_folder, ensure_chatbot_folder, allowed_file
from base.com.controller.decorators import subscription_required


# ================================================================
# FIX 1 — Serve avatar/user files stored under data/users/
# ================================================================
@app.route('/data/users/<path:filepath>')
def serve_user_file(filepath):
    """Serve user-uploaded files (avatars etc.) from the data/users folder."""
    base_dir = os.path.normpath(os.path.join(os.getcwd(), 'data', 'users'))
    full_path = os.path.normpath(os.path.join(base_dir, filepath))

    if not full_path.startswith(base_dir + os.sep):
        abort(403)

    if not os.path.exists(full_path):
        abort(404)

    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))


# ================================================================
# HELPER — process base64 avatar and save to chatbot folder
# ================================================================
def _save_avatar_from_b64(bot_avatar_data, user_id, chatbot_id):
    try:
        header, data = bot_avatar_data.split(',', 1)
        image = Image.open(io.BytesIO(base64.b64decode(data))).convert('RGBA')

        max_size = (500, 500)
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        chatbot_folder = os.path.normpath(os.path.join(
            'data', 'users', f'user_{user_id}',
            'chatbots', f'chatbot_{chatbot_id}'
        ))
        os.makedirs(chatbot_folder, exist_ok=True)

        file_path = os.path.normpath(os.path.join(chatbot_folder, 'avatar.png'))
        image.save(file_path, 'PNG')

        db_path = f"/data/users/user_{user_id}/chatbots/chatbot_{chatbot_id}/avatar.png"
        print(f"   ✅ Avatar saved → {db_path}")
        return db_path

    except Exception as e:
        print(f"   ❌ Avatar save error: {e}")
        return None


# ================================================================
# HELPER — validate & clean welcome buttons JSON (RECURSIVE)
# ================================================================
def _validate_buttons(raw_json):
    """
    Validates the welcome buttons JSON.
    Supports infinite recursive branching (nested_buttons) and
    automatically migrates legacy 'submenu_items'.
    """
    # ★ FIX: Added 'live_chat' so the backend accepts the Live Agent Transfer buttons!
    valid_types = ['url', 'intent', 'message', 'live_chat']

    try:
        buttons_list = json.loads(raw_json) if raw_json else []
        if not isinstance(buttons_list, list):
            return '[]'

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

            # Migrate legacy 'submenu_items' if they exist
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

            # Process infinite nested_buttons recursively
            nested = btn.get('nested_buttons', [])
            if isinstance(nested, list):
                for n_btn in nested:
                    valid_nested = clean_node(n_btn)  # Recursive call
                    if valid_nested:
                        cleaned['nested_buttons'].append(valid_nested)

            return cleaned

        result = []
        for button in buttons_list:
            valid_btn = clean_node(button)
            if valid_btn:
                result.append(valid_btn)

        return json.dumps(result)

    except Exception as e:
        print(f"   ❌ Button validation error: {e}")
        return '[]'


# ================================================================
# ROUTE — Bot detail
# ================================================================
@app.route('/bot/<int:chatbot_id>')
@login_required
def bot_detail(chatbot_id):
    # 1. Grab the currently logged-in user from the database
    user = get_user_by_id(session['user_id'])

    # 2. Get the chatbot
    chatbot = Chatbot.query.get_or_404(chatbot_id)

    # (Optional but recommended security check to ensure users can't view other people's bots)
    if chatbot.user_id != user.id:
        flash("Unauthorized access.", "error")
        return redirect(url_for('dashboard'))

    iframe_code = f'<iframe src="{request.host_url}embed/{chatbot.embed_code}" width="100%" height="600" frameborder="0"></iframe>'

    # 3. Pass the 'user' object to the template so the sidebar subscription check works!
    return render_template('bot_details.html', chatbot=chatbot, iframe_code=iframe_code, user=user)


# ================================================================
# ROUTE — Create chatbot
# ================================================================
@app.route('/chatbot/create', methods=['GET', 'POST'])
@login_required
@subscription_required
def create_chatbot_route():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])

    if user.subscription and not user.subscription.can_create_chatbot():
        max_limit = user.subscription.plan.max_chatbots
        limit_text = "unlimited" if max_limit == -1 else str(max_limit)
        flash(f'You have reached your chatbot limit ({limit_text}). Please upgrade your plan.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template('create_chatbot.html',
                               chatbots=get_chatbots_by_user(user.id), user=user)

    # ── POST ──
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        welcome_message = request.form.get('welcome_message', 'Hello! How can I help you?').strip()
        theme_color = request.form.get('theme_color', '#4F46E5')
        bot_name = request.form.get('bot_name', 'AI Assistant').strip()
        use_ml_model = request.form.get('use_ml_model') == 'on'

        if not name:
            flash('Chatbot name is required', 'error')
            return redirect(url_for('create_chatbot_route'))

        chat_background_color = request.form.get('chat_background_color', '#F7FAFC')
        user_message_color = request.form.get('user_message_color', theme_color)
        bot_message_color = request.form.get('bot_message_color', '#FFFFFF')
        user_text_color = request.form.get('user_text_color', '#FFFFFF')
        bot_text_color = request.form.get('bot_text_color', '#1A202C')

        # Run through the new recursive validator
        welcome_buttons = _validate_buttons(request.form.get('welcome_buttons', '[]'))

        # ── Create DB record first ──
        embed_code = secrets.token_urlsafe(16)
        new_chatbot = Chatbot(
            name=name, description=description,
            welcome_message=welcome_message, theme_color=theme_color,
            bot_name=bot_name, use_ml_model=use_ml_model,
            embed_code=embed_code, user_id=user.id,
            bot_avatar=None,
            chat_background_color=chat_background_color,
            user_message_color=user_message_color,
            bot_message_color=bot_message_color,
            user_text_color=user_text_color,
            bot_text_color=bot_text_color,
            welcome_buttons=welcome_buttons
        )
        db.session.add(new_chatbot)
        if user.subscription:
            user.subscription.increment_chatbot_count()
        db.session.commit()

        # ── Save avatar ──
        bot_avatar_data = request.form.get('bot_avatar_data', '').strip()
        if bot_avatar_data and bot_avatar_data.startswith('data:image'):
            db_path = _save_avatar_from_b64(bot_avatar_data, user.id, new_chatbot.id)
            if db_path:
                new_chatbot.bot_avatar = db_path
                db.session.commit()

        flash('Chatbot created successfully!', 'success')
        return redirect(url_for('bot_detail', chatbot_id=new_chatbot.id))

    except Exception as e:
        db.session.rollback()
        import traceback;
        traceback.print_exc()
        flash(f'Error creating chatbot: {str(e)}', 'error')
        return redirect(url_for('create_chatbot_route'))


# ================================================================
# ROUTE — Edit chatbot
# ================================================================
@app.route('/chatbot/edit/<int:chatbot_id>', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_chatbot_route(chatbot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    if request.method == 'POST':
        try:
            chatbot.name = request.form.get('name', '').strip()
            chatbot.bot_name = request.form.get('bot_name', '').strip()
            chatbot.description = request.form.get('description', '').strip()
            chatbot.welcome_message = request.form.get('welcome_message', '').strip()
            chatbot.theme_color = request.form.get('theme_color', '#4F46E5')
            chatbot.chat_background_color = request.form.get('chat_background_color', '#F7FAFC')
            chatbot.bot_message_color = request.form.get('bot_message_color', '#FFFFFF')
            chatbot.bot_text_color = request.form.get('bot_text_color', '#1A202C')
            chatbot.user_text_color = request.form.get('user_text_color', '#FFFFFF')

            remove_avatar_flag = request.form.get('remove_avatar', 'false')
            bot_avatar_data = request.form.get('bot_avatar_data', '').strip()

            if remove_avatar_flag == 'true':
                if chatbot.bot_avatar and chatbot.bot_avatar.startswith('/data/users/'):
                    rel = chatbot.bot_avatar.lstrip('/')
                    old = os.path.normpath(os.path.join(os.getcwd(), rel))
                    if os.path.exists(old):
                        try:
                            os.remove(old)
                        except Exception as e:
                            pass
                chatbot.bot_avatar = None

            elif bot_avatar_data and bot_avatar_data.startswith('data:image'):
                if chatbot.bot_avatar and chatbot.bot_avatar.startswith('/data/users/'):
                    rel = chatbot.bot_avatar.lstrip('/')
                    old = os.path.normpath(os.path.join(os.getcwd(), rel))
                    if os.path.exists(old):
                        try:
                            os.remove(old)
                        except Exception as e:
                            pass

                db_path = _save_avatar_from_b64(bot_avatar_data, chatbot.user_id, chatbot_id)
                if db_path:
                    chatbot.bot_avatar = db_path

            chatbot.use_ml_model = request.form.get('use_ml_model') == 'on'
            chatbot.updated_at = datetime.now(timezone.utc)
            db.session.commit()

            flash('Chatbot updated successfully!', 'success')
            return redirect(url_for('bot_detail', chatbot_id=chatbot_id))

        except Exception as e:
            db.session.rollback()
            import traceback;
            traceback.print_exc()
            flash(f'Error updating chatbot: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('bot_details.html', chatbot=chatbot, chatbots=chatbots, user=user)


# ================================================================
# ROUTE — Delete chatbot
# ================================================================
# ================================================================
# ROUTE — Delete chatbot
# ================================================================
@app.route('/chatbot/delete/<int:chatbot_id>')
@login_required
@subscription_required
def delete_chatbot_route(chatbot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])
    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    try:
        # 1. Delete legacy training files if they exist
        if chatbot.training_file:
            fp = os.path.join(app.config.get('UPLOAD_FOLDER', ''), chatbot.training_file)
            if os.path.exists(fp):
                os.remove(fp)

        # 2. Delete ALL related Database Records (Sessions, Live Chats, QA Pairs)
        from base.com.vo.session_vo import ChatSession
        from base.com.vo.live_chat_vo import LiveChatMessage
        from base.com.vo.qa_pair_vo import QAPair

        # Delete all Q&A pairs related to this bot
        QAPair.query.filter_by(chatbot_id=chatbot.id).delete()

        # Delete all live chat messages and the sessions themselves
        sessions = ChatSession.query.filter_by(chatbot_id=chatbot.id).all()
        for s in sessions:
            LiveChatMessage.query.filter_by(session_id=s.id).delete()
            db.session.delete(s)

        # 3. Delete the physical folder from the server (Avatars, JSON files, etc.)
        chatbot_folder = os.path.normpath(os.path.join(
            os.getcwd(), 'data', 'users', f'user_{user.id}', 'chatbots', f'chatbot_{chatbot.id}'
        ))
        if os.path.exists(chatbot_folder):
            import shutil
            shutil.rmtree(chatbot_folder)

        # 4. Clear the bot from the server's RAM/Cache
        try:
            from utils import clear_model_cache
            clear_model_cache(user.id, chatbot.id)
        except Exception:
            pass

        # 5. Delete the actual Chatbot record
        db.session.delete(chatbot)

        # 6. Update user subscription limits
        if user.subscription:
            user.subscription.decrement_chatbot_count()

        # Commit all deletions to the database
        db.session.commit()
        flash('Chatbot and all associated data deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(f'Error deleting chatbot: {str(e)}', 'error')

    return redirect(url_for('dashboard'))


# ================================================================
# ROUTE — Toggle active status
# ================================================================
@app.route('/chatbot/toggle/<int:chatbot_id>')
@login_required
@subscription_required
def toggle_chatbot_route(chatbot_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    chatbot.is_active = not chatbot.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': chatbot.is_active})


# ================================================================
# ROUTE — Preview chatbot
# ================================================================
@app.route('/chatbot/preview/<int:chatbot_id>')
@login_required
@subscription_required
def preview_chatbot(chatbot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))
    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    welcome_buttons_data = []
    if chatbot.welcome_buttons:
        try:
            welcome_buttons_data = json.loads(chatbot.welcome_buttons)
        except json.JSONDecodeError:
            pass

    bot_avatar_url = None
    if chatbot.bot_avatar:
        path = chatbot.bot_avatar.strip()
        base = request.url_root.rstrip('/')
        bot_avatar_url = path if path.startswith(('http://', 'https://')) else base + path

    return render_template(
        'preview_chatbot.html',
        chatbot=chatbot, chatbots=chatbots, user=user,
        welcome_buttons=welcome_buttons_data,
        bot_avatar_url=bot_avatar_url
    )


# ================================================================
# ROUTE — Deploy chatbot
# ================================================================
@app.route('/chatbot/deploy/<int:chatbot_id>')
@login_required
@subscription_required
def deploy_chatbot(chatbot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # Check if the chatbot is ALREADY active
    if chatbot.is_active:
        # It's already deployed. Show a gentle info message (or remove this flash if you prefer silence)
        flash('Chatbot is already deployed and active.', 'info')
    else:
        # It's NOT active yet. Deploy it!
        chatbot.is_active = True
        db.session.commit()
        flash('Chatbot deployed successfully!', 'success')

    return redirect(url_for('deploy_page', chatbot_id=chatbot_id))


@app.route('/chatbot/deploy/<int:chatbot_id>/view')
@login_required
@subscription_required
def deploy_page(chatbot_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)
    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    URL = "http://127.0.0.1:5000"
    embed_url = f"{URL}/embed/{chatbot.embed_code}"
    iframe_code = (
        f'<iframe src="{embed_url}" width="400" height="600" frameborder="0" '
        f'style="border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,0.15);"></iframe>'
    )

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    return render_template(
        'deploy_chatbot.html',
        chatbot=chatbot,
        iframe_code=iframe_code,
        chatbots=chatbots,
        user=user
    )


print("✅ Chatbot controller loaded successfully!")


# ================================================================
# ROUTE — Save Interactive Flow (AJAX from Train Page)
# ================================================================
@app.route('/chatbot/save-flow/<int:chatbot_id>', methods=['POST'])
@login_required
def save_flow_route(chatbot_id):
    """
    Saves the Interactive Flow Builder data directly to the chatbot's
    welcome_buttons column without reloading the page.
    """
    chatbot = get_chatbot_by_id(chatbot_id)

    # 1. Security Check
    if not chatbot or chatbot.user_id != session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # 2. Get the JSON payload from the frontend fetch request
        data = request.get_json()
        raw_flow = data.get('flow_data', [])

        # 3. We convert it to a string and run it through the exact same
        # recursive validator we built earlier so it stays perfectly formatted
        validated_json_string = _validate_buttons(json.dumps(raw_flow))

        # 4. Save to the database
        chatbot.welcome_buttons = validated_json_string
        chatbot.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        print(f"✅ Interactive Flow saved for Chatbot ID: {chatbot.id}")

        return jsonify({
            'success': True,
            'message': 'Flow saved successfully!'
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        print(f"❌ Error saving flow: {e}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500


@app.route('/chatbot/train/<int:chatbot_id>', methods=['GET'])
@login_required
def train_chatbot_route(chatbot_id):
    # 1. Grab the logged-in user so the sidebar knows their subscription tier!
    user = get_user_by_id(session['user_id'])

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # 2. Pass user=user to the template
    return render_template('train_chatbot.html', chatbot=chatbot, user=user)