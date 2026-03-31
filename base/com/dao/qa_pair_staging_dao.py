"""
QA Pairs Staging DAO
Handles all database operations for qa_pairs_staging table
"""
from base import db
from base.com.vo.qa_pairs_staging_vo import QAPairStaging
from base.com.vo.qa_pair_vo import QAPair
from datetime import datetime, timezone


class QAPairStagingDAO:

    # ──────────────────────────────────────────
    # CREATE
    # ──────────────────────────────────────────

    @staticmethod
    def create(chatbot_id, question, answer, added_by, tag=None):
        """Add a new Q&A pair to staging"""
        staging = QAPairStaging(
            chatbot_id=chatbot_id,
            question=question,
            answer=answer,
            tag=tag,
            added_by=added_by,
            status='pending'
        )
        db.session.add(staging)
        db.session.commit()
        return staging

    # ──────────────────────────────────────────
    # READ
    # ──────────────────────────────────────────

    @staticmethod
    def get_by_id(staging_id):
        """Get a single staging pair by ID"""
        return QAPairStaging.query.get(staging_id)

    @staticmethod
    def get_all_by_chatbot(chatbot_id):
        """Get all staging pairs for a chatbot"""
        return QAPairStaging.query.filter_by(chatbot_id=chatbot_id).order_by(
            QAPairStaging.created_at.desc()
        ).all()

    @staticmethod
    def get_by_status(chatbot_id, status):
        """Get staging pairs by status (pending / approved / rejected)"""
        return QAPairStaging.query.filter_by(
            chatbot_id=chatbot_id,
            status=status
        ).order_by(QAPairStaging.created_at.desc()).all()

    @staticmethod
    def get_pending(chatbot_id):
        """Get all pending staging pairs for a chatbot"""
        return QAPairStagingDAO.get_by_status(chatbot_id, 'pending')

    # ──────────────────────────────────────────
    # UPDATE
    # ──────────────────────────────────────────

    @staticmethod
    def mark_tested(staging_id):
        """Mark a staging pair as previewed/tested"""
        staging = QAPairStagingDAO.get_by_id(staging_id)
        if not staging:
            return None
        staging.mark_tested()
        db.session.commit()
        return staging

    @staticmethod
    def approve(staging_id):
        """Approve a staging pair"""
        staging = QAPairStagingDAO.get_by_id(staging_id)
        if not staging:
            return None, "Staging pair not found"
        if staging.status != 'pending':
            return None, f"Cannot approve a pair with status '{staging.status}'"
        staging.approve()
        db.session.commit()
        return staging, None

    @staticmethod
    def reject(staging_id, note=None):
        """Reject a staging pair with optional note"""
        staging = QAPairStagingDAO.get_by_id(staging_id)
        if not staging:
            return None, "Staging pair not found"
        if staging.status != 'pending':
            return None, f"Cannot reject a pair with status '{staging.status}'"
        staging.reject(note=note)
        db.session.commit()
        return staging, None

    # ──────────────────────────────────────────
    # MERGE
    # ──────────────────────────────────────────

    @staticmethod
    def merge_to_production(staging_id):
        """
        Merge approved staging pair into qa_pairs (production).
        Returns the new QAPair if successful.
        """
        staging = QAPairStagingDAO.get_by_id(staging_id)
        if not staging:
            return None, "Staging pair not found"
        if staging.status != 'approved':
            return None, "Only approved pairs can be merged"
        if staging.merged_at is not None:
            return None, "This pair has already been merged"

        # Copy to production qa_pairs
        new_pair = staging.to_qa_pair()
        db.session.add(new_pair)

        # Mark staging as merged
        staging.mark_merged()
        db.session.commit()

        return new_pair, None

    # ──────────────────────────────────────────
    # DELETE
    # ──────────────────────────────────────────

    @staticmethod
    def delete(staging_id):
        """Delete a staging pair (only if pending or rejected)"""
        staging = QAPairStagingDAO.get_by_id(staging_id)
        if not staging:
            return False, "Staging pair not found"
        if staging.status == 'approved' and staging.merged_at:
            return False, "Cannot delete an already merged pair"
        db.session.delete(staging)
        db.session.commit()
        return True, None