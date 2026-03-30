"""
Subscription Controller
Handles subscription plans, selection, and management
"""
from base import app, db
from flask import render_template, request, redirect, url_for, session, flash
from datetime import datetime, timezone, timedelta

from base.com.vo.user_vo import User
from base.com.vo.subscription_vo import SubscriptionPlan, Subscription
from base.com.dao.user_dao import get_user_by_id
from base.com.dao.subscription_dao import (
    initialize_subscription_plans,
    get_all_active_plans,
    get_plan_by_name,
    create_trial_subscription,
    get_subscription_by_user_id
)
from base.com.dao.chat_dao import get_chatbots_by_user
from base.com.controller.decorators import subscription_required


# ============================================
# SUBSCRIPTION ROUTES
# ============================================

@app.route('/subscription/plans')  # ✅ Added /subscription prefix
def subscription_plans():
    """Show subscription plans page - Step 2"""
    # Initialize plans if needed
    if SubscriptionPlan.query.count() == 0:
        initialize_subscription_plans()

    plans = get_all_active_plans()

    current_plan = None
    is_pending_registration = False
    pending_username = None

    if 'pending_user_id' in session:
        is_pending_registration = True
        pending_username = session.get('pending_username', 'User')

        if session.pop('registration_success', False):
            flash('Account created successfully! Please choose a subscription plan to continue.', 'success')
    elif 'user_id' in session:
        user = get_user_by_id(session['user_id'])
        if user and user.subscription:
            current_plan = user.subscription.plan.name

    return render_template(
        'subscription.html',
        plans=plans,
        current_plan=current_plan,
        is_pending_registration=is_pending_registration,
        pending_username=pending_username
    )


@app.route('/subscription/select')  # ✅ Added /subscription prefix
def select_subscription():
    """Handle plan selection - Step 3"""
    plan_name = request.args.get('plan')

    print(f"🔵 /subscription/select called - plan={plan_name}")

    if not plan_name:
        flash('Please select a plan.', 'error')
        return redirect(url_for('subscription_plans'))  # ✅ Fixed function name

    plan = get_plan_by_name(plan_name)
    if not plan:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('subscription_plans'))  # ✅ Fixed function name

    # Case 1: Newly registered user (pending)
    if 'pending_user_id' in session:
        user_id = session['pending_user_id']
        user = get_user_by_id(user_id)

        if not user:
            session.clear()
            flash('Registration error. Please try again.', 'error')
            return redirect(url_for('register'))  # ✅ Fixed function name

        try:
            # Check if user already has a subscription (prevent duplicate)
            existing_subscription = get_subscription_by_user_id(user_id)

            if existing_subscription:
                # Update existing subscription instead of creating new one
                existing_subscription.plan_id = plan.id
                existing_subscription.status = 'trial' if plan_name == 'free_trial' else 'active'
                existing_subscription.is_trial = (plan_name == 'free_trial')

                if plan_name == 'free_trial':
                    trial_end = datetime.now(timezone.utc) + timedelta(days=14)
                    existing_subscription.end_date = trial_end
                    existing_subscription.trial_end_date = trial_end
                else:
                    existing_subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)
                    existing_subscription.next_billing_date = existing_subscription.end_date

                db.session.commit()
                plan_message = f'Successfully subscribed to {plan.display_name} plan!'
            else:
                # Create new subscription
                if plan_name == 'free_trial':
                    subscription = create_trial_subscription(user_id)
                    if not subscription:
                        flash('Failed to activate trial. Please try again.', 'error')
                        return redirect(url_for('subscription_plans'))  # ✅ Fixed
                    plan_message = 'Your 14-day free trial has been activated!'
                else:
                    end_date = datetime.now(timezone.utc) + timedelta(days=30)
                    subscription = Subscription(
                        user_id=user_id,
                        plan_id=plan.id,
                        status='active',
                        is_trial=False,
                        end_date=end_date,
                        next_billing_date=end_date
                    )
                    db.session.add(subscription)
                    db.session.commit()
                    plan_message = f'Successfully subscribed to {plan.display_name} plan!'

            # Auto-login the user
            session.pop('pending_user_id', None)
            session.pop('pending_email', None)
            session.pop('pending_username', None)

            session['user_id'] = user.id
            session['username'] = user.username
            session['email'] = user.email

            flash(plan_message, 'success')
            flash(f'Welcome to your dashboard, {user.first_name}!', 'info')
            return redirect(url_for('dashboard'))  # ✅ Fixed function name

        except Exception as e:
            db.session.rollback()
            print(f"Error creating subscription: {e}")
            import traceback
            traceback.print_exc()
            flash('Failed to activate subscription. Please try again.', 'error')
            return redirect(url_for('subscription_plans'))  # ✅ Fixed

    # Case 2: Logged-in user changing subscription
    elif 'user_id' in session:
        user_id = session['user_id']
        user = get_user_by_id(user_id)

        if not user:
            session.clear()
            flash('Session expired. Please log in again.', 'error')
            return redirect(url_for('login'))  # ✅ Fixed function name

        try:
            if user.subscription:
                # Update existing subscription
                old_plan = user.subscription.plan.display_name
                user.subscription.plan_id = plan.id
                user.subscription.status = 'trial' if plan_name == 'free_trial' else 'active'
                user.subscription.is_trial = (plan_name == 'free_trial')

                if plan_name == 'free_trial':
                    user.subscription.end_date = datetime.now(timezone.utc) + timedelta(days=14)
                    user.subscription.trial_end_date = user.subscription.end_date
                else:
                    user.subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)

                user.subscription.next_billing_date = user.subscription.end_date
                db.session.commit()
                flash(f'Successfully changed from {old_plan} to {plan.display_name}!', 'success')
            else:
                # Create new subscription
                if plan_name == 'free_trial':
                    subscription = create_trial_subscription(user_id)
                    if not subscription:
                        flash('Failed to activate trial. Please try again.', 'error')
                        return redirect(url_for('subscription_plans'))  # ✅ Fixed
                    flash('Your 14-day free trial has been activated!', 'success')
                else:
                    end_date = datetime.now(timezone.utc) + timedelta(days=30)
                    subscription = Subscription(
                        user_id=user_id,
                        plan_id=plan.id,
                        status='active',
                        is_trial=False,
                        end_date=end_date,
                        next_billing_date=end_date
                    )
                    db.session.add(subscription)
                    db.session.commit()
                    flash(f'Successfully subscribed to {plan.display_name} plan!', 'success')

            return redirect(url_for('dashboard'))  # ✅ Fixed function name

        except Exception as e:
            db.session.rollback()
            print(f"Error updating subscription: {e}")
            import traceback
            traceback.print_exc()
            flash('Failed to update subscription. Please try again.', 'error')
            return redirect(url_for('subscription_plans'))  # ✅ Fixed

    # Case 3: Not logged in or pending
    else:
        flash('Please register or log in to select a plan.', 'info')
        return redirect(url_for('register'))  # ✅ Fixed function name


@app.route('/subscription/manage')  # ✅ Added /subscription prefix
@subscription_required
def manage_subscription():
    """Show subscription management page"""
    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)

    # Get usage stats
    usage_stats = user.subscription.get_usage_stats()

    return render_template(
        'manage_subscription.html',
        user=user,
        subscription=user.subscription,
        chatbots=chatbots,
        usage_stats=usage_stats
    )


@app.route('/subscription/reactivate')  # ✅ Added /subscription prefix
@subscription_required
def reactivate_subscription():
    """Reactivate cancelled subscription"""
    user = get_user_by_id(session['user_id'])

    if not user.subscription or user.subscription.status != 'cancelled':
        flash('No cancelled subscription found.', 'error')
        return redirect(url_for('dashboard'))  # ✅ Fixed function name

    try:
        user.subscription.status = 'active'

        if user.subscription.end_date < datetime.now(timezone.utc):
            user.subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)
            user.subscription.next_billing_date = user.subscription.end_date

        db.session.commit()
        flash('Your subscription has been reactivated!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Reactivate error: {e}")
        flash('Failed to reactivate subscription. Please try again.', 'error')

    return redirect(url_for('manage_subscription'))  # ✅ Fixed function name


print("✅ Subscription controller loaded successfully!")