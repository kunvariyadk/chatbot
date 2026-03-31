"""
Q&A Controller
Handles Q&A pair management (get, update, delete, download)
"""
import os

from base import app, db
from flask import request, jsonify, send_file
import json
from io import BytesIO
from datetime import datetime, timezone

from base.com.vo.qa_pair_vo import QAPair
from base.com.vo.chatbot_vo import Chatbot
from base.com.dao.chat_dao import get_chatbot_by_id
from base.com.dao.qa_pair_dao import (
    get_qa_pairs_from_db,
    get_qa_pair_by_id,
    update_single_qa_pair,
    delete_qa_pair
)
from base.com.controller.decorators import subscription_required, login_required


# ============================================
# HELPER — convert QAPair model OR dict → dict
# ============================================
def qa_to_dict(qa):
    """
    Safely convert a QAPair model instance OR an already-dict value
    into a plain Python dict so we can use ['key'] notation everywhere.
    """
    if qa is None:
        return None

    # Already a dict — return as-is
    if isinstance(qa, dict):
        return qa

    # SQLAlchemy model instance — convert via __dict__ or attributes
    return {
        'id': getattr(qa, 'id', None),
        'chatbot_id': getattr(qa, 'chatbot_id', None),
        'question': getattr(qa, 'question', ''),
        'answer': getattr(qa, 'answer', ''),
        'tag': getattr(qa, 'tag', ''),
        'created_at': (
            qa.created_at.isoformat()
            if getattr(qa, 'created_at', None) else None
        ),
        'updated_at': (
            qa.updated_at.isoformat()
            if getattr(qa, 'updated_at', None) else None
        ),
    }


def qa_list_to_dicts(qa_list):
    """Convert a list of QAPair models or dicts to a list of dicts."""
    if not qa_list:
        return []
    return [qa_to_dict(qa) for qa in qa_list]


# ============================================
# REGENERATE INTENTS
# ============================================
def regenerate_intents_from_db(chatbot_id):
    """Regenerate intents and KB for specific chatbot"""
    try:
        from base.com.service.file_service import ensure_chatbot_folder

        chatbot = get_chatbot_by_id(chatbot_id)
        if not chatbot:
            return False

        raw_pairs = get_qa_pairs_from_db(chatbot_id)
        qa_pairs = qa_list_to_dicts(raw_pairs)

        intents = []
        for qa in qa_pairs:
            intents.append({
                'tag': qa.get('tag') or f'qa_{qa.get("id")}',
                'patterns': [qa.get('question')],
                'responses': [qa.get('answer')]
            })

        intents_data = {'intents': intents}
        chatbot.training_data = json.dumps(intents_data)

        chatbot_folder = ensure_chatbot_folder(chatbot.user_id, chatbot_id)

        intents_path = os.path.join(chatbot_folder, 'intents.json')
        with open(intents_path, 'w', encoding='utf-8') as f:
            json.dump(intents_data, f, indent=2)

        kb_path = os.path.join(chatbot_folder, 'knowledge_base.json')

        knowledge_base = []
        for intent in intents:
            knowledge_base.append({
                'intent': intent['tag'],
                'tag': intent['tag'],
                'patterns': intent['patterns'],
                'responses': intent['responses'],
                'chatbot_id': chatbot_id
            })

        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge_base, f, indent=2, ensure_ascii=False)

        chatbot.intents_path = intents_path
        db.session.commit()

        # Clear cache
        try:
            from utils import clear_model_cache
            clear_model_cache(chatbot.user_id, chatbot_id=chatbot_id)
        except Exception:
            pass

        return True

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error regenerating intents: {e}")
        return False


# ============================================
# Q&A MANAGEMENT ROUTES
# ============================================

@app.route('/chatbot/get-qa-pairs/<int:chatbot_id>', methods=['GET'])
@login_required
@subscription_required
def get_qa_pairs(chatbot_id):
    """Get Q&A pairs with timestamps"""
    from flask import session

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        raw_pairs = get_qa_pairs_from_db(chatbot_id)
        qa_pairs = qa_list_to_dicts(raw_pairs)

        # Fallback: parse training_data JSON if DB has no records
        if not qa_pairs and chatbot.training_data:
            training_data = json.loads(chatbot.training_data)
            intents = training_data.get('intents', [])

            qa_pairs = []
            for intent in intents:
                patterns = intent.get('patterns', [])
                responses = intent.get('responses', [])

                if patterns and responses:
                    qa_pairs.append({
                        'id': None,
                        'question': patterns[0],
                        'answer': responses[0],
                        'tag': intent.get('tag', ''),
                        'created_at': None,
                        'updated_at': None
                    })

        return jsonify({
            'success': True,
            'qa_pairs': qa_pairs,
            'count': len(qa_pairs)
        })

    except Exception as e:
        print(f"Get Q&A error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load Q&A pairs'})


@app.route('/chatbot/update-qa-pair/<int:qa_id>', methods=['POST'])
@login_required
@subscription_required
def update_qa_pair_route(qa_id):
    """Update Q&A pair"""
    from flask import session

    try:
        data = request.get_json()
        question = data.get('question')
        answer = data.get('answer')

        if not question and not answer:
            return jsonify({'success': False, 'message': 'Question or answer required'})

        # FIX: convert to dict so ['key'] access works
        raw_pair = get_qa_pair_by_id(qa_id)
        qa_pair = qa_to_dict(raw_pair)

        if not qa_pair:
            return jsonify({'success': False, 'message': 'Q&A pair not found'})

        chatbot = get_chatbot_by_id(qa_pair['chatbot_id'])
        if chatbot.user_id != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        # Validate lengths
        if question and len(question) > 500:
            return jsonify({'success': False, 'message': 'Question exceeds 500 characters'})

        if answer and len(answer) > 1000:
            return jsonify({'success': False, 'message': 'Answer exceeds 1000 characters'})

        # Update in database
        success = update_single_qa_pair(qa_id, question=question, answer=answer)

        if not success:
            return jsonify({'success': False, 'message': 'Failed to update'})

        # Regenerate intents
        regenerate_intents_from_db(qa_pair['chatbot_id'])

        return jsonify({
            'success': True,
            'message': 'Q&A pair updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Update error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/chatbot/delete-qa-pair/<int:qa_id>', methods=['POST'])
@login_required
@subscription_required
def delete_qa_pair_route(qa_id):
    """Delete a single Q&A pair"""
    from flask import session

    try:
        # FIX: convert to dict so ['key'] access works
        raw_pair = get_qa_pair_by_id(qa_id)
        qa_pair = qa_to_dict(raw_pair)

        if not qa_pair:
            return jsonify({'success': False, 'message': 'Q&A pair not found'})

        # Check ownership
        chatbot = get_chatbot_by_id(qa_pair['chatbot_id'])
        if chatbot.user_id != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        chatbot_id = qa_pair['chatbot_id']

        if delete_qa_pair(qa_id):
            # Regenerate intents
            regenerate_intents_from_db(chatbot_id)

            return jsonify({
                'success': True,
                'message': 'Q&A pair deleted successfully!'
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to delete Q&A pair'})

    except Exception as e:
        print(f"Delete Q&A error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@app.route('/chatbot/download-intents/<int:chatbot_id>', methods=['GET'])
@login_required
@subscription_required
def download_intents(chatbot_id):
    """Download intents as JSON file"""
    from flask import session

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not chatbot.training_data:
        return jsonify({'success': False, 'message': 'No training data available'}), 404

    try:
        training_data = json.loads(chatbot.training_data)

        json_data = BytesIO()
        json_data.write(json.dumps(training_data, indent=2, ensure_ascii=False).encode('utf-8'))
        json_data.seek(0)

        # Sanitize filename
        safe_name = "".join(
            c for c in chatbot.name if c.isalnum() or c in (' ', '-', '_')
        ).strip()
        filename = f"{safe_name}_intents.json"

        return send_file(
            json_data,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        print(f"Download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to download intents'}), 500


@app.route('/chatbot/delete-training/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def delete_training_data(chatbot_id):
    """Delete all training data"""
    from flask import session

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Delete QA pairs from database
        QAPair.query.filter_by(chatbot_id=chatbot_id).delete()

        # Clear chatbot training data
        chatbot.training_data = None
        chatbot.training_file = None
        chatbot.is_trained = False

        db.session.commit()

        # Delete chatbot-specific files
        from base.com.service.file_service import get_chatbot_folder
        import shutil

        chatbot_folder = get_chatbot_folder(chatbot.user_id, chatbot_id)
        if os.path.exists(chatbot_folder):
            shutil.rmtree(chatbot_folder)
            print(f"Deleted chatbot folder: {chatbot_folder}")

        # Clear cache
        try:
            from base.com.utils.utils import clear_model_cache
            clear_model_cache(chatbot.user_id, chatbot_id=chatbot_id)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': 'Training data deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Delete training error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


print("✅ Q&A controller loaded successfully!")
