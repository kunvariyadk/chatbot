"""
Staging Controller
Handles preview, update, deploy and discard of staging Q&A pairs.

Flow
----
  1st train upload  → chatbot.is_trained is False  → goes directly into qa_pairs  (existing behaviour)
  2nd+ train upload → chatbot.is_trained is True   → goes into qa_pairs_staging for review

Staging actions available per chatbot:
  GET  /chatbot/staging/<chatbot_id>            → list all pending staging pairs
  POST /chatbot/staging/update/<staging_id>     → edit a single staging pair answer/question
  POST /chatbot/staging/deploy/<chatbot_id>     → merge ALL approved/pending into qa_pairs + delete from staging
  POST /chatbot/staging/discard/<chatbot_id>    → delete ALL staging rows for chatbot
  POST /chatbot/staging/preview/<chatbot_id>    → run a test question against staging data only (no KB change)
"""

from base import app, db
from flask import request, jsonify, session
from datetime import datetime, timezone

from base.com.vo.qa_pairs_staging_vo import QAPairStaging
from base.com.dao.chat_dao import get_chatbot_by_id
from base.com.controller.decorators import login_required, subscription_required


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _owned_chatbot(chatbot_id):
    """Return chatbot if it exists and belongs to the logged-in user, else None."""
    chatbot = get_chatbot_by_id(chatbot_id)
    if chatbot and chatbot.user_id == session.get('user_id'):
        return chatbot
    return None


def save_to_staging(chatbot_id: int, qa_list: list, added_by: int) -> int:
    """
    Insert qa_list rows into qa_pairs_staging with status='pending'.
    Returns the number of rows inserted.
    Called by training_controller when chatbot.is_trained is True (2nd+ upload).
    """
    count = 0
    for qa in qa_list:
        question = (qa.get('question') or '').strip()
        answer = (qa.get('answer') or '').strip()
        if not question or not answer:
            continue

        row = QAPairStaging(
            chatbot_id=chatbot_id,
            question=question,
            answer=answer,
            tag=qa.get('tag', ''),
            added_by=added_by,
            status='pending',
        )
        db.session.add(row)
        count += 1

    db.session.commit()
    print(f"✅ Saved {count} rows to staging for chatbot {chatbot_id}")
    return count


def chatbot_has_training(chatbot_id: int) -> bool:
    """Return True if the chatbot already has qa_pairs (i.e. is already trained)."""
    from base.com.vo.qa_pair_vo import QAPair
    return db.session.query(
        QAPair.query.filter_by(chatbot_id=chatbot_id).exists()
    ).scalar()


# ============================================================
# ROUTES
# ============================================================

@app.route('/chatbot/staging/<int:chatbot_id>', methods=['GET'])
@login_required
@subscription_required
def get_staging_pairs(chatbot_id):
    """List all pending staging pairs for a chatbot."""
    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    pairs = QAPairStaging.query.filter_by(
        chatbot_id=chatbot_id,
        status='pending'
    ).order_by(QAPairStaging.created_at.asc()).all()

    return jsonify({
        'success': True,
        'staging_pairs': [p.to_dict() for p in pairs],
        'count': len(pairs)
    })


@app.route('/chatbot/staging/update/<int:staging_id>', methods=['POST'])
@login_required
@subscription_required
def update_staging_pair(staging_id):
    """Edit a single staging pair's question / answer before deploying."""
    pair = QAPairStaging.query.get(staging_id)
    if not pair:
        return jsonify({'success': False, 'message': 'Staging pair not found'}), 404

    chatbot = _owned_chatbot(pair.chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json() or {}
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()

    if not question and not answer:
        return jsonify({'success': False, 'message': 'Question or answer required'})

    if question and len(question) > 500:
        return jsonify({'success': False, 'message': 'Question exceeds 500 characters'})
    if answer and len(answer) > 1000:
        return jsonify({'success': False, 'message': 'Answer exceeds 1000 characters'})

    if question:
        pair.question = question
    if answer:
        pair.answer = answer

    pair.updated_at = datetime.now(timezone.utc)
    pair.mark_tested()  # user reviewed it → mark tested
    db.session.commit()

    return jsonify({'success': True, 'message': 'Staging pair updated', 'pair': pair.to_dict()})


@app.route('/chatbot/staging/preview/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def preview_staging_response(chatbot_id):
    """
    Test a question against the staging data only.
    Does a simple keyword / exact-match lookup across staging pairs —
    does NOT touch the live KB or the ML model.
    """
    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json() or {}
    question = data.get('question', '').strip().lower()

    if not question:
        return jsonify({'success': False, 'message': 'Question is required'})

    pairs = QAPairStaging.query.filter_by(
        chatbot_id=chatbot_id,
        status='pending'
    ).all()

    if not pairs:
        return jsonify({'success': False, 'message': 'No staging data to preview'})

    # Mark all pairs as tested
    for p in pairs:
        if not p.tested_at:
            p.mark_tested()

    db.session.commit()

    # --- Exact match first ---
    for p in pairs:
        if p.question.strip().lower() == question:
            return jsonify({
                'success': True,
                'matched': True,
                'match_type': 'exact',
                'staging_id': p.id,
                'question': p.question,
                'answer': p.answer,
            })

    # --- Keyword / substring match ---
    best = None
    best_score = 0

    q_words = set(question.split())
    for p in pairs:
        p_words = set(p.question.strip().lower().split())
        overlap = len(q_words & p_words)
        if overlap > best_score:
            best_score = overlap
            best = p

    if best and best_score > 0:
        return jsonify({
            'success': True,
            'matched': True,
            'match_type': 'keyword',
            'staging_id': best.id,
            'question': best.question,
            'answer': best.answer,
            'score': best_score,
        })

    return jsonify({
        'success': True,
        'matched': False,
        'message': 'No matching staging pair found for this question',
    })


@app.route('/chatbot/staging/deploy/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def deploy_staging(chatbot_id):
    """
    Merge ALL pending staging pairs into qa_pairs.
    Skips duplicates, auto-generates tags, AND retrains the ML model.
    """
    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    pending = QAPairStaging.query.filter_by(
        chatbot_id=chatbot_id,
        status='pending'
    ).all()

    if not pending:
        return jsonify({'success': False, 'message': 'No pending staging pairs to deploy'})

    try:
        from base.com.vo.qa_pair_vo import QAPair
        from base.com.dao.qa_pair_dao import append_qa_pairs_to_db
        from base.com.controller.training_controller import regenerate_intents_from_db

        from base.com.utils.utils import preprocess_text
        # 1. Fetch live DB questions to handle updates/duplicates
        existing_live_qas = QAPair.query.filter_by(chatbot_id=chatbot_id).all()
        # Use preprocess_text to match the exact same normalization the chatbot uses!
        existing_questions = {preprocess_text(qa.question): qa for qa in existing_live_qas if qa.question}

        # 2. Find the absolute highest tag number currently in the live DB
        max_tag_num = 0
        for qa in existing_live_qas:
            if qa.tag and str(qa.tag).startswith('qa_'):
                try:
                    num = int(qa.tag.split('_')[1])
                    if num > max_tag_num:
                        max_tag_num = num
                except (ValueError, IndexError):
                    continue

        current_tag_index = max_tag_num + 1
        qa_list = []
        updated_count = 0
        skipped_count = 0

        # 3. Filter and assign guaranteed unique tags
        from datetime import datetime, timezone
        for p in pending:
            # Normalize exactly like the chatbot to catch punctuation differences
            q_clean = preprocess_text(p.question or '')

            if not q_clean:
                skipped_count += 1
                continue

            if q_clean in existing_questions:
                existing_qa = existing_questions[q_clean]
                if existing_qa is not True:
                    if existing_qa.answer != p.answer:
                        existing_qa.answer = p.answer
                        existing_qa.updated_at = datetime.now(timezone.utc)
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    skipped_count += 1
                continue

            existing_questions[q_clean] = True
            fresh_tag = f"qa_{current_tag_index}"

            qa_list.append({
                'question': p.question,
                'answer': p.answer,
                'tag': fresh_tag
            })

            current_tag_index += 1

        # 4. Save unique pairs to live DB
        if qa_list:
            append_qa_pairs_to_db(chatbot_id, qa_list)

        # 5. Mark all as processed and delete from staging
        for p in pending:
            p.mark_merged()
            p.status = 'approved'

        db.session.commit()

        QAPairStaging.query.filter_by(
            chatbot_id=chatbot_id,
            status='approved'
        ).delete()
        db.session.commit()

        # 6. Regenerate live JSON files AND RETRAIN ML MODEL
        if qa_list or updated_count > 0:
            regenerate_intents_from_db(chatbot_id)

            # ==========================================
            # 🌟 NEW FIX: Retrain the ML model!
            # ==========================================
            try:
                from base.com.service.model_training import train_chatbot_model
                from base.com.utils.utils import clear_model_cache

                print(f"🧠 Retraining ML model for chatbot {chatbot_id} with new staging data...")
                train_chatbot_model(chatbot.user_id, chatbot_id)
                clear_model_cache(chatbot.user_id, chatbot_id=chatbot_id)

                # Make sure the chatbot is set to use the newly trained ML model
                chatbot.use_ml_model = True
                chatbot.is_trained = True
                db.session.commit()
                print("✅ ML Retraining successful!")

            except Exception as ml_err:
                print(f"❌ ML training failed during deployment: {ml_err}")
                import traceback
                traceback.print_exc()
            # ==========================================

        print(f"✅ Deployed {len(qa_list)} staging pairs. Skipped {skipped_count} duplicates.")

        return jsonify({
            'success': True,
            'message': f'✅ Deployed {len(qa_list)} new pairs! (Skipped {skipped_count} duplicates)',
            'deployed_count': len(qa_list),
            'skipped_count': skipped_count
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Deploy error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Deploy failed: {str(e)}'}), 500


@app.route('/chatbot/staging/discard/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def discard_staging(chatbot_id):
    """Delete all pending staging pairs for a chatbot without merging."""
    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    deleted = QAPairStaging.query.filter_by(
        chatbot_id=chatbot_id,
        status='pending'
    ).delete()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Discarded {deleted} staging pair(s)',
        'discarded_count': deleted,
    })



@app.route('/chatbot/staging/test-live/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def test_live_response(chatbot_id):
    """
    ✅ DEBUG ROUTE: Run a question through the REAL chatbot matching logic.
    Shows exactly what KB entries exist, what patterns the chatbot sees, and
    what intent/confidence/answer it produces.
    """
    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json() or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'success': False, 'message': 'question is required'})

    try:
        from base.com.utils.utils import (
            load_knowledge_base, get_intent_with_confidence,
            get_response_from_kb, preprocess_text, SMART_CACHE
        )
        from base.com.vo.qa_pair_vo import QAPair

        # 1. What's in the raw database?
        db_pairs = QAPair.query.filter_by(chatbot_id=chatbot_id).all()
        db_summary = [{'id': p.id, 'tag': p.tag, 'question': p.question, 'answer': p.answer[:80]} for p in db_pairs]

        # 2. Force-clear ALL cache for this user so we get fresh data
        SMART_CACHE.clear_user(chatbot.user_id)

        # 3. What does load_knowledge_base build from DB?
        kb = load_knowledge_base(chatbot.user_id, chatbot_id=chatbot_id)
        kb_summary = []
        for item in kb:
            kb_summary.append({
                'tag': item.get('tag'),
                'patterns': item.get('patterns', []),
                'response_preview': (item.get('responses') or [''])[0][:80]
            })

        # 4. Run the REAL intent matching
        intent, confidence = get_intent_with_confidence(question, chatbot.user_id, chatbot_id=chatbot_id)

        # 5. Get the actual answer
        answer = None
        if intent:
            answer = get_response_from_kb(intent, chatbot.user_id, chatbot_id=chatbot_id)

        # 6. Check what preprocessed question looks like
        preprocessed = preprocess_text(question)

        return jsonify({
            'success': True,
            'question': question,
            'preprocessed_question': preprocessed,
            'db_pair_count': len(db_pairs),
            'kb_entry_count': len(kb),
            'matched_intent': intent,
            'confidence': round(confidence, 4),
            'answer': answer,
            'kb_entries': kb_summary,
            'db_pairs': db_summary,
        })

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()})


print("✅ Staging controller loaded successfully!")


# ============================================================
# PAGE ROUTE — renders staging.html
# ============================================================

# ============================================================
# PAGE ROUTE — renders staging.html
# ============================================================

@app.route('/chatbot/staging-page/<int:chatbot_id>', methods=['GET'])
@login_required
@subscription_required
def staging_page(chatbot_id):
    """Render the staging review page."""
    from flask import render_template
    from base.com.dao.user_dao import get_user_by_id
    from base.com.vo.qa_pairs_staging_vo import QAPairStaging # Make sure we import the model

    chatbot = _owned_chatbot(chatbot_id)
    if not chatbot:
        from flask import flash, redirect, url_for
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    user = get_user_by_id(session['user_id'])

    # 1. Fetch all pending staging items for this specific chatbot
    raw_staging_items = QAPairStaging.query.filter_by(
        chatbot_id=chatbot.id,
        status='pending'
    ).all()

    # 2. Convert the database objects into a clean list of dictionaries for JavaScript
    staging_items_list = []
    for item in raw_staging_items:
        staging_items_list.append({
            'id': item.id,
            'question': item.question,
            'answer': item.answer
        })

    # 3. Pass the data to the HTML template!
    return render_template(
        'staging.html',
        chatbot=chatbot,
        user=user,
        staging_items=staging_items_list  # 👈 This makes the data appear on the page!
    )

