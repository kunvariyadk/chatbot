"""
Training Controller
Handles chatbot training with JSON, text, Excel uploads and manual Q&A entry
"""
from base import app, db
from flask import request, redirect, url_for, session, flash, jsonify, render_template
import json
import os

from base.com.vo.chatbot_vo import Chatbot
from base.com.dao.user_dao import get_user_by_id
from base.com.dao.chat_dao import get_chatbot_by_id, get_chatbots_by_user
from base.com.dao.qa_pair_dao import save_qa_pairs_to_db, append_qa_pairs_to_db, get_qa_pairs_from_db
from base.com.service.file_service import get_chatbot_folder, ensure_chatbot_folder
from base.com.controller.decorators import subscription_required, login_required

from base.com.controller.staging_controller import save_to_staging, chatbot_has_training


def validate_and_convert_training_data(data):
    """Validate training data format"""
    if not isinstance(data, dict):
        return None

    if 'intents' in data:
        intents = data['intents']
        if isinstance(intents, list) and len(intents) > 0:
            for intent in intents:
                if not all(k in intent for k in ['tag', 'patterns', 'responses']):
                    return None
            return data

    if 'training_data' in data:
        training_data = data['training_data']
        if isinstance(training_data, list):
            intents = []
            for idx, item in enumerate(training_data):
                if 'question' in item and 'answer' in item:
                    intents.append({
                        'tag': f'qa_{idx + 1}',
                        'patterns': [item['question']],
                        'responses': [item['answer']]
                    })
            if intents:
                return {'intents': intents}

    if isinstance(data, list):
        intents = []
        for idx, item in enumerate(data):
            if isinstance(item, dict) and 'question' in item and 'answer' in item:
                intents.append({
                    'tag': f'qa_{idx + 1}',
                    'patterns': [item['question']],
                    'responses': [item['answer']]
                })
        if intents:
            return {'intents': intents}

    return None


def get_existing_training_data(chatbot_id):
    """Get existing training data from database"""
    try:
        chatbot = get_chatbot_by_id(chatbot_id)
        if not chatbot or not chatbot.training_data:
            return None
        return json.loads(chatbot.training_data)
    except Exception as e:
        print(f"Error loading existing training data: {e}")
        return None


def get_max_tag_number(intents):
    """Get maximum tag number from existing intents"""
    max_num = 0
    for intent in intents:
        tag = intent.get('tag', '')
        if tag.startswith('qa_'):
            try:
                num = int(tag.split('_')[1])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                continue
    return max_num


def build_qa_list_from_intents(converted_data):
    """
    Build flat Q&A list from intents — saves EVERY pattern as its own row.
    """
    qa_list = []
    for intent in converted_data.get('intents', []):
        patterns = intent.get('patterns', [])
        responses = intent.get('responses', [])
        tag = intent.get('tag', '')

        if not patterns or not responses:
            continue

        answer = responses[0]

        for pattern in patterns:
            if pattern and str(pattern).strip():
                qa_list.append({
                    'question': str(pattern).strip(),
                    'answer': answer,
                    'tag': tag
                })

    return qa_list


def regenerate_intents_from_db(chatbot_id):
    """
    Regenerate intents and KB for specific chatbot only.
    """
    try:
        chatbot = get_chatbot_by_id(chatbot_id)
        if not chatbot:
            return False

        qa_pairs = get_qa_pairs_from_db(chatbot_id)

        tag_map = {}  # tag -> {patterns: [], responses: []}
        for qa in qa_pairs:
            tag = qa.get('tag') or f'qa_{qa.get("id")}'
            question = qa.get('question', '')
            answer = qa.get('answer', '')

            if not question or not answer:
                continue

            if tag not in tag_map:
                tag_map[tag] = {'patterns': [], 'responses': [answer]}
            tag_map[tag]['patterns'].append(question)

        intents = [
            {
                'tag': tag,
                'patterns': data['patterns'],
                'responses': data['responses']
            }
            for tag, data in tag_map.items()
        ]

        intents_data = {'intents': intents}
        chatbot.training_data = json.dumps(intents_data)

        chatbot_folder = ensure_chatbot_folder(chatbot.user_id, chatbot_id)

        intents_path = os.path.join(chatbot_folder, 'intents.json')
        with open(intents_path, 'w', encoding='utf-8') as f:
            json.dump(intents_data, f, indent=2)

        kb_path = os.path.join(chatbot_folder, 'knowledge_base.json')
        knowledge_base = [
            {
                'intent': intent['tag'],
                'tag': intent['tag'],
                'patterns': intent['patterns'],
                'responses': intent['responses'],
                'chatbot_id': chatbot_id
            }
            for intent in intents
        ]

        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(knowledge_base, f, indent=2, ensure_ascii=False)

        chatbot.intents_path = intents_path
        db.session.commit()

        try:
            from utils import clear_model_cache
            clear_model_cache(chatbot.user_id, chatbot_id=chatbot_id)
        except:
            pass

        print(f"✅ Regenerated intents and KB for chatbot {chatbot_id} "
              f"({len(intents)} intents, {len(qa_pairs)} patterns total)")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error regenerating intents: {e}")
        import traceback
        traceback.print_exc()
        return False


def parse_text_content(content):
    """Enhanced parser for text/HTML content to extract Q&A pairs"""
    import re
    from html.parser import HTMLParser

    class MLStripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self.reset()
            self.strict = False
            self.convert_charrefs = True
            self.text = []

        def handle_data(self, d):
            self.text.append(d)

        def get_data(self):
            return ''.join(self.text)

    stripper = MLStripper()
    try:
        stripper.feed(content)
        text = stripper.get_data()
    except:
        text = content

    qa_pairs = []

    qa_pattern = re.compile(
        r'(?:^|\n)\s*Q(?:uestion)?[:.\s]+(.+?)\s*(?:\n|$)\s*A(?:nswer)?[:.\s]+(.+?)(?=\n\s*Q(?:uestion)?[:.\s]|$)',
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    matches = qa_pattern.findall(text)
    if matches:
        for q, a in matches:
            q_clean = re.sub(r'\s+', ' ', q.strip())
            a_clean = re.sub(r'\s+', ' ', a.strip())
            if len(q_clean) > 3 and len(a_clean) > 3:
                qa_pairs.append({'question': q_clean, 'answer': a_clean})
        if qa_pairs:
            return qa_pairs

    numbered_pattern = re.compile(
        r'\d+\.\s*Q(?:uestion)?[:.\s]+(.+?)\s*A(?:nswer)?[:.\s]+(.+?)(?=\d+\.\s*Q(?:uestion)?[:.\s]|$)',
        re.IGNORECASE | re.DOTALL
    )
    matches = numbered_pattern.findall(text)
    if matches:
        for q, a in matches:
            q_clean = re.sub(r'\s+', ' ', q.strip())
            a_clean = re.sub(r'\s+', ' ', a.strip())
            if len(q_clean) > 3 and len(a_clean) > 3:
                qa_pairs.append({'question': q_clean, 'answer': a_clean})
        if qa_pairs:
            return qa_pairs

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    clean_lines = []
    for line in lines:
        if (len(line) < 5 or
                line.lower().startswith(('http', 'www', '©', 'copyright', 'all rights')) or
                line.lower() in ['faq', 'q&a', 'questions', 'answers']):
            continue
        line = re.sub(r'^\d+[.)]\s*', '', line)
        if len(line) > 5:
            clean_lines.append(line)

    for i in range(0, len(clean_lines) - 1, 2):
        question = clean_lines[i]
        answer = clean_lines[i + 1] if i + 1 < len(clean_lines) else ''
        if (question and answer and
                10 <= len(question) <= 300 and
                10 <= len(answer) <= 1000 and
                question.lower() != answer.lower()):
            qa_pairs.append({'question': question, 'answer': answer})

    seen = set()
    unique_pairs = []
    for pair in qa_pairs:
        key = (pair['question'].lower(), pair['answer'].lower())
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)

    return unique_pairs


# ============================================
# TRAINING ROUTES
# ============================================

@app.route('/chatbot/train/<int:chatbot_id>', methods=['GET', 'POST'])
@login_required
@subscription_required
def train_chatbot(chatbot_id):
    """Main training page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('dashboard'))

    user_id = session['user_id']
    chatbot_folder = get_chatbot_folder(chatbot.user_id, chatbot_id)
    os.makedirs(chatbot_folder, exist_ok=True)

    if request.method == 'POST':
        upload_mode = request.form.get('upload_mode', 'append')

        # ── JSON file upload ──────────────────────────────────────────────
        if 'training_file' in request.files:
            file = request.files['training_file']

            if file and file.filename:
                if not file.filename.lower().endswith('.json'):
                    return jsonify({'success': False, 'message': 'Please upload a JSON file'})

                try:
                    file_content = file.read().decode('utf-8')
                    parsed_data = json.loads(file_content)
                    converted_data = validate_and_convert_training_data(parsed_data)

                    if not converted_data:
                        return jsonify({'success': False, 'message': 'Invalid training data format'})

                    # Append mode — offset tags for the new intents
                    if upload_mode == 'append':
                        existing_data = get_existing_training_data(chatbot_id)
                        new_intents = converted_data.get('intents', [])

                        if existing_data:
                            existing_intents = existing_data.get('intents', [])
                            max_tag_num = get_max_tag_number(existing_intents)

                            for intent in new_intents:
                                max_tag_num += 1
                                intent['tag'] = f'qa_{max_tag_num}'

                        # FIX: Isolate ONLY new intents so staging doesn't receive existing data
                        converted_data = {'intents': new_intents}

                    qa_list = build_qa_list_from_intents(converted_data)

                    # ── STAGING GATE ──────────────────────────────────────────────────
                    # ONLY send to staging if user wants to APPEND to an already trained bot.
                    if upload_mode == 'append' and chatbot.is_trained and chatbot_has_training(chatbot_id):
                        staged_count = save_to_staging(
                            chatbot_id, qa_list, added_by=session['user_id']
                        )
                        return jsonify({
                            'success': True,
                            'staged': True,
                            'message': (
                                f'✅ {staged_count} Q&A pairs sent to staging for review. '
                                f'Preview and deploy from the Staging tab.'
                            ),
                            'staged_count': staged_count,
                            'ml_trained': False,
                        })
                    # ── END STAGING GATE ─────────────────────────────────────────────

                    # If REPLACE ALL, wipe the live DB and any lingering staging drafts
                    if upload_mode == 'replace':
                        from base.com.vo.qa_pairs_staging_vo import QAPairStaging
                        QAPairStaging.query.filter_by(chatbot_id=chatbot_id).delete()
                        db.session.commit()
                        save_qa_pairs_to_db(chatbot_id, qa_list)
                    else:
                        append_qa_pairs_to_db(chatbot_id, qa_list)

                    # Save intents.json to disk
                    intents_path = os.path.join(chatbot_folder, 'intents.json')
                    with open(intents_path, 'w', encoding='utf-8') as f:
                        json.dump(converted_data, f, indent=2)

                    chatbot.training_data = json.dumps(converted_data)
                    chatbot.intents_path = intents_path
                    chatbot.training_file = file.filename
                    chatbot.trained_folder = os.path.join(chatbot_folder, 'models')
                    chatbot.is_trained = True
                    db.session.commit()

                    print(f"\n{'=' * 60}")
                    print(f"🤖 AUTO-TRAINING ML MODEL FOR CHATBOT {chatbot_id}")
                    print(f"{'=' * 60}\n")

                    try:
                        from base.com.service.model_training import train_chatbot_model
                        from base.com.utils.utils import clear_model_cache

                        train_result = train_chatbot_model(user_id, chatbot_id)
                        clear_model_cache(user_id, chatbot_id=chatbot_id)

                        chatbot.use_ml_model = True
                        db.session.commit()

                        action = "appended to" if upload_mode == 'append' else "trained"
                        return jsonify({
                            'success': True,
                            'message': (
                                f'✅ Successfully {action} '
                                f'{len(converted_data.get("intents", []))} intents '
                                f'({len(qa_list)} patterns) '
                                f'with {train_result.get("accuracy", 0):.1%} accuracy!'
                            ),
                            'intent_count': len(converted_data.get('intents', [])),
                            'pattern_count': len(qa_list),
                            'ml_trained': True,
                            'chatbot_id': chatbot_id
                        })
                    except Exception as e:
                        print(f"❌ ML training error: {e}")
                        return jsonify({
                            'success': True,
                            'message': f'✅ Training data saved ({len(qa_list)} patterns), but ML training failed: {str(e)}',
                            'intent_count': len(converted_data.get('intents', [])),
                            'pattern_count': len(qa_list),
                            'ml_trained': False
                        })

                except json.JSONDecodeError:
                    return jsonify({'success': False, 'message': 'Invalid JSON format'})
                except Exception as e:
                    print(f"File upload error: {e}")
                    return jsonify({'success': False, 'message': f'Error: {str(e)}'})

        # ── Manual / inline JSON entry ────────────────────────────────────
        if request.is_json or request.form.get('training_data'):
            try:
                if request.is_json:
                    data = request.get_json()
                    training_data_str = data.get('training_data')
                    upload_mode = data.get('upload_mode', 'append')
                else:
                    training_data_str = request.form.get('training_data')
                    upload_mode = request.form.get('upload_mode', 'append')

                if not training_data_str:
                    return jsonify({'success': False, 'message': 'No training data provided'})

                parsed_data = json.loads(training_data_str)
                converted_data = validate_and_convert_training_data(parsed_data)

                if not converted_data:
                    return jsonify({'success': False, 'message': 'Invalid training data format'})

                if upload_mode == 'append':
                    existing_data = get_existing_training_data(chatbot_id)
                    new_intents = converted_data.get('intents', [])

                    if existing_data:
                        existing_intents = existing_data.get('intents', [])
                        max_tag_num = get_max_tag_number(existing_intents)

                        for intent in new_intents:
                            max_tag_num += 1
                            intent['tag'] = f'qa_{max_tag_num}'

                    # FIX: Isolate ONLY new intents
                    converted_data = {'intents': new_intents}

                qa_list = build_qa_list_from_intents(converted_data)

                # ── STAGING GATE ─────────────────────────────────────────────────
                if upload_mode == 'append' and chatbot.is_trained and chatbot_has_training(chatbot_id):
                    staged_count = save_to_staging(
                        chatbot_id, qa_list, added_by=session['user_id']
                    )
                    return jsonify({
                        'success': True,
                        'staged': True,
                        'message': (
                            f'✅ {staged_count} Q&A pairs sent to staging for review. '
                            f'Preview and deploy from the Staging tab.'
                        ),
                        'staged_count': staged_count,
                        'ml_trained': False,
                    })
                # ── END STAGING GATE ─────────────────────────────────────────────

                if upload_mode == 'replace':
                    from base.com.vo.qa_pairs_staging_vo import QAPairStaging
                    QAPairStaging.query.filter_by(chatbot_id=chatbot_id).delete()
                    db.session.commit()
                    save_qa_pairs_to_db(chatbot_id, qa_list)
                else:
                    append_qa_pairs_to_db(chatbot_id, qa_list)

                regenerate_intents_from_db(chatbot_id)

                chatbot.training_file = 'manual_entry.json'
                chatbot.is_trained = True
                db.session.commit()

                try:
                    from base.com.service.model_training import train_chatbot_model
                    from base.com.utils.utils import clear_model_cache

                    train_result = train_chatbot_model(user_id, chatbot_id)
                    clear_model_cache(user_id, chatbot_id=chatbot_id)

                    chatbot.use_ml_model = True
                    db.session.commit()

                    action = "appended and trained" if upload_mode == 'append' else "trained"
                    return jsonify({
                        'success': True,
                        'message': f'✅ Successfully {action} {len(converted_data.get("intents", []))} intents ({len(qa_list)} patterns)!',
                        'intent_count': len(converted_data.get('intents', [])),
                        'pattern_count': len(qa_list),
                        'ml_trained': True,
                        'chatbot_id': chatbot_id
                    })
                except Exception as e:
                    return jsonify({
                        'success': True,
                        'message': f'✅ Training data saved ({len(qa_list)} patterns), but ML training failed',
                        'intent_count': len(converted_data.get('intents', [])),
                        'pattern_count': len(qa_list),
                        'ml_trained': False
                    })

            except json.JSONDecodeError:
                return jsonify({'success': False, 'message': 'Invalid JSON format'})
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error: {str(e)}'})

    # GET request
    user = get_user_by_id(session['user_id'])
    chatbots = get_chatbots_by_user(user.id)
    return render_template('train_chatbot.html', chatbot=chatbot, chatbots=chatbots, user=user)


@app.route('/chatbot/train-text/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def train_chatbot_text(chatbot_id):
    """Handle text/HTML upload"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if 'text_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})

    file = request.files['text_file']
    upload_mode = request.form.get('upload_mode', 'append')

    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file selected'})

    allowed_extensions = ['.txt', '.html', '.htm']
    file_ext = file.filename[file.filename.rfind('.'):].lower()

    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'message': 'Please upload a TXT or HTML file'})

    try:
        content = file.read().decode('utf-8', errors='ignore')
        qa_pairs = parse_text_content(content)

        if not qa_pairs:
            return jsonify({
                'success': False,
                'message': 'Could not extract Q&A pairs from file. Please check the format.'
            })

        start_index = 1
        if upload_mode == 'append':
            existing_data = get_existing_training_data(chatbot_id)
            if existing_data:
                existing_intents = existing_data.get('intents', [])
                start_index = get_max_tag_number(existing_intents) + 1

        qa_list = [
            {
                'question': qa['question'],
                'answer': qa['answer'],
                'tag': f'qa_{start_index + idx}'
            }
            for idx, qa in enumerate(qa_pairs)
        ]

        # ── STAGING GATE ─────────────────────────────────────────────────────
        if upload_mode == 'append' and chatbot.is_trained and chatbot_has_training(chatbot_id):
            staged_count = save_to_staging(
                chatbot_id, qa_list, added_by=session['user_id']
            )
            return jsonify({
                'success': True,
                'staged': True,
                'message': (
                    f'✅ {staged_count} Q&A pairs sent to staging for review. '
                    f'Preview and deploy from the Staging tab.'
                ),
                'staged_count': staged_count,
                'ml_trained': False,
            })
        # ── END STAGING GATE ─────────────────────────────────────────────────

        if upload_mode == 'replace':
            from base.com.vo.qa_pairs_staging_vo import QAPairStaging
            QAPairStaging.query.filter_by(chatbot_id=chatbot_id).delete()
            db.session.commit()
            save_qa_pairs_to_db(chatbot_id, qa_list)
        else:
            append_qa_pairs_to_db(chatbot_id, qa_list)

        regenerate_intents_from_db(chatbot_id)

        chatbot.is_trained = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'✅ Extracted and saved {len(qa_pairs)} Q&A pairs!',
            'intent_count': len(qa_pairs),
            'ml_trained': False
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error processing file: {str(e)}'})


@app.route('/chatbot/train-excel/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def train_chatbot_excel(chatbot_id):
    """Handle Excel file upload"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if 'excel_file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})

    file = request.files['excel_file']
    upload_mode = request.form.get('upload_mode', 'append')

    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file selected'})

    allowed_extensions = ['.xlsx', '.xls', '.csv']
    file_ext = file.filename[file.filename.rfind('.'):].lower()

    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'message': 'Please upload an Excel or CSV file'})

    try:
        import pandas as pd
        from io import BytesIO

        file_bytes = BytesIO(file.read())
        df = pd.read_csv(file_bytes) if file_ext == '.csv' else pd.read_excel(file_bytes)

        if 'Question' not in df.columns or 'Answer' not in df.columns:
            return jsonify({
                'success': False,
                'message': 'Excel file must have "Question" and "Answer" columns'
            })

        qa_pairs = []
        for _, row in df.iterrows():
            question = str(row['Question']).strip()
            answer = str(row['Answer']).strip()
            if question and answer and question != 'nan' and answer != 'nan':
                qa_pairs.append({'question': question, 'answer': answer})

        if not qa_pairs:
            return jsonify({'success': False, 'message': 'No valid Q&A pairs found in Excel file'})

        start_index = 1
        if upload_mode == 'append':
            existing_data = get_existing_training_data(chatbot_id)
            if existing_data:
                existing_intents = existing_data.get('intents', [])
                start_index = get_max_tag_number(existing_intents) + 1

        qa_list = [
            {
                'question': qa['question'],
                'answer': qa['answer'],
                'tag': f'qa_{start_index + idx}'
            }
            for idx, qa in enumerate(qa_pairs)
        ]

        # ── STAGING GATE ─────────────────────────────────────────────────────
        if upload_mode == 'append' and chatbot.is_trained and chatbot_has_training(chatbot_id):
            staged_count = save_to_staging(
                chatbot_id, qa_list, added_by=session['user_id']
            )
            return jsonify({
                'success': True,
                'staged': True,
                'message': (
                    f'✅ {staged_count} Q&A pairs sent to staging for review. '
                    f'Preview and deploy from the Staging tab.'
                ),
                'staged_count': staged_count,
                'ml_trained': False,
            })
        # ── END STAGING GATE ─────────────────────────────────────────────────

        if upload_mode == 'replace':
            from base.com.vo.qa_pairs_staging_vo import QAPairStaging
            QAPairStaging.query.filter_by(chatbot_id=chatbot_id).delete()
            db.session.commit()
            save_qa_pairs_to_db(chatbot_id, qa_list)
        else:
            append_qa_pairs_to_db(chatbot_id, qa_list)

        regenerate_intents_from_db(chatbot_id)

        chatbot.is_trained = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'✅ Imported {len(qa_pairs)} Q&A pairs from Excel!',
            'intent_count': len(qa_pairs),
            'ml_trained': False
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error processing file: {str(e)}'})


@app.route('/chatbot/train-manual/<int:chatbot_id>', methods=['POST'])
@login_required
@subscription_required
def train_chatbot_manual(chatbot_id):
    """Handle manual Q&A entry"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    chatbot = get_chatbot_by_id(chatbot_id)

    if not chatbot or chatbot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        from base.com.vo.qa_pair_vo import QAPair
        from datetime import datetime, timezone

        data = request.get_json()
        qa_pairs = data.get('qa_pairs', [])
        upload_mode = data.get('upload_mode', 'append')

        if not qa_pairs:
            return jsonify({'success': False, 'message': 'No Q&A pairs provided'})

        start_index = 1
        if upload_mode == 'append':
            existing_data = get_existing_training_data(chatbot_id)
            if existing_data:
                existing_intents = existing_data.get('intents', [])
                start_index = get_max_tag_number(existing_intents) + 1

        qa_list = []
        for idx, qa in enumerate(qa_pairs):
            question = qa.get('question', '').strip()
            answer = qa.get('answer', '').strip()
            qa_id = qa.get('id')

            if not question or not answer:
                continue

            # Editing an existing row
            if qa_id and isinstance(qa_id, int):
                existing_qa = QAPair.query.get(qa_id)
                if existing_qa and existing_qa.chatbot_id == chatbot_id:
                    existing_qa.question = question
                    existing_qa.answer = answer
                    existing_qa.updated_at = datetime.now(timezone.utc)
                    continue

            qa_list.append({
                'question': question,
                'answer': answer,
                'tag': f'qa_{start_index + idx}'
            })

        # ── STAGING GATE ─────────────────────────────────────────────────────
        if upload_mode == 'append' and qa_list and chatbot.is_trained and chatbot_has_training(chatbot_id):
            staged_count = save_to_staging(
                chatbot_id, qa_list, added_by=session['user_id']
            )
            db.session.commit()
            return jsonify({
                'success': True,
                'staged': True,
                'message': (
                    f'✅ {staged_count} Q&A pairs sent to staging for review. '
                    f'Preview and deploy from the Staging tab.'
                ),
                'staged_count': staged_count,
                'ml_trained': False,
            })
        # ── END STAGING GATE ─────────────────────────────────────────────────

        if qa_list:
            if upload_mode == 'replace':
                from base.com.vo.qa_pairs_staging_vo import QAPairStaging
                QAPairStaging.query.filter_by(chatbot_id=chatbot_id).delete()
                db.session.commit()
                save_qa_pairs_to_db(chatbot_id, qa_list)
            else:
                append_qa_pairs_to_db(chatbot_id, qa_list)

        db.session.commit()

        regenerate_intents_from_db(chatbot_id)

        chatbot.is_trained = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'✅ Successfully saved {len(qa_pairs)} Q&A pairs!',
            'intent_count': len(qa_pairs),
            'ml_trained': False
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


print("✅ Training controller loaded successfully!")
