"""
File Service
Handles file system operations for users and chatbots
"""
import os
from flask import current_app


def get_user_folder(user_id):
    """
    Get user data folder path

    Args:
        user_id: User ID

    Returns:
        str: Path to user folder (data/users/user_{user_id})
    """
    return os.path.join(
        current_app.config['USER_DATA_FOLDER'],
        f'user_{user_id}'
    )


def get_chatbot_folder(user_id, chatbot_id):
    """
    Get chatbot folder path

    Args:
        user_id: User ID
        chatbot_id: Chatbot ID

    Returns:
        str: Path to chatbot folder (data/users/user_{user_id}/chatbots/chatbot_{chatbot_id})
    """
    return os.path.join(
        get_user_folder(user_id),
        'chatbots',
        f'chatbot_{chatbot_id}'
    )


def get_avatar_path(user_id, chatbot_id, filename):
    """
    Get avatar file path inside chatbot folder

    Args:
        user_id: User ID
        chatbot_id: Chatbot ID
        filename: Avatar filename

    Returns:
        str: Full path to avatar file
    """
    return os.path.join(
        get_chatbot_folder(user_id, chatbot_id),
        filename
    )


def ensure_user_folder(user_id):
    """
    Ensure user folder exists, create if not

    Args:
        user_id: User ID

    Returns:
        str: Path to user folder
    """
    user_folder = get_user_folder(user_id)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder


def ensure_chatbot_folder(user_id, chatbot_id):
    """
    Ensure chatbot folder exists, create if not

    Args:
        user_id: User ID
        chatbot_id: Chatbot ID

    Returns:
        str: Path to chatbot folder
    """
    chatbot_folder = get_chatbot_folder(user_id, chatbot_id)
    os.makedirs(chatbot_folder, exist_ok=True)
    return chatbot_folder


def create_directory_structure(app):
    """
    Create all necessary directory structure with proper permissions

    Args:
        app: Flask application instance
    """
    BASE_DATA_FOLDER = app.config.get('BASE_DATA_FOLDER', 'data')

    directories = [
        app.config['USER_DATA_FOLDER'],
        app.config['UPLOAD_FOLDER'],
        app.config.get('AVATARS_FOLDER'),
        os.path.join(BASE_DATA_FOLDER, 'temp'),
        os.path.join(BASE_DATA_FOLDER, 'backups')
    ]

    # Add log directory if configured
    log_file = os.getenv('LOG_FILE')
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            directories.append(log_dir)

    for directory in directories:
        if directory:  # Skip None values
            try:
                os.makedirs(directory, mode=0o755, exist_ok=True)
                if app.config.get('DEBUG'):
                    print(f"✓ Directory ready: {directory}")
            except Exception as e:
                print(f"✗ Failed to create {directory}: {e}")
                raise


def allowed_file(filename, allowed_extensions=None):
    """
    Check if file extension is allowed

    Args:
        filename: Filename to check
        allowed_extensions: Set of allowed extensions (default: png,jpg,jpeg,gif,svg)

    Returns:
        bool: True if allowed, False otherwise
    """
    if allowed_extensions is None:
        # Default allowed extensions
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg'}

    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions