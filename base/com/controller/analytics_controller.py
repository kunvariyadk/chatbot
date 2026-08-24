"""
Analytics Controller
Handles analytics dashboard and conversation transcript inspection
"""
from base import app, db
from flask import render_template, request, jsonify, session
from base.com.controller.decorators import login_required
from base.com.dao.chat_dao import get_chatbots_by_user, get_chatbot_by_id
from base.com.dao.user_dao import get_user_by_id

@app.route('/analytics')
@login_required
def analytics_dashboard():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    chatbots = get_chatbots_by_user(user_id)
    
    # Selected chatbot filter
    selected_bot_id = request.args.get('chatbot_id', type=int)
    selected_chatbot = None
    if selected_bot_id:
        selected_chatbot = get_chatbot_by_id(selected_bot_id)
        if selected_chatbot and selected_chatbot.user_id != user_id:
            selected_chatbot = None

    # Mock/Sample Analytics Data for Visual Layout Preview
    analytics_data = {
        'total_sessions': 142 if not selected_bot_id else 58,
        'total_messages': 896 if not selected_bot_id else 340,
        'avg_messages_per_session': 6.3 if not selected_bot_id else 5.8,
        'avg_confidence': 0.91 if not selected_bot_id else 0.94,
        'fallback_rate': 0.06 if not selected_bot_id else 0.04,
        'live_handoff_count': 12 if not selected_bot_id else 5,
        'avg_response_time': '1.1s'
    }

    # Sample top intents for charts
    top_intents = [
        {'intent': 'pricing_info', 'count': 45, 'percentage': 32},
        {'intent': 'feature_inquiry', 'count': 38, 'percentage': 27},
        {'intent': 'business_hours', 'count': 25, 'percentage': 18},
        {'intent': 'support_request', 'count': 20, 'percentage': 14},
        {'intent': 'general_greeting', 'count': 14, 'percentage': 9}
    ]

    # Sample unresolved fallback queries
    unresolved_queries = [
        {'query': 'Can I integrate with Shopify custom app?', 'count': 8, 'last_seen': '2 hours ago'},
        {'query': 'What is your refund policy for annual plans?', 'count': 5, 'last_seen': '5 hours ago'},
        {'query': 'Do you offer SLA for enterprise support?', 'count': 3, 'last_seen': '1 day ago'}
    ]

    # Sample recent chat sessions
    sample_sessions = [
        {
            'id': 1001,
            'chatbot_name': selected_chatbot.name if selected_chatbot else 'Customer Support Bot',
            'session_token': 'sess_99283811',
            'visitor_name': 'Alex Johnson',
            'user_ip': '192.168.1.45',
            'started_at': 'Aug 03, 2026 at 01:30 PM',
            'duration': '4m 12s',
            'message_count': 8,
            'avg_confidence': 96,
            'status': 'bot',
            'status_label': '🤖 Bot Handled'
        },
        {
            'id': 1002,
            'chatbot_name': selected_chatbot.name if selected_chatbot else 'Sales Inquiry Bot',
            'session_token': 'sess_77410294',
            'visitor_name': 'Sarah Miller',
            'user_ip': '203.0.113.19',
            'started_at': 'Aug 03, 2026 at 11:15 AM',
            'duration': '7m 45s',
            'message_count': 14,
            'avg_confidence': 88,
            'status': 'live',
            'status_label': '👨‍💻 Live Agent Escalated'
        },
        {
            'id': 1003,
            'chatbot_name': selected_chatbot.name if selected_chatbot else 'E-Commerce Helper',
            'session_token': 'sess_55192033',
            'visitor_name': 'David Kim',
            'user_ip': '198.51.100.82',
            'started_at': 'Aug 02, 2026 at 08:45 PM',
            'duration': '2m 10s',
            'message_count': 4,
            'avg_confidence': 42,
            'status': 'fallback',
            'status_label': '⚠️ High Fallback'
        }
    ]

    return render_template(
        'analytics.html',
        user=user,
        chatbots=chatbots,
        selected_chatbot=selected_chatbot,
        selected_bot_id=selected_bot_id,
        analytics=analytics_data,
        top_intents=top_intents,
        unresolved_queries=unresolved_queries,
        recent_sessions=sample_sessions
    )


@app.route('/api/analytics/session/<int:session_id>/messages')
@login_required
def get_session_transcript_api(session_id):
    """API endpoint to load full message history for the conversation modal"""
    # Sample mock transcript for preview
    sample_transcripts = {
        1001: [
            {'sender': 'user', 'text': 'Hi, what are your business operating hours?', 'time': '01:30 PM', 'intent': 'business_hours', 'confidence': 98},
            {'sender': 'bot', 'text': 'Hello! Our support team is available Monday through Friday from 9 AM to 6 PM EST.', 'time': '01:30 PM', 'intent': 'business_hours', 'confidence': 98},
            {'sender': 'user', 'text': 'Do you offer a free trial for the Pro plan?', 'time': '01:31 PM', 'intent': 'pricing_info', 'confidence': 95},
            {'sender': 'bot', 'text': 'Yes! We offer a 14-day free trial on our Pro plan with full access to all features.', 'time': '01:31 PM', 'intent': 'pricing_info', 'confidence': 95},
            {'sender': 'user', 'text': 'Awesome, thank you!', 'time': '01:32 PM', 'intent': 'default_thanks', 'confidence': 99},
            {'sender': 'bot', 'text': "You're very welcome! Let me know if you need anything else.", 'time': '01:32 PM', 'intent': 'default_thanks', 'confidence': 99}
        ],
        1002: [
            {'sender': 'user', 'text': 'I need custom enterprise SLA and dedicated hosting.', 'time': '11:15 AM', 'intent': 'support_request', 'confidence': 78},
            {'sender': 'bot', 'text': 'I can help with enterprise options! Would you like me to connect you with a live agent?', 'time': '11:15 AM', 'intent': 'support_request', 'confidence': 78},
            {'sender': 'user', 'text': 'Yes please transfer me.', 'time': '11:16 AM', 'intent': 'live_chat_transfer', 'confidence': 99},
            {'sender': 'bot', 'text': 'Connecting you with an enterprise specialist...', 'time': '11:16 AM', 'intent': 'system', 'confidence': 100},
            {'sender': 'owner', 'text': 'Hello Sarah! I am Mark from Enterprise Support. How can I help with your SLA requirements?', 'time': '11:17 AM', 'intent': 'human_agent', 'confidence': 100}
        ],
        1003: [
            {'sender': 'user', 'text': 'Can I integrate with Shopify custom app version 3?', 'time': '08:45 PM', 'intent': 'fallback', 'confidence': 35},
            {'sender': 'bot', 'text': "I'm sorry, I don't have details about Shopify custom app version 3 in my knowledge base.", 'time': '08:45 PM', 'intent': 'fallback', 'confidence': 35},
            {'sender': 'user', 'text': 'How do I issue refunds?', 'time': '08:46 PM', 'intent': 'pricing_info', 'confidence': 48},
            {'sender': 'bot', 'text': 'You can manage subscriptions in your account dashboard under Manage Subscription.', 'time': '08:46 PM', 'intent': 'pricing_info', 'confidence': 48}
        ]
    }
    
    messages = sample_transcripts.get(session_id, [
        {'sender': 'user', 'text': f'Sample message for session #{session_id}', 'time': '12:00 PM', 'intent': 'general', 'confidence': 90},
        {'sender': 'bot', 'text': 'This is a sample bot response demonstration.', 'time': '12:00 PM', 'intent': 'general', 'confidence': 90}
    ])
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'messages': messages
    })
