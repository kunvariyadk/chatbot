"""
Subscription Data Access Object
Database operations for Subscription and SubscriptionPlan models
"""
import json
from base import db
from base.com.vo.subscription_vo import SubscriptionPlan, Subscription
from datetime import datetime, timezone, timedelta


def initialize_subscription_plans():
    """Initialize default subscription plans"""
    plans = [
        {
            'name': 'free_trial',
            'display_name': 'Free Trial',
            'price': 0.0,
            'billing_cycle': 'trial',
            'max_chatbots': 1,
            'max_messages_per_month': 100,
            'max_training_data_size': 500,
            'features': json.dumps({
                'chatbots': 1,
                'messages': 100,
                'ml_training': False,
                'custom_branding': False,
                'analytics': 'basic',
                'support': 'email',
                'api_access': False,
                'priority_support': False
            })
        },
        {
            'name': 'basic',
            'display_name': 'Basic',
            'price': 9.99,
            'billing_cycle': 'monthly',
            'max_chatbots': 3,
            'max_messages_per_month': 1000,
            'max_training_data_size': 2000,
            'features': json.dumps({
                'chatbots': 3,
                'messages': 1000,
                'ml_training': True,
                'custom_branding': False,
                'analytics': 'basic',
                'support': 'email',
                'api_access': False,
                'priority_support': False
            })
        },
        {
            'name': 'moderate',
            'display_name': 'Moderate',
            'price': 29.99,
            'billing_cycle': 'monthly',
            'max_chatbots': 10,
            'max_messages_per_month': 5000,
            'max_training_data_size': 10000,
            'features': json.dumps({
                'chatbots': 10,
                'messages': 5000,
                'ml_training': True,
                'custom_branding': True,
                'analytics': 'advanced',
                'support': 'priority',
                'api_access': True,
                'priority_support': False
            })
        },
        {
            'name': 'advanced',
            'display_name': 'Advanced',
            'price': 99.99,
            'billing_cycle': 'monthly',
            'max_chatbots': -1,
            'max_messages_per_month': -1,
            'max_training_data_size': -1,
            'features': json.dumps({
                'chatbots': 'unlimited',
                'messages': 'unlimited',
                'ml_training': True,
                'custom_branding': True,
                'analytics': 'advanced',
                'support': 'dedicated',
                'api_access': True,
                'priority_support': True,
                'white_label': True
            })
        }
    ]

    for plan_data in plans:
        existing = SubscriptionPlan.query.filter_by(name=plan_data['name']).first()
        if not existing:
            plan = SubscriptionPlan(**plan_data)
            db.session.add(plan)

    db.session.commit()
    print(f"✅ Initialized {len(plans)} subscription plans")


def create_trial_subscription(user_id):
    """Create trial subscription"""
    trial_plan = SubscriptionPlan.query.filter_by(name='free_trial').first()
    if not trial_plan:
        print("❌ Error: Free trial plan not found!")
        return None

    trial_end = datetime.now(timezone.utc) + timedelta(days=14)

    subscription = Subscription(
        user_id=user_id,
        plan_id=trial_plan.id,
        status='trial',
        is_trial=True,
        trial_end_date=trial_end,
        end_date=trial_end
    )

    db.session.add(subscription)
    db.session.commit()
    print(f"✅ Created trial subscription for user {user_id}")
    return subscription


def get_subscription_by_user_id(user_id):
    """Get subscription for user"""
    return Subscription.query.filter_by(user_id=user_id).first()


def get_plan_by_name(plan_name):
    """Get subscription plan by name"""
    return SubscriptionPlan.query.filter_by(name=plan_name).first()


def get_all_active_plans():
    """Get all active subscription plans"""
    return SubscriptionPlan.query.filter_by(is_active=True).all()


def update_subscription_plan(user_id, new_plan_name):
    """Update subscription plan"""
    subscription = get_subscription_by_user_id(user_id)
    if not subscription:
        print(f"❌ No subscription found for user {user_id}")
        return False

    new_plan = get_plan_by_name(new_plan_name)
    if not new_plan:
        print(f"❌ Plan '{new_plan_name}' not found")
        return False

    subscription.plan_id = new_plan.id
    subscription.status = 'active'
    subscription.is_trial = (new_plan_name == 'free_trial')
    subscription.updated_at = datetime.now(timezone.utc)

    if new_plan_name == 'free_trial':
        trial_end = datetime.now(timezone.utc) + timedelta(days=14)
        subscription.trial_end_date = trial_end
        subscription.end_date = trial_end
    else:
        subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)
        subscription.next_billing_date = subscription.end_date

    db.session.commit()
    print(f"✅ Updated subscription for user {user_id} to {new_plan.display_name}")
    return True


def reset_all_monthly_counters():
    """Reset monthly counters for all active subscriptions"""
    subscriptions = Subscription.query.filter_by(status='active').all()
    count = 0
    for subscription in subscriptions:
        subscription.reset_monthly_counters()
        count += 1
    print(f"✅ Reset {count} subscription message counters")
    return count