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
            return render_template('login.html')

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
            return render_template('login.html')

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

    # Get all chatbots for this user
    chatbots = get_chatbots_by_user(user.id)

    # Calculate statistics
    total_chatbots = len(chatbots)
    active_chatbots = sum(1 for bot in chatbots if bot.is_active)

    # Check if ML model is trained
    from flask import current_app
    user_folder = os.path.join(current_app.config['USER_DATA_FOLDER'], f'user_{user.id}')
    ml_model_trained = os.path.exists(os.path.join(user_folder, 'chatbot_model.h5'))

    # Subscription warnings & Premium Check
    subscription_warning = None
    is_premium = False  # ★ NEW: Default to False

    if user.subscription:
        # ★ NEW: Check if the user is on a paid plan
        if user.subscription and 'free' not in user.subscription.plan.name.lower():
            is_premium = True

        if user.subscription.is_trial and user.subscription.days_remaining() <= 3:
            subscription_warning = f"Your trial expires in {user.subscription.days_remaining()} days!"
        elif user.subscription.status == 'cancelled':
            subscription_warning = f"Your subscription is cancelled and will end in {user.subscription.days_remaining()} days."

    # ── ★ ONLY QUERY LEADS IF USER IS PREMIUM ★ ──
    total_leads = 0
    recent_sessions = []

    if is_premium:
        from base.com.vo.session_vo import ChatSession
        chatbot_ids = [bot.id for bot in chatbots]

        if chatbot_ids:
            total_leads = ChatSession.query.filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.visitor_name.isnot(None)
            ).count()

            recent_sessions = ChatSession.query.filter(
                ChatSession.chatbot_id.in_(chatbot_ids),
                ChatSession.visitor_name.isnot(None)
            ).order_by(ChatSession.started_at.desc()).limit(15).all()

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
        is_premium=is_premium  # 👈 Pass the flag to HTML!
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
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        sender_user = "kunvariya.dk@gmail.com"
        sender_pass = "cwpctdztwwohcjhe"  # Your Gmail App Password here
        sender_from = "kunvariya.dk@gmail.com"

        if not sender_user or not sender_pass:
            print("CRITICAL: Missing MAIL_USERNAME or MAIL_PASSWORD")
            return False

        display_name = user.username or user.email

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Inter, Arial, sans-serif; background: #f7fafc; margin: 0; padding: 0; }}
    .wrap {{ max-width: 580px; margin: 40px auto; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .header {{ background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; padding: 32px 36px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
    .body {{ padding: 32px 36px; line-height: 1.6; color: #4a5568; }}
    .cta {{ display: block; margin: 28px 0; text-align: center; }}
    .btn {{ background: #667eea; color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 15px; display: inline-block; }}
    .footer {{ padding: 20px 36px; background: #f7fafc; font-size: 12px; color: #a0aec0; text-align: center; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header"><h1>Password Reset Request</h1></div>
    <div class="body">
      <p>Hello <strong>{display_name}</strong>,</p>
      <p>We received a request to reset your account password. Click the button below to set a new one:</p>
      <div class="cta">
        <a href="{reset_url}" class="btn">Reset My Password</a>
      </div>
      <p>This link will expire in <strong>1 hour</strong>.</p>
      <p>If you did not request this, you can safely ignore this email.</p>
    </div>
    <div class="footer">ChatBot Builder - Secure Account Management</div>
  </div>=
</body>
</html>"""

        plain_body = f"Hello {display_name},\n\nReset your password here: {reset_url}\n\nThis link expires in 1 hour."

        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Reset your ChatBot Builder Password"
        msg['From'] = sender_from
        msg['To'] = user.email

        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_user, sender_pass)
            server.sendmail(sender_from, user.email, msg.as_bytes())

        print(f"Email sent successfully to {user.email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("SMTP Auth failed - use a Gmail App Password, not your account password")
        print("Generate one at: https://myaccount.google.com/apppasswords")
        return False
    except smtplib.SMTPException as e:
        print(f"SMTP error: {e}")
        return False
    except Exception as e:
        print(f"Password reset email failed: {e}")
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
            # Generate reset token
            token = serializer.dumps(email, salt='password-reset-salt')
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
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except SignatureExpired:
        flash('The password reset link has expired', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid password reset link', 'error')
        return redirect(url_for('auth.forgot_password'))

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
        user = get_user_by_email(email)
        if user:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Password has been reset successfully! You can now login.', 'success')
            return render_template("login.html")
        else:
            flash('User not found', 'error')
            return redirect(url_for('forgot_password'))

    return render_template('reset_password.html', token=token)
