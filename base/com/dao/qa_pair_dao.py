"""
QA Pair Data Access Object
Database operations for QA pairs
"""
from base import db
from base.com.vo.qa_pair_vo import QAPair
from datetime import datetime, timezone


def save_qa_pairs_to_db(chatbot_id, qa_data_list):
    """Save or replace all QA pairs for a chatbot"""
    try:
        # Delete existing pairs
        QAPair.query.filter_by(chatbot_id=chatbot_id).delete()
        current_time = datetime.now(timezone.utc)

        # Add new pairs
        for idx, qa_data in enumerate(qa_data_list):
            qa_pair = QAPair(
                chatbot_id=chatbot_id,
                question=qa_data['question'],
                answer=qa_data['answer'],
                tag=qa_data.get('tag', f'qa_{idx + 1}'),
                created_at=current_time,
                updated_at=current_time
            )
            db.session.add(qa_pair)

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error saving QA pairs: {e}")
        return False


def get_qa_pairs_from_db(chatbot_id):
    """Get all QA pairs for a chatbot"""
    qa_pairs = QAPair.query.filter_by(chatbot_id=chatbot_id).order_by(QAPair.created_at).all()
    return [qa.to_dict() for qa in qa_pairs]


def get_qa_pair_by_id(qa_id):
    """Get single QA pair by ID"""
    return QAPair.query.get(qa_id)


def update_single_qa_pair(qa_id, question=None, answer=None):
    """Update a single QA pair"""
    try:
        qa_pair = QAPair.query.get(qa_id)
        if qa_pair:
            if question is not None:
                qa_pair.question = question
            if answer is not None:
                qa_pair.answer = answer
            qa_pair.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        print(f"Error updating QA pair: {e}")
        return False


def delete_qa_pair(qa_id):
    """Delete a single QA pair"""
    try:
        qa_pair = QAPair.query.get(qa_id)
        if qa_pair:
            db.session.delete(qa_pair)
            db.session.commit()
            return True
        return False
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting QA pair: {e}")
        return False


def count_qa_pairs(chatbot_id):
    """Count QA pairs for a chatbot"""
    return QAPair.query.filter_by(chatbot_id=chatbot_id).count()


def append_qa_pairs_to_db(chatbot_id, qa_data_list):
    """
    Append new QA pairs with duplicate prevention

    Args:
        chatbot_id: Chatbot ID
        qa_data_list: List of dicts with 'question', 'answer', 'tag'

    Returns:
        bool: True if successful
    """
    try:
        from base import db
        from base.com.vo.qa_pair_vo import QAPair
        from datetime import datetime, timezone

        # Get existing pairs
        existing_pairs = QAPair.query.filter_by(chatbot_id=chatbot_id).all()

        existing_questions = set()
        max_tag_num = 0

        for pair in existing_pairs:
            existing_questions.add(pair.question.lower().strip())
            if pair.tag and pair.tag.startswith('qa_'):
                try:
                    num = int(pair.tag.split('_')[1])
                    max_tag_num = max(max_tag_num, num)
                except (ValueError, IndexError):
                    continue

        # Filter out duplicates
        unique_qa_data = []
        for qa_data in qa_data_list:
            question_normalized = qa_data['question'].lower().strip()
            if question_normalized not in existing_questions:
                unique_qa_data.append(qa_data)
                existing_questions.add(question_normalized)

        if not unique_qa_data:
            print(f"⚠️ All {len(qa_data_list)} Q&A pairs were duplicates")
            return True

        # Add new pairs
        current_time = datetime.now(timezone.utc)
        for qa_data in unique_qa_data:
            max_tag_num += 1
            qa_pair = QAPair(
                chatbot_id=chatbot_id,
                question=qa_data['question'],
                answer=qa_data['answer'],
                tag=qa_data.get('tag', f'qa_{max_tag_num}'),
                created_at=current_time,
                updated_at=current_time
            )
            db.session.add(qa_pair)

        db.session.commit()
        print(f"✅ Appended {len(unique_qa_data)} unique Q&A pairs")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error appending QA pairs: {e}")
        import traceback
        traceback.print_exc()
        return False