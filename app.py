"""
Application Entry Point
Imports the configured Flask app from base package
"""
from base import app, db
# from base.com.dao.subscription_dao import initialize_subscription_plans
# from base.com.vo.subscription_vo import SubscriptionPlan

# For WSGI servers (Gunicorn, uWSGI, etc.)
application = app

if __name__ == '__main__':
    # Development server
    with app.app_context():
        # Create all database tables
        db.create_all()

        # Initialize subscription plans if needed
    #     if SubscriptionPlan.query.count() == 0:
    #         initialize_subscription_plans()
    #         print("✅ Subscription plans initialized")
    #
    # # Run development server
    # print("\n" + "=" * 60)
    # print("🚀 Starting Chatbot Panel Development Server")
    # print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)