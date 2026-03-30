"""
Subscription Value Objects (Models)
Subscription plans and user subscriptions
"""
import json
from base import db
from datetime import datetime, timezone, timedelta


class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    billing_cycle = db.Column(db.String(20), default='monthly')
    max_chatbots = db.Column(db.Integer, default=1)
    max_messages_per_month = db.Column(db.Integer, default=100)
    max_training_data_size = db.Column(db.Integer, default=1000)
    features = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    subscriptions = db.relationship('Subscription', backref='plan', lazy=True)

    def __repr__(self):
        return f'<SubscriptionPlan {self.display_name}>'

    def get_features(self):
        """Parse features JSON"""
        if not self.features:
            return {}
        try:
            return json.loads(self.features)
        except (json.JSONDecodeError, TypeError):
            return {}


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    start_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    end_date = db.Column(db.DateTime(timezone=True))
    trial_end_date = db.Column(db.DateTime(timezone=True))
    is_trial = db.Column(db.Boolean, default=False)
    chatbots_created = db.Column(db.Integer, default=0)
    messages_this_month = db.Column(db.Integer, default=0)
    last_reset_date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    payment_method = db.Column(db.String(50))
    last_payment_date = db.Column(db.DateTime(timezone=True))
    next_billing_date = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def is_expired(self):
        """Check if subscription is expired"""
        now = datetime.now(timezone.utc)

        def _to_aware(dt):
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        if self.is_trial and self.trial_end_date:
            trial_end = _to_aware(self.trial_end_date)
            return now > trial_end

        if self.end_date:
            end = _to_aware(self.end_date)
            return now > end

        return False

    def days_remaining(self):
        """Get days remaining in subscription"""
        now = datetime.now(timezone.utc)

        def _to_aware(dt):
            if dt and dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        target_date = None
        if self.is_trial and self.trial_end_date:
            target_date = _to_aware(self.trial_end_date)
        elif self.end_date:
            target_date = _to_aware(self.end_date)

        if target_date:
            delta = target_date - now
            return max(0, delta.days)
        return 0

    def can_send_message(self):
        """Check if user can send another message"""
        if self.plan.max_messages_per_month == -1:
            return True
        return self.messages_this_month < self.plan.max_messages_per_month

    def can_create_chatbot(self):
        """Check if user can create another chatbot"""
        if self.plan.max_chatbots == -1:
            return True
        return self.chatbots_created < self.plan.max_chatbots

    def increment_chatbot_count(self):
        """Increment chatbot counter"""
        self.chatbots_created += 1
        self.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    def decrement_chatbot_count(self):
        """Decrement chatbot counter"""
        if self.chatbots_created > 0:
            self.chatbots_created -= 1
            self.updated_at = datetime.now(timezone.utc)
            db.session.commit()

    def increment_message_count(self):
        """Increment message counter"""
        self.messages_this_month += 1
        self.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    def reset_monthly_counters(self):
        """Reset monthly counters"""
        self.messages_this_month = 0
        self.last_reset_date = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        db.session.commit()

    def get_usage_stats(self):
        """Get usage statistics"""
        chatbot_limit = self.plan.max_chatbots
        message_limit = self.plan.max_messages_per_month

        return {
            'chatbots': {
                'used': self.chatbots_created,
                'limit': 'Unlimited' if chatbot_limit == -1 else chatbot_limit,
                'remaining': 'Unlimited' if chatbot_limit == -1 else max(0, chatbot_limit - self.chatbots_created),
                'percentage': 0 if chatbot_limit == -1 else min(100, (self.chatbots_created / chatbot_limit) * 100)
            },
            'messages': {
                'used': self.messages_this_month,
                'limit': 'Unlimited' if message_limit == -1 else message_limit,
                'remaining': 'Unlimited' if message_limit == -1 else max(0, message_limit - self.messages_this_month),
                'percentage': 0 if message_limit == -1 else min(100, (self.messages_this_month / message_limit) * 100)
            },
            'subscription': {
                'days_remaining': self.days_remaining(),
                'is_expired': self.is_expired(),
                'is_trial': self.is_trial,
                'status': self.status,
                'plan_name': self.plan.display_name
            }
        }

    def __repr__(self):
        return f'<Subscription user_id={self.user_id} plan={self.plan.name} status={self.status}>'