"""
Virtual Staging API Controllers - Image Upload Version
"""
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from typing import Tuple, Dict, Any
from models.virtual_staging import StagingParameters, StyleEnum, FurnitureThemeEnum
from service.virtual_staging_service import VirtualStagingService
from datetime import datetime
import uuid
import os
import base64
from pathlib import Path
from PIL import Image
from threading import Lock

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Lock to ensure only one image generation request at a time per session
_generation_locks: Dict[str, Lock] = {}
_generation_locks_lock = Lock()

# Note: All uploads are now handled via AWS S3 for deployment compatibility


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def upload_file_to_s3(file, session_id: str) -> str:
    """Upload file to S3 and return S3 URL"""
    if not file or not allowed_file(file.filename):
        return None
    
    try:
        from service.aws_service import AWSService
        
        # Read file content
        file_content = file.read()
        
        # Upload to S3
        result = AWSService.upload_bytes(
            image_bytes=file_content,
            filename=f"original_{session_id}.png",
            folder="staging",
            content_type="image/png"
        )
        
        if result.get("success"):
            return result.get("url")
        else:
            print(f"S3 upload failed: {result.get('error')}")
            return None
    except Exception as e:
        print(f"Error uploading to S3: {str(e)}")
        return None


def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 string"""
    with open(image_path, 'rb') as image_file:
        return base64.standard_b64encode(image_file.read()).decode('utf-8')


def get_image_mime_type(image_path: str) -> str:
    """Get MIME type from image file extension"""
    _, ext = os.path.splitext(image_path.lower())
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    return mime_types.get(ext, 'image/jpeg')




# Create blueprint
virtual_staging_bp = Blueprint('virtual_staging', __name__, url_prefix='/api/virtual-staging')

# Initialize service
vs_service = VirtualStagingService(gemini_model="gemini-2.0-flash")


def generate_session_id() -> str:
    """Generate a unique session ID"""
    return f"vs_{uuid.uuid4().hex[:12]}"


@virtual_staging_bp.route('/session', methods=['POST'])
def create_session() -> Tuple[Dict[str, Any], int]:
    """
    Create a new virtual staging session for a property
    
    Form data (multipart/form-data):
    {
        "property_id": str (required)
    }
    """
    try:
        # Get form data
        property_id = request.form.get('property_id', type=str)
        
        # Validate required fields
        if not property_id:
            return {'error': 'Missing required field: property_id'}, 400
        
        # Get property to access panoramic images
        from service.property_service import PropertyService
        property_service = PropertyService()
        property_obj = property_service.get_property(property_id)
        if not property_obj:
            return {'error': 'Property not found'}, 404
        
        # Get panoramic images
        panoramic_images = [img for img in property_obj.images if img.imageType == "panoramic"]
        if not panoramic_images:
            return {'error': 'No panoramic images found for this property'}, 400
        
        # Extract panoramic image URLs
        panoramic_image_urls = [img.url for img in panoramic_images]
        selected_image = panoramic_images[0]
        
        # Generate session_id
        session_id = generate_session_id()
        
        # Create staging parameters (use defaults for initial session)
        staging_params = StagingParameters(
            role=request.form.get('role', 'professional interior designer')
        )
        
        # Create session with all panoramic images
        staging = vs_service.create_staging_session_from_s3(
            session_id=session_id,
            property_id=property_id,
            original_image_url=selected_image.url,
            panoramic_images=panoramic_image_urls,
            staging_parameters=staging_params
        )
        
        if not staging:
            return {'error': 'Failed to create staging session'}, 500
        
        return {
            'message': 'Session created successfully',
            'session_id': session_id,
            'property_id': property_id,
            'panoramic_images_count': len(panoramic_images),
            'staging': staging.to_dict()
        }, 201
    
    except Exception as e:
        return {'error': f'Error creating session: {str(e)}'}, 500


@virtual_staging_bp.route('/generate', methods=['POST'])
def generate_staging() -> Tuple[Dict[str, Any], int]:
    """
    Generate virtual staging with Gemini using a panoramic image from the property
    
    Form data (multipart/form-data):
    {
        "session_id": str (required),
        "image_index": int (optional - index of panoramic image to use, defaults to session's original),
        "custom_prompt": str (required - prompt for Gemini to edit the image),
        "image_mask": file (optional - second image to specify specific area/point),
        "style": str (optional),
        "furniture_theme": str (optional),
        "color_scheme": str (optional),
        "specific_request": str (optional),
        "user_message": str (optional - user's request for chat history)
    }
    """
    # Get session_id first to acquire lock
    session_id = request.form.get('session_id', type=str)
    if not session_id:
        return {'error': 'Missing required field: session_id'}, 400
    
    # Acquire lock for this session - only one generation at a time
    
    
    try:
        # Get custom_prompt (required)
        custom_prompt = request.form.get('custom_prompt', type=str)
        if not custom_prompt or custom_prompt.strip() == '':
            return {'error': 'Missing required field: custom_prompt'}, 400
        
        # Get optional user message for chat history
        user_message = request.form.get('user_message', type=str)
        
        # Get image_index for selecting panoramic image (required)
        image_index = request.form.get('image_index', type=int)
        if image_index is None:
            return {'error': 'Missing required field: image_index'}, 400
        
        # Get the session to access property
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}, 404
        
        # Get property to access panoramic images
        from service.property_service import PropertyService
        property_service = PropertyService()
        property_obj = property_service.get_property(session.property_id)
        if not property_obj:
            return {'error': 'Property not found'}, 404
        
        # Get panoramic images
        panoramic_images = [img for img in property_obj.images if img.imageType == "panoramic"]
        if not panoramic_images:
            return {'error': 'No panoramic images found for this property'}, 400
        
        # Determine which image to use
        if image_index < 0 or image_index >= len(panoramic_images):
            return {'error': f'Invalid image_index. Available panoramic images: 0-{len(panoramic_images)-1}'}, 400
        selected_image = panoramic_images[image_index]
        
        # Get form data
        style = request.form.get('style', type=str)
        furniture_theme = request.form.get('furniture_theme', type=str)
        color_scheme = request.form.get('color_scheme', type=str)
        specific_request = request.form.get('specific_request', type=str)

        
        # Handle optional mask image for specific area/point
        mask_image_path = None
        
        # Create staging parameters with optional theme
        staging_params = StagingParameters(
            role=request.form.get('role', 'professional interior designer'),
            style=style,  # Can be None
            furniture_style=furniture_theme,  # Can be None
            color_scheme=color_scheme,  # Can be None
            specific_request=specific_request  # Can be None
        )
        
        # Generate staging with selected panoramic image
        response = vs_service.generate_staging(
            session_id=session_id,
            image_index=image_index,
            staging_parameters=staging_params,
            custom_prompt=custom_prompt,
            mask_image_url=mask_image_path,
            user_message=user_message
        )
        
        if not response:
            return {'error': 'Failed to generate staging'}, 500
    
        
        return {
            'message': 'Virtual staging generated successfully',
            'session_id': session_id,
            'new_panorama_url': response.image_url,
            'selected_image': {
                'url': selected_image.url,
                'filename': selected_image.filename,
                'index': image_index
            },
            'available_panoramic_images': len(panoramic_images),
            'staging_type': 'AI-Generated (gemini-2.5-flash-image)',
            'prompt_used': response.prompt_used
        }, 200
    
    except Exception as e:
        return {'error': f'Error generating staging: {str(e)}'}, 500



@virtual_staging_bp.route('/session/<session_id>', methods=['GET'])
def get_session(session_id: str) -> Tuple[Dict[str, Any], int]:
    """Get a staging session with all metadata in the response format"""
    try:
        response = vs_service.get_session_response(session_id)
        
        if not response:
            return {'error': 'Session not found'}, 404
        
        # Format datetime in GMT format
        def format_datetime(dt):
            if dt is None:
                return None
            if isinstance(dt, str):
                return dt
            return dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        session_data = response.model_dump(mode='json')
        # Ensure datetime fields are formatted correctly
        session_data['created_at'] = format_datetime(response.created_at)
        session_data['updated_at'] = format_datetime(response.updated_at)
        session_data['completed_at'] = format_datetime(response.completed_at)
        
        return {
            'message': 'Session retrieved successfully',
            'session': session_data
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving session: {str(e)}'}, 500


@virtual_staging_bp.route('/refine', methods=['POST'])
def refine_staging() -> Tuple[Dict[str, Any], int]:
    """
    Refine an existing staging with new parameters and uploaded image
    
    Form data (multipart/form-data):
    {
        "session_id": str,
        "image": file (uploaded image),
        "style": str,
        "furniture_theme": str,
        "color_scheme": str (optional),
        "specific_request": str (optional),
        "user_message": str (optional - user's refinement request for chat history)
    }
    """
    try:
        # Check if image file is present
        if 'image' not in request.files:
            return {'error': 'No image file provided'}, 400
        
        file = request.files['image']
        if file.filename == '':
            return {'error': 'No image file selected'}, 400
        
        # Validate and save image
        image_path = save_uploaded_file(file)
        if not image_path:
            return {'error': 'Invalid image format. Allowed: png, jpg, jpeg, gif, webp'}, 400
        
        # Get form data
        session_id = request.form.get('session_id', type=str)
        style = request.form.get('style', type=str)
        furniture_theme = request.form.get('furniture_theme', type=str)
        color_scheme = request.form.get('color_scheme', type=str)
        specific_request = request.form.get('specific_request', type=str)
        user_message = request.form.get('user_message', type=str)
        
        # Validate required fields
        if not session_id:
            return {'error': 'Missing required field: session_id'}, 400
        
        # Create new staging parameters with optional theme
        new_params = StagingParameters(
            role=request.form.get('role', 'professional interior designer'),
            style=style,  # Can be None
            furniture_style=furniture_theme,  # Can be None
            color_scheme=color_scheme,  # Can be None
            specific_request=specific_request  # Can be None
        )
        
        # Refine staging with optional user message for chat history
        response = vs_service.refine_staging(
            session_id=session_id,
            new_staging_parameters=new_params,
            user_message=user_message
        )
        
        if not response:
            return {'error': 'Failed to refine staging'}, 500
        
        return {
            'message': 'Staging refined successfully',
            'image_url': response.image_url,
            'image_path': image_path,
            'updated_at': response.updated_at.isoformat(),
            'prompt_used': response.prompt_used
        }, 200
    
    except Exception as e:
        return {'error': f'Error refining staging: {str(e)}'}, 500


@virtual_staging_bp.route('/property/<int:property_id>', methods=['GET'])
def get_property_sessions(property_id: str) -> Tuple[Dict[str, Any], int]:
    """Get all sessions for a property"""
    try:
        sessions = vs_service.get_sessions_by_property(property_id)
        
        return {
            'message': 'Sessions retrieved successfully',
            'property_id': property_id,
            'sessions': [
                {
                    'session_id': session_id,
                    'data': session.to_dict()
                }
                for session_id, session in sessions
            ]
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving sessions: {str(e)}'}, 500


@virtual_staging_bp.route('/user/<int:user_id>', methods=['GET'])
def get_user_sessions(user_id: int) -> Tuple[Dict[str, Any], int]:
    """Get all sessions for a user"""
    try:
        sessions = vs_service.get_sessions_by_user(user_id)
        
        return {
            'message': 'Sessions retrieved successfully',
            'user_id': user_id,
            'sessions': [
                {
                    'session_id': session_id,
                    'data': session.to_dict()
                }
                for session_id, session in sessions
            ]
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving sessions: {str(e)}'}, 500


@virtual_staging_bp.route('/session/<session_id>', methods=['DELETE'])
def delete_session(session_id: str) -> Tuple[Dict[str, Any], int]:
    """Delete a staging session"""
    try:
        success = vs_service.delete_session(session_id)
        
        if not success:
            return {'error': 'Failed to delete session'}, 500
        
        return {'message': f'Session {session_id} deleted successfully'}, 200
    
    except Exception as e:
        return {'error': f'Error deleting session: {str(e)}'}, 500


@virtual_staging_bp.route('/styles', methods=['GET'])
def get_available_styles() -> Tuple[Dict[str, Any], int]:
    """Get available style options"""
    styles = [style.value for style in StyleEnum]
    return {
        'message': 'Available styles retrieved successfully',
        'styles': styles
    }, 200


@virtual_staging_bp.route('/furniture-themes', methods=['GET'])
def get_available_furniture_themes() -> Tuple[Dict[str, Any], int]:
    """Get available furniture theme options"""
    themes = [theme.value for theme in FurnitureThemeEnum]
    return {
        'message': 'Available furniture themes retrieved successfully',
        'furniture_themes': themes
    }, 200


@virtual_staging_bp.route('/color-palettes', methods=['GET'])
def get_color_palettes() -> Tuple[Dict[str, Any], int]:
    """Get available color palette options"""
    from config.prompt_config import COLOR_PALETTES
    
    palettes = {
        hex_color: {
            'name': info['name'],
            'description': info['description'],
            'complement': info['complement']
        }
        for hex_color, info in COLOR_PALETTES.items()
    }
    
    return {
        'message': 'Color palettes retrieved successfully',
        'color_palettes': palettes
    }, 200


# ==================== SAVE OPERATIONS ====================
@virtual_staging_bp.route('/save-change', methods=['POST'])
def save_change() -> Tuple[Dict[str, Any], int]:
    """
    Save the current working image to persist changes
    
    JSON body:
    {
        "session_id": str
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return {'error': 'No JSON data provided'}, 400
        
        session_id = data.get('session_id')
        if not session_id:
            return {'error': 'Missing required field: session_id'}, 400
        
        response = vs_service.save_change(session_id)
        
        if not response or not response.success:
            return {'error': response.message if response else 'Failed to save change'}, 500
        
        return {
            'message': response.message,
            'image_url': response.image_url,
            'saved_at': response.saved_at.isoformat()
        }, 200
    
    except Exception as e:
        return {'error': f'Error saving change: {str(e)}'}, 500


@virtual_staging_bp.route('/session/<session_id>/save-change', methods=['POST'])
def save_session_change(session_id: str) -> Tuple[Dict[str, Any], int]:
    """
    Save the current working image and persist to AWS
    
    This is the RESTful endpoint that uses session_id from the URL path.
    It will:
    1. Persist the current working image to AWS S3
    2. Update the session in Firestore
    3. Return the saved image information
    
    URL path:
    /api/virtual-staging/session/<session_id>/save-change
    """
    try:
        # Validate session exists
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': f'Session {session_id} not found'}, 404
        
        # Check if there's a current working image to save
        if not session.current_image_url:
            return {'error': 'No current working image to save for this session'}, 400
        
        # Save the change (persists to AWS and creates new version)
        response = vs_service.save_change(session_id)
        
        if not response or not response.success:
            return {'error': response.message if response else 'Failed to save change'}, 500

        return {
            'message': response.message,
            'session_id': session_id,
            'image_url': response.image_url,
            'saved_at': response.saved_at.strftime('%a, %d %b %Y %H:%M:%S GMT')
        }, 200
    
    except Exception as e:
        return {'error': f'Error saving session change: {str(e)}'}, 500


@virtual_staging_bp.route('/session/<session_id>/save-change-with-session', methods=['POST'])
def save_session_change_with_session(session_id: str) -> Tuple[Dict[str, Any], int]:
    """
    Save the current working image and return complete session response
    
    Same as /save-change but returns the full session data in the response format:
    {
        "message": "Changes saved successfully",
        "session": { ... full session data ... }
    }
    
    URL path:
    /api/virtual-staging/session/<session_id>/save-change-with-session
    """
    try:
        # Validate session exists
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': f'Session {session_id} not found'}, 404
        
        # Check if there's a current working image to save
        if not session.current_image_url:
            return {'error': 'No current working image to save for this session'}, 400
        
        # Save the change (persists to AWS and creates new version)
        save_response = vs_service.save_change(session_id)
        
        if not save_response or not save_response.success:
            return {'error': save_response.message if save_response else 'Failed to save change'}, 500

        # Get the full session response after saving
        session_response = vs_service.get_session_response(session_id)
        
        if not session_response:
            return {'error': 'Failed to retrieve session after save'}, 500

        return {
            'message': save_response.message,
            'session': session_response.model_dump(mode='json')
        }, 200
    
    except Exception as e:
        return {'error': f'Error saving session change: {str(e)}'}, 500


@virtual_staging_bp.route('/revert-change', methods=['POST'])
def revert_change() -> Tuple[Dict[str, Any], int]:
    """
    Revert to a previous saved version - NOT SUPPORTED
    
    Versioning has been removed. This endpoint returns an error.
    """
    return {'error': 'Versioning is not supported. Revert functionality is disabled.'}, 400


@virtual_staging_bp.route('/version-history/<session_id>', methods=['GET'])
def get_version_history(session_id: str) -> Tuple[Dict[str, Any], int]:
    """Get version history for a session - returns empty since versioning is disabled"""
    try:
        # Check if session exists
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}, 404
        
        return {
            'message': 'Versioning is disabled - no version history available',
            'session_id': session_id,
            'total_versions': 0,
            'current_version': 1,
            'has_unsaved_changes': False,
            'versions': []
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving version history: {str(e)}'}, 500

@virtual_staging_bp.route('/chat-history/<session_id>', methods=['GET'])
def get_chat_history(session_id: str) -> Tuple[Dict[str, Any], int]:
    """
    Get the persistent chat history for a staging session
    
    Query parameters:
    - include_full_history (bool, optional): Include full conversation or just recent messages. Default: false
    - last_n_messages (int, optional): Number of recent messages to include. Default: 10
    """
    try:
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}, 404
        
        if not session.chat_history_id:
            return {'error': 'No chat history found for this session'}, 404
        
        # Get query parameters
        include_full = request.args.get('include_full_history', type=bool, default=False)
        last_n = request.args.get('last_n_messages', type=int, default=10)
        
        # Get chat history
        chat_history = vs_service.chat_history_service.get_history(session.chat_history_id)
        if not chat_history:
            return {'error': 'Chat history not found'}, 404
        
        # Get conversation summary
        summary = vs_service.chat_history_service.get_conversation_summary(session.chat_history_id)
        
        return {
            'message': 'Chat history retrieved successfully',
            'session_id': session_id,
            'chat_history_id': session.chat_history_id,
            'summary': summary,
            'context': vs_service.chat_history_service.get_llm_context(
                session.chat_history_id,
                include_full_history=include_full,
                last_n_messages=last_n
            )
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving chat history: {str(e)}'}, 500

@virtual_staging_bp.route('/chat-history/<session_id>/messages', methods=['GET'])
def get_chat_messages(session_id: str) -> Tuple[Dict[str, Any], int]:
    """
    Get all messages from the chat history of a session
    
    Query parameters:
    - role (str, optional): Filter by message role ('user', 'assistant'). Default: all
    """
    try:
        session = vs_service.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}, 404
        
        if not session.chat_history_id:
            return {'error': 'No chat history found for this session'}, 404
        
        # Get chat history
        chat_history = vs_service.chat_history_service.get_history(session.chat_history_id)
        if not chat_history:
            return {'error': 'Chat history not found'}, 404
        
        # Get optional role filter
        role_filter = request.args.get('role', type=str, default=None)
        
        # Filter messages if role is specified
        messages = chat_history.messages
        if role_filter:
            messages = [m for m in messages if m.role.value == role_filter]
        
        return {
            'message': 'Chat messages retrieved successfully',
            'session_id': session_id,
            'total_messages': len(messages),
            'messages': [
                {
                    'message_id': m.message_id,
                    'role': m.role.value,
                    'content': m.content,
                    'refinement_iteration': m.refinement_iteration,
                    'staging_parameters_used': m.staging_parameters_used,
                    'created_at': m.created_at.isoformat(),
                    'metadata': m.metadata
                }
                for m in messages
            ]
        }, 200
    
    except Exception as e:
        return {'error': f'Error retrieving chat messages: {str(e)}'}, 500


@virtual_staging_bp.route('/furniture/find', methods=['POST'])
def find_furniture():
    """Find a furniture item that matches the user's prompt"""
    try:
        data = request.get_json()
        
        if not data or 'prompt' not in data:
            return {'error': 'Missing required field: prompt'}, 400
        
        prompt = data.get('prompt', '').strip()
        if not prompt:
            return {'error': 'Prompt cannot be empty'}, 400
        
        # Find furniture using Gemini
        furniture = vs_service.gemini_service.find_furniture_by_prompt(prompt)
        
        if not furniture:
            return {
                'success': False,
                'message': 'No matching furniture found',
                'furniture': None
            }, 404
        
        return {
            'success': True,
            'message': 'Furniture found successfully',
            'furniture': furniture
        }, 200
    
    except Exception as e:
        return {'error': f'Error finding furniture: {str(e)}'}, 500


@virtual_staging_bp.route('/furniture/inventory', methods=['GET'])
def get_furniture_inventory():
    """Get the complete furniture inventory"""
    try:
        inventory = vs_service.gemini_service.get_furniture_inventory()
        
        return {
            'success': True,
            'message': 'Furniture inventory retrieved successfully',
            'total_items': len(inventory),
            'inventory': inventory
        }, 200
    
    except Exception as e:
        return {'error': f'Error getting furniture inventory: {str(e)}'}, 500


@virtual_staging_bp.route('/extract-furniture/<session_id>/<int:image_index>', methods=['POST'])
def extract_furniture(session_id: str, image_index: int):
    """
    Extract furniture from an image and provide shopping recommendations.
    
    Request body (JSON):
    {
        "budget": "optional string (e.g., '$2,000')",
        "furniture_items": "optional list of specific furniture types to search for"
    }
    
    Returns:
    {
        "success": true,
        "total_budget_limit": "string",
        "furniture_items": [
            {
                "item_type": "string",
                "top_3_suggestions": [
                    {
                        "product_name": "string",
                        "retailer": "string",
                        "price": "string",
                        "link": "string",
                        "why_it_is_a_pick": "string"
                    }
                ]
            }
        ]
    }
    """
    try:
        # Get request data
        data = request.get_json() or {}
        budget = data.get('budget')
        furniture_items = data.get('furniture_items')
        
        print(f"[API] 🔍 Extracting furniture from session {session_id}, image index {image_index}")
        print(f"[API] Budget: {budget}, Specific items: {furniture_items}")
        
        # Call the furniture extraction service
        result = vs_service.gemini_service.extract_furniture_from_the_image(
            session_id=session_id,
            image_index=image_index,
            budget=budget,
            furniture_items=furniture_items
        )
        
        if result and 'error' not in result:
            return {
                'success': True,
                'message': f'Successfully extracted furniture from image {image_index}',
                **result  # Unpack total_budget_limit and furniture_items
            }, 200
        else:
            return {
                'success': False,
                'error': result.get('error', 'Unknown error during furniture extraction'),
                'total_budget_limit': budget or 'Not specified',
                'furniture_items': []
            }, 400
    
    except Exception as e:
        print(f"[API] ❌ Error in extract_furniture endpoint: {str(e)}")
        return {
            'success': False,
            'error': f'Error extracting furniture: {str(e)}'
        }, 500