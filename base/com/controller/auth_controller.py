"""
Authentication Controller
Handles user registration, login, logout, and password management
"""
import os
import re
from datetime import timedelta

from base import app
import dns.resolver
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import SignatureExpired, BadSignature
# Remove the subscription_required definition from auth_controller.py
# and add this import at the top:

from base.com.controller.decorators import subscription_required, login_required
from base import db, serializer, mail
from base.com.vo.user_vo import User
from base.com.vo.subscription_vo import SubscriptionPlan, Subscription
from base.com.dao.user_dao import (
    get_user_by_email,
    create_user,
    get_user_by_id, get_user_by_username
)
from base.com.dao.chat_dao import (
    get_chatbots_by_user,
    get_chatbot_by_id, get_active_chatbots_by_user,
    get_chatbot_by_embed_code
)
from base.com.dao.subscription_dao import (
    create_trial_subscription,
    get_all_active_plans
)
from base.com.service.file_service import ensure_user_folder
from flask_mail import Message

# Email validation regex
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def domain_exists(email):
    """Check if the email domain actually exists"""
    try:
        domain = email.split('@')[-1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except dns.resolver.NXDOMAIN:
        return False
    except Exception:
        return False


@app.route('/', methods=['GET'])
def index():
    """Home route - redirect based on login status"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login with Remember Me functionality"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return redirect(url_for('login'))

        user = get_user_by_email(email)

        if user and check_password_hash(user.password, password):
            # Check if user has subscription
            if not user.subscription:
                flash('Please select a subscription plan to access your account.', 'warning')
                session['pending_user_id'] = user.id
                session['pending_email'] = user.email
                session['pending_username'] = user.username
                return render_template("subscription.html")

            # Check subscription status
            if user.subscription.status in ['expired', 'cancelled']:
                session['user_id'] = user.id
                session['username'] = user.username
                session['email'] = user.email
                flash('Your subscription has expired. Please renew to continue.', 'warning')
                return render_template("subscription.html")

            # Set session with remember me
            session['user_id'] = user.id
            session['username'] = user.username
            session['email'] = user.email

            # Configure session permanence
            from flask import current_app

            if remember:
                session.permanent = True
                current_app.permanent_session_lifetime = timedelta(days=30)
            else:
                session.permanent = False

            flash(f'Welcome back, {user.first_name}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

    # GET request
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration - Step 1"""
    if 'user_id' in session:
        return render_template("dashboard.html")

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        username = request.form.get('User_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not all([first_name, last_name, username, email, phone, password, confirm_password]):
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if get_user_by_username(username):
            flash('Username already exists.', 'error')
            return render_template('register.html')

        if get_user_by_email(email):
            flash('Email already registered.', 'error')
            return render_template('register.html')

        if username == email:
            flash('Username and Email cannot be the same.', 'error')
            return render_template('register.html')

        if not EMAIL_REGEX.match(email):
            flash('Invalid email format.', 'error')
            return render_template('register.html')

        if not domain_exists(email):
            flash('Invalid email domain.', 'error')
            return render_template('register.html')

        if not phone.isdigit() or len(phone) != 10:
            flash('Phone number must be exactly 10 digits.', 'error')
            return render_template('register.html')

        try:
            # Create user
            new_user = create_user(
                first_name=first_name,
                last_name=last_name,
                username=username,
                email=email,
                phone=phone,
                password=password
            )

            # Create user folder
            ensure_user_folder(new_user.id)

            # Store pending user info
            session['pending_user_id'] = new_user.id
            session['pending_email'] = new_user.email
            session['pending_username'] = new_user.username
            session['registration_success'] = True

            return render_template("subscription.html")

        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'error')
            return render_template('register.html')

    return render_template('register.html')


# @bp.route('/login', methods=['GET', 'POST'])
# def login():
#     """User login with Remember Me functionality"""
#     if 'user_id' in session:
#         return render_template("dashboard.html")
#
#     if request.method == 'POST':
#         email = request.form.get('email', '').strip()
#         password = request.form.get('password', '')
#         remember = request.form.get('remember') == 'on'
#
#         if not email or not password:
#             flash('Please enter both email and password.', 'error')
#             return render_template('login.html')
#
#         user = get_user_by_email(email)
#
#         if user and check_password_hash(user.password, password):
#             # Check if user has subscription
#             if not user.subscription:
#                 flash('Please select a subscription plan to access your account.', 'warning')
#                 session['pending_user_id'] = user.id
#                 session['pending_email'] = user.email
#                 session['pending_username'] = user.username
#                 return redirect(url_for('subscription.plans'))
#
#             # Check subscription status
#             if user.subscription.status in ['expired', 'cancelled']:
#                 session['user_id'] = user.id
#                 session['username'] = user.username
#                 session['email'] = user.email
#                 flash('Your subscription has expired. Please renew to continue.', 'warning')
#                 return redirect(url_for('subscription.plans'))
#
#             # Set session with remember me
#             session['user_id'] = user.id
#             session['username'] = user.username
#             session['email'] = user.email
#
#             # Configure session permanence
#             from datetime import timedelta
#             from flask import current_app
#
#             if remember:
#                 session.permanent = True
#                 current_app.permanent_session_lifetime = timedelta(days=30)
#             else:
#                 session.permanent = False
#
#             flash(f'Welcome back, {user.first_name}!', 'success')
#             return redirect(url_for('dashboard'))
#         else:
#             flash('Invalid email or password.', 'error')
#             return render_template('login.html')
#
#     return render_template('login.html')


@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """User dashboard - shows chatbots and subscription info"""
    import os
    user = get_user_by_id(session['user_id'])

    # ── SUBSCRIPTION STATUS CHECK ──────────────────────────────────────────
    if user.subscription and not user.subscription.is_expired() \
            and user.subscription.status != 'cancelled':
        session.pop('sub_status', None)
    else:
        if not user.subscription:
            session['sub_status'] = 'none'
        elif user.subscription.is_expired():
            session['sub_status'] = 'expired'
        elif user.subscription.status == 'cancelled':
            session['sub_status'] = 'cancelled'
    # ──────────────────────────────────────────────────────────────────────

    chatbots = get_chatbots_by_user(user.id)
    total_chatbots = len(chatbots)
    active_chatbots = sum(1 for bot in chatbots if bot.is_active)

    from flask import current_app
    user_folder = os.path.join(current_app.config['USER_DATA_FOLDER'], f'user_{user.id}')
    ml_model_trained = os.path.exists(os.path.join(user_folder, 'chatbot_model.h5'))

    subscription_warning = None
    is_premium = False

    if user.subscription:
        if 'free' not in user.subscription.plan.name.lower():
            is_premium = True
        if user.subscription.is_trial and user.subscription.days_remaining() <= 3:
            subscription_warning = f"Your trial expires in {user.subscription.days_remaining()} days!"
        elif user.subscription.status == 'cancelled':
            subscription_warning = f"Your subscription is cancelled and will end in {user.subscription.days_remaining()} days."

    total_leads = 0
    recent_sessions = []

    # ── NEW: per-bot chat counts & sparkline history ───────────────────────
    from base.com.vo.session_vo import ChatSession, ChatMessage
    from sqlalchemy import func
    from datetime import datetime, timezone, timedelta

    chatbot_ids = [bot.id for bot in chatbots]

    if chatbot_ids:
        # AI chat count — sessions handled purely by AI (status='bot')
        ai_rows = (
            ChatSession.query
            .with_entities(
                ChatSession.chatbot_id,
                func.count(ChatSession.id).label('cnt')
            )
            .filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.status == 'bot'
            )
            .group_by(ChatSession.chatbot_id)
            .all()
        )
        ai_map = {r.chatbot_id: r.cnt for r in ai_rows}

        # Live session count — escalated to human owner
        live_rows = (
            ChatSession.query
            .with_entities(
                ChatSession.chatbot_id,
                func.count(ChatSession.id).label('cnt')
            )
            .filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                db.or_(
                    ChatSession.is_live == True,
                    ChatSession.status == 'human'
                )
            )
            .group_by(ChatSession.chatbot_id)
            .all()
        )
        live_map = {r.chatbot_id: r.cnt for r in live_rows}

        # 7-day daily message history per bot (for sparkline mini-chart)
        # Single query for all bots at once
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        history_rows = (
            db.session.query(
                ChatSession.chatbot_id,
                func.date(ChatSession.started_at).label('day'),
                func.count(ChatMessage.id).label('msg_count')
            )
            .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.started_at >= cutoff
            )
            .group_by(ChatSession.chatbot_id, func.date(ChatSession.started_at))
            .all()
        )

        # { chatbot_id: { 'YYYY-MM-DD': count } }
        hist_map = {}
        for r in history_rows:
            hist_map.setdefault(r.chatbot_id, {})[str(r.day)] = r.msg_count

        # Date slots oldest → newest
        date_slots = [
            (datetime.now(timezone.utc) - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(6, -1, -1)
        ]

        for bot in chatbots:
            bot.chat_count = ai_map.get(bot.id, 0)
            bot.live_chat_count = live_map.get(bot.id, 0)
            bot.daily_chat_history = [
                hist_map.get(bot.id, {}).get(d, 0) for d in date_slots
            ]

    else:
        for bot in chatbots:
            bot.chat_count = 0
            bot.live_chat_count = 0
            bot.daily_chat_history = [0, 0, 0, 0, 0, 0, 0]
    # ──────────────────────────────────────────────────────────────────────

    # Leads — premium only (your existing logic, unchanged)
    if is_premium and chatbot_ids:
        total_leads = (
            ChatSession.query
            .filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.visitor_name.isnot(None)
            )
            .count()
        )
        recent_sessions = (
            ChatSession.query
            .filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.visitor_name.isnot(None)
            )
            .order_by(ChatSession.started_at.desc())
            .limit(15)
            .all()
        )

    return render_template(
        'dashboard.html',
        user=user,
        chatbots=chatbots,
        total_chatbots=total_chatbots,
        active_chatbots=active_chatbots,
        ml_model_trained=ml_model_trained,
        subscription_warning=subscription_warning,
        total_leads=total_leads,
        recent_sessions=recent_sessions,
        is_premium=is_premium
    )


@app.route('/bots')
@login_required
def bots():
    """Chatbot listing page"""
    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)
    return render_template('bots.html', user=user, chatbots=chatbots)


@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


def send_reset_password_email(user, reset_url):
    """
    Send a professional password reset email with one-time link.
    """
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        # Your Gmail credentials (consider moving to config)
        SMTP_USER = "kunvariya.dk@gmail.com"
        SMTP_PASS = "cwpctdztwwohcjhe"
        FROM_EMAIL = "kunvariya.dk@gmail.com"

        if not SMTP_USER or not SMTP_PASS:
            app.logger.error("SMTP credentials missing")
            return False

        display_name = f"{user.first_name} {user.last_name}".strip() or user.username or user.email

        # --- Professional HTML Email ---
        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password</title>
  <style>
    /* Reset styles */
    body, table, td, p, a {{ margin: 0; padding: 0; border: 0; font-size: 100%; }}
    body {{ font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; background-color: #f4f7fb; margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    td {{ vertical-align: top; }}
    .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,0.05); }}
    .header {{ background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); padding: 32px 28px; text-align: center; }}
    .header h1 {{ margin: 0; color: #ffffff; font-size: 24px; font-weight: 700; letter-spacing: -0.3px; }}
    .content {{ padding: 40px 32px; background: #ffffff; }}
    .greeting {{ font-size: 18px; color: #1F2937; font-weight: 600; margin-bottom: 20px; }}
    .message {{ color: #4B5563; line-height: 1.6; margin-bottom: 24px; font-size: 16px; }}
    .button-container {{ text-align: center; margin: 32px 0; }}
    .button {{ background-color: #4F46E5; border-radius: 12px; display: inline-block; padding: 14px 32px; color: #ffffff !important; text-decoration: none; font-weight: 600; font-size: 16px; transition: background 0.2s; box-shadow: 0 2px 6px rgba(79,70,229,0.3); }}
    .button:hover {{ background-color: #4338CA; }}
    .info-box {{ background: #F3F4F6; border-left: 4px solid #4F46E5; padding: 16px 20px; border-radius: 10px; margin: 24px 0; font-size: 14px; color: #374151; }}
    .info-box strong {{ color: #1F2937; }}
    .footer {{ background: #F9FAFB; padding: 24px 32px; text-align: center; font-size: 12px; color: #9CA3AF; border-top: 1px solid #E5E7EB; }}
    .footer a {{ color: #4F46E5; text-decoration: none; }}
    @media only screen and (max-width: 600px) {{
      .content {{ padding: 28px 20px; }}
      .button {{ display: block; width: auto; text-align: center; }}
      .container {{ width: 100% !important; border-radius: 0; }}
    }}
  </style>
</head>
<body style="background-color: #f4f7fb; padding: 24px 12px;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" align="center">
    <tr>
      <td align="center">
        <div class="container">
          <!-- Header -->
          <div class="header">
            <h1>🔐 Reset Your Password</h1>
          </div>

          <!-- Main Content -->
          <div class="content">
            <div class="greeting">Hello, {display_name}</div>
            <div class="message">
              We received a request to reset the password for your ChatBot Builder account. Click the button below to create a new password.
            </div>

            <div class="button-container">
              <a href="{reset_url}" class="button" style="color:#ffffff;">Reset My Password</a>
            </div>

            <div class="info-box">
              <strong>⚠️ Security Information</strong><br>
              • This link is <strong>valid for 1 hour</strong> and can be used <strong>only once</strong>.<br>
              • If you didn't request this, please ignore this email. Your password will not change.<br>
              • For security, never share this link with anyone.
            </div>

            <div class="message" style="font-size: 14px; margin-top: 24px;">
              If the button above doesn't work, copy and paste this link into your browser:
              <div style="background: #F3F4F6; padding: 10px; border-radius: 8px; margin-top: 8px; font-family: monospace; word-break: break-all; font-size: 13px;">
                {reset_url}
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="footer">
            <p>© 2025 ChatBot Builder. All rights reserved.</p>
            <p>This is an automated message, please do not reply directly to this email.</p>
            <p><a href="{{ url_for('login', _external=True) }}">Visit our website</a></p>
          </div>
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""

        # Plain text alternative (for old email clients)
        plain_body = f"""Reset Your Password - ChatBot Builder

Hello {display_name},

We received a request to reset the password for your ChatBot Builder account.

To reset your password, click the link below (valid for 1 hour, one-time use only):

{reset_url}

If the link above doesn't work, copy and paste it into your browser.

Security Notes:
- This link expires after 1 hour and can be used only once.
- If you didn't request a password reset, please ignore this email. Your password will not change.
- Never share this link with anyone.

Best regards,
ChatBot Builder Team
"""

        # Build email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Reset your ChatBot Builder password"
        msg['From'] = f"ChatBot Builder <{FROM_EMAIL}>"
        msg['To'] = user.email
        msg['Reply-To'] = "support@chatbotbuilder.com"  # adjust to your domain

        # Attach parts
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # Send via SMTP
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, user.email, msg.as_bytes())

        app.logger.info(f"Password reset email sent to {user.email}")
        return True

    except smtplib.SMTPAuthenticationError:
        app.logger.error("SMTP auth failed – use a Gmail App Password")
        return False
    except smtplib.SMTPException as e:
        app.logger.error(f"SMTP error: {e}")
        return False
    except Exception as e:
        app.logger.error(f"Password reset email failed: {e}")
        return False


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password request using smtplib"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = get_user_by_email(email)

        if user:
            # Generate reset token containing email and current password hash for one-time use
            token_data = {
                'email': user.email,
                'password_hash': user.password
            }
            token = serializer.dumps(token_data, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)

            # Attempt to send email
            if send_reset_password_email(user, reset_url):
                flash('A password reset link has been sent to your email.', 'success')
            else:
                flash('Technical error sending email. Please check server logs.', 'error')
        else:
            # Security: do not reveal if the email exists
            flash('If that email exists, a reset link has been sent.', 'info')

        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    try:
        # Verify token (expires in 1 hour)
        data = serializer.loads(token, salt='password-reset-salt', max_age=3600)
        if isinstance(data, dict):
            email = data.get('email')
            token_password_hash = data.get('password_hash')
        else:
            email = data
            token_password_hash = None
    except SignatureExpired:
        flash('The password reset link has expired', 'error')
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash('Invalid password reset link', 'error')
        return redirect(url_for('forgot_password'))

    user = get_user_by_email(email)
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('forgot_password'))

    # Ensure the link is one-time use by checking it against the current password hash
    if not token_password_hash or user.password != token_password_hash:
        flash('This password reset link has already been used.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password', token=token))

        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('reset_password', token=token))

        # Update password
        user.password = generate_password_hash(password)
        db.session.commit()
        flash('Password has been reset successfully! You can now login.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)
