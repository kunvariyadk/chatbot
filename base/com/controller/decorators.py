"""
Controller Decorators
Common decorators used across controllers
"""
from functools import wraps
from flask import session, redirect, url_for, flash
from base.com.dao.user_dao import get_user_by_id


def subscription_required(f):
    """
    Decorator to require active subscription.

    - If not logged in          -> redirect to login
    - If no subscription        -> redirect to dashboard with overlay (status: none)
    - If subscription expired   -> redirect to dashboard with overlay (status: expired)
    - If subscription cancelled -> redirect to dashboard with overlay (status: cancelled)
    - Otherwise                 -> allow access normally

    The dashboard reads session['sub_status'] to show the correct
    locked overlay and message to the user.

    Usage:
        @app.route('/some-route')
        @subscription_required
        def some_view():
            ...
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Must be logged in
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))

        # 2. User must exist in DB
        user = get_user_by_id(session['user_id'])
        if not user:
            session.clear()
            flash('Session expired. Please log in again.', 'error')
            return redirect(url_for('login'))

        # 3. No subscription at all
        if not user.subscription:
            session['sub_status'] = 'none'
            return redirect(url_for('dashboard'))

        # 4. Subscription expired
        if user.subscription.is_expired():
            session['sub_status'] = 'expired'
            return redirect(url_for('dashboard'))

        # 5. Subscription cancelled
        if user.subscription.status == 'cancelled':
            session['sub_status'] = 'cancelled'
            return redirect(url_for('dashboard'))

        # 6. All good — clear any stale flag and proceed
        session.pop('sub_status', None)
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):
    """
    Decorator to require login (but not necessarily active subscription)

    Usage:
        @app.route('/some-route')
        @login_required
        def some_view():
            ...
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


def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        user = get_user_by_id(session['user_id'])

        # 1. Check if they have a subscription
        if not user.subscription:
            session['sub_status'] = 'none'
            return redirect(url_for('dashboard'))

        # 2. Check if expired or cancelled first
        if user.subscription.is_expired():
            session['sub_status'] = 'expired'
            return redirect(url_for('dashboard'))

        if user.subscription.status == 'cancelled':
            session['sub_status'] = 'cancelled'
            return redirect(url_for('dashboard'))

        # 3. Get the plan name from the connected SubscriptionPlan table
        try:
            plan_name = user.subscription.plan.name.lower()
        except AttributeError:
            flash('Subscription verification error. Please contact support.', 'error')
            return redirect(url_for('dashboard'))

        # 4. Block if it's the free plan
        if 'free' in plan_name:
            flash('Live Chat requires a premium subscription. Please upgrade to access this feature.', 'warning')
            return redirect(url_for('subscription_plans'))

        return f(*args, **kwargs)

    return decorated_function