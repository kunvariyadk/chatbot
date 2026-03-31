"""
Controller Decorators
Common decorators used across controllers
"""
from functools import wraps
from flask import session, redirect, url_for, flash
from base.com.dao.user_dao import get_user_by_id


def subscription_required(f):
    """
    Decorator to require active subscription

    Usage:
        @bp.route('/some-route')
        @subscription_required
        def some_view():
            # Your code here
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))

        # Get user from database
        user = get_user_by_id(session['user_id'])

        if not user:
            session.clear()
            flash('Please log in again', 'error')
            return redirect(url_for('auth.login'))

        # Check if user has a subscription
        if not user.subscription:
            flash('You need an active subscription to access this feature.', 'warning')
            return redirect(url_for('subscription.plans'))

        # Check if subscription is expired
        if user.subscription.is_expired():
            flash('Your subscription has expired. Please renew to continue.', 'error')
            return redirect(url_for('subscription.plans'))

        # Check if subscription is cancelled
        if user.subscription.status == 'cancelled':
            flash('Your subscription has been cancelled. Please reactivate or choose a new plan.', 'warning')
            return redirect(url_for('subscription.manage'))

        # All checks passed - allow access
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):
    """
    Decorator to require login (but not necessarily active subscription)

    Usage:
        @bp.route('/some-route')
        @login_required
        def some_view():
            # Your code here
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))

        user = get_user_by_id(session['user_id'])

        if not user:
            session.clear()
            flash('Please log in again', 'error')
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function