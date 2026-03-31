"""
User Profile Controller
Handles user profile management and password changes
"""
import re
import dns.resolver
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
# Remove the subscription_required definition from auth_controller.py
# and add this import at the top:
from base import app
from base.com.controller.decorators import subscription_required, login_required
from base import db
from base.com.vo.user_vo import User
from base.com.dao.user_dao import get_user_by_id, get_user_by_email, get_user_by_username, update_user
from base.com.dao.chat_dao import get_chatbots_by_user
from base.com.controller.auth_controller import subscription_required,login_required

# Create Blueprint

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


@app.route('/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_profile():
    """Edit user profile"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])

    if request.method == 'POST':
        new_first_name = request.form.get('first_name')
        new_last_name = request.form.get('last_name')
        new_username = request.form.get('username')
        new_email = request.form.get('email')
        new_phone = request.form.get('phone')

        # Validation
        if not all([new_first_name, new_last_name, new_username, new_email, new_phone]):
            flash('All fields are required.', 'error')
            return redirect(url_for('edit_profile'))

        # Check if username is taken by another user

        if new_username != user.username:
            existing_user = get_user_by_username(new_username)
            if existing_user:
                flash('Username already taken', 'error')
                return redirect(url_for('edit_profile'))

        # Check if email is taken by another user
        if new_email != user.email:
            existing_email = get_user_by_email(new_email)
            if existing_email:
                flash('Email already registered', 'error')
                return redirect(url_for('edit_profile'))

            # Validate email format
            if not EMAIL_REGEX.match(new_email):
                flash('Invalid email format', 'error')
                return redirect(url_for('edit_profile'))

            if not domain_exists(new_email):
                flash('Invalid email domain', 'error')
                return redirect(url_for('edit_profile'))

        # Check if username and email are the same
        if new_username == new_email:
            flash('Username and Email cannot be the same.', 'error')
            return redirect(url_for('edit_profile'))

        # Validate phone number
        if not new_phone.isdigit() or len(new_phone) != 10:
            flash('Phone number must be exactly 10 digits.', 'error')
            return redirect(url_for('edit_profile'))

        # Update user information
        update_user(
            user.id,
            first_name=new_first_name,
            last_name=new_last_name,
            username=new_username,
            email=new_email,
            phone=new_phone
        )

        # Update session
        session['username'] = new_username
        session['email'] = new_email

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('dashboard'))

    chatbots = get_chatbots_by_user(user.id)
    return render_template('edit_profile.html', user=user, chatbots=chatbots)


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
@subscription_required
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user = get_user_by_id(session['user_id'])

    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Verify current password
        if not check_password_hash(user.password, current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('change_password'))

        # Check if new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('user.change_password'))

        # Check password length
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return redirect(url_for('user.change_password'))

        # Update password
        user.password = generate_password_hash(new_password)
        db.session.commit()

        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))

    chatbots = get_chatbots_by_user(user.id)
    return render_template('change_password.html', user=user, chatbots=chatbots)