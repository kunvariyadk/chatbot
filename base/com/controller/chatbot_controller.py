"""
Chatbot Controller
Handles chatbot creation, editing, deletion, preview, and deployment
"""
from base import app, db
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timezone
import secrets
import json
import os
import time
import base64
import io
from PIL import Image
import shutil

from base.com.vo.chatbot_vo import Chatbot
from base.com.vo.user_vo import User
from base.com.dao.user_dao import get_user_by_id
from base.com.dao.chat_dao import (
    get_chatbot_by_id,
    get_chatbots_by_user,
    create_chatbot,
    update_chatbot,
    delete_chatbot as delete_chatbot_dao,
    toggle_chatbot_status,
    count_chatbots_by_user,
    get_chatbot_by_embed_code
)
from base.com.service.file_service import (
    get_chatbot_folder,
    ensure_chatbot_folder,
    allowed_file
)
from base.com.controller.decorators import subscription_required


# ============================================
# CHATBOT CRUD ROUTES
# ============================================

@app.route('/chatbot/create', methods=['GET', 'POST'])
@subscription_required
def create_chatbot_route():
    """Create a new chatbot"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])

    # Check subscription limits
    if user.subscription and not user.subscription.can_create_chatbot():
        max_limit = user.subscription.plan.max_chatbots
        limit_text = "unlimited" if max_limit == -1 else str(max_limit)
        flash(f'You have reached your chatbot limit ({limit_text}). Please upgrade your plan.', 'error')
        return redirect(url_for('subscription_plans'))

    # GET request - Show form
    if request.method == 'GET':
        chatbots = get_chatbots_by_user(user.id)
        return render_template('create_chatbot.html', chatbots=chatbots, user=user)

    # POST request - Create chatbot
    try:
        # Get basic form data
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        welcome_message = request.form.get('welcome_message', 'Hello! How can I help you?').strip()
        theme_color = request.form.get('theme_color', '#4F46E5')
        bot_name = request.form.get('bot_name', 'AI Assistant').strip()
        use_ml_model = request.form.get('use_ml_model') == 'on'

        # Validate required fields
        if not name:
            flash('Chatbot name is required', 'error')
            return redirect(url_for('create_chatbot_route'))

        # Get color settings
        chat_background_color = request.form.get('chat_background_color', '#F7FAFC')
        user_message_color = request.form.get('user_message_color', theme_color)
        bot_message_color = request.form.get('bot_message_color', '#FFFFFF')
        user_text_color = request.form.get('user_text_color', '#FFFFFF')
        bot_text_color = request.form.get('bot_text_color', '#1A202C')

        print(f"\n{'=' * 70}")
        print(f"🤖 CREATE CHATBOT")
        print(f"   Name: {name}")
        print(f"   User ID: {user.id}")
        print(f"{'=' * 70}")

        # Process welcome buttons
        welcome_buttons_json = request.form.get('welcome_buttons', '[]')
        validated_buttons = []

        try:
            buttons_list = json.loads(welcome_buttons_json) if welcome_buttons_json else []

            if not isinstance(buttons_list, list):
                buttons_list = []

            valid_types = ['url', 'intent', 'message', 'submenu']

            for idx, button in enumerate(buttons_list):
                if not isinstance(button, dict):
                    continue

                button_text = button.get('text', '').strip()
                button_type = button.get('type', 'url').strip()
                button_value = button.get('value', '').strip()
                has_submenu = button.get('has_submenu', False)
                submenu_items = button.get('submenu_items', [])

                if not button_text:
                    continue

                if button_type not in valid_types:
                    button_type = 'url'

                validated_button = {
                    'text': button_text,
                    'type': button_type,
                    'value': button_value,
                    'has_submenu': has_submenu
                }

                # Validate submenu items
                if has_submenu and isinstance(submenu_items, list):
                    validated_submenu = []
                    for sub_item in submenu_items:
                        if isinstance(sub_item, dict):
                            sub_text = sub_item.get('text', '').strip()
                            sub_type = sub_item.get('type', 'url').strip()
                            sub_value = sub_item.get('value', '').strip()

                            if sub_text:
                                if sub_type not in valid_types:
                                    sub_type = 'url'

                                validated_submenu.append({
                                    'text': sub_text,
                                    'type': sub_type,
                                    'value': sub_value
                                })

                    validated_button['submenu_items'] = validated_submenu
                else:
                    validated_button['submenu_items'] = []

                validated_buttons.append(validated_button)

            welcome_buttons = json.dumps(validated_buttons)

        except json.JSONDecodeError as e:
            print(f"   ❌ JSON error: {e}")
            welcome_buttons = '[]'
            validated_buttons = []

        # Process avatar (Base64)
        bot_avatar = None
        bot_avatar_data = request.form.get('bot_avatar_data', '').strip()

        if bot_avatar_data and bot_avatar_data.startswith('data:image'):
            try:
                # Parse base64
                header, data = bot_avatar_data.split(',', 1)
                image_data = base64.b64decode(data)
                image = Image.open(io.BytesIO(image_data))
                image = image.convert('RGBA')

                # Resize if needed
                max_size = (500, 500)
                if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save to temp folder
                temp_folder = os.path.join('data', 'temp')
                os.makedirs(temp_folder, exist_ok=True)

                timestamp = str(int(time.time() * 1000))
                unique_filename = f"avatar_temp_{user.id}_{timestamp}.png"
                temp_path = os.path.join(temp_folder, unique_filename)
                temp_path = os.path.normpath(temp_path)

                # Save image
                image.save(temp_path, 'PNG')

                if not os.path.exists(temp_path):
                    raise Exception(f"Failed to save temp avatar to {temp_path}")

                bot_avatar = f"temp:{unique_filename}"
                print(f"   ✅ Temp avatar saved: {bot_avatar}")

            except Exception as e:
                print(f"   ❌ Avatar processing error: {e}")
                flash('Error processing avatar image. Please try again.', 'error')
                bot_avatar = None

        # Create chatbot in database
        embed_code = secrets.token_urlsafe(16)

        new_chatbot = Chatbot(
            name=name,
            description=description,
            welcome_message=welcome_message,
            theme_color=theme_color,
            bot_name=bot_name,
            use_ml_model=use_ml_model,
            embed_code=embed_code,
            user_id=user.id,
            bot_avatar=bot_avatar,
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

        print(f"   ✅ Chatbot created in database (ID: {new_chatbot.id})")

        # Move temp avatar to chatbot folder
        if bot_avatar and bot_avatar.startswith('temp:'):
            temp_filename = bot_avatar.replace('temp:', '')
            temp_folder = os.path.join('data', 'temp')
            old_path = os.path.join(temp_folder, temp_filename)
            old_path = os.path.normpath(old_path)

            if os.path.exists(old_path):
                try:
                    chatbot_folder = os.path.join(
                        'data', 'users', f'user_{new_chatbot.user_id}',
                        'chatbots', f'chatbot_{new_chatbot.id}'
                    )
                    chatbot_folder = os.path.normpath(chatbot_folder)
                    os.makedirs(chatbot_folder, exist_ok=True)

                    new_filename = "avatar.png"
                    new_path = os.path.join(chatbot_folder, new_filename)
                    new_path = os.path.normpath(new_path)

                    shutil.move(old_path, new_path)

                    if os.path.exists(new_path):
                        db_path = f"/data/users/user_{new_chatbot.user_id}/chatbots/chatbot_{new_chatbot.id}/{new_filename}"
                        new_chatbot.bot_avatar = db_path
                        db.session.commit()
                        print(f"   ✅ Avatar moved successfully")

                except Exception as e:
                    print(f"   ❌ Error moving avatar: {e}")
                    new_chatbot.bot_avatar = None
                    db.session.commit()

        print(f"\n{'=' * 70}")
        print(f"✅ CHATBOT CREATION COMPLETE!")
        print(f"   ID: {new_chatbot.id}")
        print(f"   Name: {new_chatbot.name}")
        print(f"{'=' * 70}\n")

        flash('Chatbot created successfully!', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        db.session.rollback()
        print(f"\n❌ CHATBOT CREATION ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error creating chatbot: {str(e)}', 'error')
        return redirect(url_for('create_chatbot_route'))


@app.route('/chatbot/edit/<int:chatbot_id>', methods=['GET', 'POST'])
@subscription_required
def edit_chatbot_route(chatbot_id):
    """Edit an existing chatbot"""
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
            # Basic fields
            chatbot.name = request.form.get('name', '').strip()
            chatbot.bot_name = request.form.get('bot_name', '').strip()
            chatbot.description = request.form.get('description', '').strip()
            chatbot.welcome_message = request.form.get('welcome_message', '').strip()

            # Colors
            chatbot.theme_color = request.form.get('theme_color', '#4F46E5')
            chatbot.chat_background_color = request.form.get('chat_background_color', '#F7FAFC')
            chatbot.bot_message_color = request.form.get('bot_message_color', '#FFFFFF')
            chatbot.bot_text_color = request.form.get('bot_text_color', '#1A202C')
            chatbot.user_text_color = request.form.get('user_text_color', '#FFFFFF')

            # Handle avatar changes
            remove_avatar_flag = request.form.get('remove_avatar', 'false')
            bot_avatar_data = request.form.get('bot_avatar_data', '').strip()

            # Case 1: User wants to remove avatar
            if remove_avatar_flag == 'true':
                if chatbot.bot_avatar and chatbot.bot_avatar.startswith('/data/users/'):
                    relative_path = chatbot.bot_avatar.replace('/data/', '')
                    old_path = os.path.join('data', relative_path)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception as e:
                            print(f"   ⚠️ Could not delete old avatar: {e}")

                chatbot.bot_avatar = None

            # Case 2: User uploaded new avatar (base64 data)
            elif bot_avatar_data and bot_avatar_data.startswith('data:image'):
                try:
                    # Delete old avatar file if exists
                    if chatbot.bot_avatar and chatbot.bot_avatar.startswith('/data/users/'):
                        relative_path = chatbot.bot_avatar.replace('/data/', '')
                        old_path = os.path.join('data', relative_path)
                        old_path = os.path.normpath(old_path)

                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                            except Exception as e:
                                print(f"   ⚠️ Could not delete old avatar: {e}")

                    # Process new avatar
                    header, data = bot_avatar_data.split(',', 1)
                    image_data = base64.b64decode(data)
                    image = Image.open(io.BytesIO(image_data))
                    image = image.convert('RGBA')

                    # Resize if too large
                    max_size = (500, 500)
                    if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                        image.thumbnail(max_size, Image.Resampling.LANCZOS)

                    # Build path
                    chatbot_folder = os.path.join(
                        'data', 'users', f'user_{chatbot.user_id}',
                        'chatbots', f'chatbot_{chatbot_id}'
                    )
                    chatbot_folder = os.path.normpath(chatbot_folder)
                    os.makedirs(chatbot_folder, exist_ok=True)

                    unique_filename = "avatar.png"
                    file_path = os.path.join(chatbot_folder, unique_filename)
                    file_path = os.path.normpath(file_path)

                    # Save the image
                    image.save(file_path, 'PNG')

                    if not os.path.exists(file_path):
                        raise Exception(f"Failed to save avatar to {file_path}")

                    # Update database path
                    chatbot.bot_avatar = f"/data/users/user_{chatbot.user_id}/chatbots/chatbot_{chatbot_id}/{unique_filename}"

                except Exception as e:
                    print(f"    ❌ Avatar processing error: {e}")
                    flash('Error processing avatar image', 'error')

            # Welcome Buttons with Submenu Support
            welcome_buttons_raw = request.form.get('welcome_buttons', '[]')

            try:
                if isinstance(welcome_buttons_raw, str):
                    buttons_list = json.loads(welcome_buttons_raw) if welcome_buttons_raw else []
                else:
                    buttons_list = welcome_buttons_raw if welcome_buttons_raw else []

                if not isinstance(buttons_list, list):
                    buttons_list = []

                validated_buttons = []
                valid_types = ['url', 'intent', 'message', 'submenu']

                for idx, button in enumerate(buttons_list):
                    if not isinstance(button, dict):
                        continue

                    button_text = button.get('text', '').strip()
                    button_type = button.get('type', 'url').strip()
                    button_value = button.get('value', '').strip()
                    has_submenu = button.get('has_submenu', False)
                    submenu_items = button.get('submenu_items', [])

                    if not button_text:
                        continue

                    if button_type not in valid_types:
                        button_type = 'url'

                    validated_button = {
                        'text': button_text,
                        'type': button_type,
                        'value': button_value,
                        'has_submenu': has_submenu
                    }

                    # Validate submenu items
                    if has_submenu and isinstance(submenu_items, list):
                        validated_submenu = []
                        for sub_item in submenu_items:
                            if isinstance(sub_item, dict):
                                sub_text = sub_item.get('text', '').strip()
                                sub_type = sub_item.get('type', 'url').strip()
                                sub_value = sub_item.get('value', '').strip()

                                if sub_text:
                                    if sub_type not in valid_types:
                                        sub_type = 'url'

                                    validated_submenu.append({
                                        'text': sub_text,
                                        'type': sub_type,
                                        'value': sub_value
                                    })

                        validated_button['submenu_items'] = validated_submenu
                    else:
                        validated_button['submenu_items'] = []

                    validated_buttons.append(validated_button)

                chatbot.welcome_buttons = json.dumps(validated_buttons)

            except json.JSONDecodeError as e:
                print(f"    JSON decode error: {e}")
                chatbot.welcome_buttons = '[]'
            except Exception as e:
                print(f"    Validation error: {e}")
                chatbot.welcome_buttons = '[]'

            # Other settings
            chatbot.use_ml_model = request.form.get('use_ml_model') == 'on'
            chatbot.updated_at = datetime.now(timezone.utc)

            # Commit changes
            db.session.commit()

            flash('Chatbot updated successfully!', 'success')
            return redirect(url_for('dashboard'))

        except Exception as e:
            db.session.rollback()
            print(f"❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Error updating chatbot: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('edit_chatbot.html', chatbot=chatbot, chatbots=chatbots, user=user)


@app.route('/chatbot/delete/<int:chatbot_id>')
@subscription_required
def delete_chatbot_route(chatbot_id):
    """Delete a chatbot"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])
    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # Delete training file if exists
    if chatbot.training_file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], chatbot.training_file)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Delete chatbot
    db.session.delete(chatbot)

    # Decrement count
    if user.subscription:
        user.subscription.decrement_chatbot_count()

    db.session.commit()

    flash('Chatbot deleted successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/chatbot/toggle/<int:chatbot_id>')
@subscription_required
def toggle_chatbot_route(chatbot_id):
    """Toggle chatbot active status"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    chatbot.is_active = not chatbot.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': chatbot.is_active})


# ============================================
# CHATBOT PREVIEW & DEPLOY ROUTES
# ============================================

@app.route('/chatbot/preview/<int:chatbot_id>')
@subscription_required
def preview_chatbot(chatbot_id):
    """Preview chatbot before deployment"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    # Parse welcome buttons
    welcome_buttons_data = []
    if chatbot.welcome_buttons:
        try:
            welcome_buttons_data = json.loads(chatbot.welcome_buttons)
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing welcome buttons: {e}")
            welcome_buttons_data = []

    # Get avatar URL
    bot_avatar_url = None
    if chatbot.bot_avatar:
        avatar_path = chatbot.bot_avatar.strip()
        base_url = request.url_root.rstrip('/')

        if avatar_path.startswith(('http://', 'https://')):
            bot_avatar_url = avatar_path
        elif avatar_path.startswith('/data/users/'):
            bot_avatar_url = base_url + avatar_path
        elif avatar_path.startswith('/static/'):
            bot_avatar_url = base_url + avatar_path
        else:
            if not avatar_path.startswith('data/users/'):
                avatar_path = f"data/users/{avatar_path.lstrip('/')}"
            bot_avatar_url = f"{base_url}/{avatar_path}"

    return render_template(
        'preview_chatbot.html',
        chatbot=chatbot,
        chatbots=chatbots,
        user=user,
        welcome_buttons=welcome_buttons_data,
        bot_avatar_url=bot_avatar_url
    )


@app.route('/chatbot/deploy/<int:chatbot_id>')
@subscription_required
def deploy_chatbot(chatbot_id):
    """Deploy/activate a chatbot"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    # Activate
    chatbot.is_active = True
    db.session.commit()

    # Generate iframe code
    embed_url = f"{request.host_url.rstrip('/')}/embed/{chatbot.embed_code}"
    iframe_code = f'<iframe src="{embed_url}" width="400" height="600" frameborder="0" style="border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);"></iframe>'

    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    flash('Chatbot deployed successfully!', 'success')

    return render_template(
        'deploy_chatbot.html',
        chatbot=chatbot,
        iframe_code=iframe_code,
        chatbots=chatbots,
        user=user
    )


print("✅ Chatbot controller loaded successfully!")