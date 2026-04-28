"""
User Data Access Object
Database operations for User model
"""
from werkzeug.security import generate_password_hash
from base import db
from base.com.vo.user_vo import User
from base.com.vo.subscription_vo import Subscription


from sqlalchemy.orm import joinedload

def get_user_by_id(user_id):
    return User.query.options(
        joinedload(User.subscription).joinedload(Subscription.plan)
    ).filter(User.id == user_id).first()

def get_user_by_email(email):
    """Get user by email"""
    return User.query.filter_by(email=email).first()


def get_user_by_username(username):
    """Get user by username"""
    return User.query.filter_by(username=username).first()


def create_user(first_name, last_name, username, email, phone, password):
    """Create new user"""
    hashed_password = generate_password_hash(password)

    new_user = User(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        phone=phone,
        password=hashed_password
    )

    db.session.add(new_user)
    db.session.commit()

    return new_user


def update_user(user_id, **kwargs):
    """Update user fields"""
    user = get_user_by_id(user_id)
    if not user:
        return None

    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)

    db.session.commit()
    return user


def delete_user(user_id):
    """Delete user"""
    user = get_user_by_id(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return True
    return False


def get_all_users():
    """Get all users"""
    return User.query.all()