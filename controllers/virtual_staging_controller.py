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

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create upload folder if it doesn't exist
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file) -> str:
    """Save uploaded file and return file path"""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to make filename unique
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        return filepath
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
    Create a new virtual staging session with image upload
    
    Form data (multipart/form-data):
    {
        "property_id": int,
        "user_id": int,
        "room_name": str,
        "image": file (uploaded image),
        "style": str (StyleEnum),
        "furniture_theme": str (FurnitureThemeEnum),
        "color_scheme": str (hex color, optional),
        "specific_request": str (optional)
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
        property_id = request.form.get('property_id', type=int)
        user_id = request.form.get('user_id', type=int)
        room_name = request.form.get('room_name', type=str)
        style = request.form.get('style', type=str)
        furniture_theme = request.form.get('furniture_theme', type=str)
        color_scheme = request.form.get('color_scheme', type=str)
        specific_request = request.form.get('specific_request', type=str)
        
        # Validate required fields
        if not all([property_id, user_id, room_name, style, furniture_theme]):
            return {'error': 'Missing required fields: property_id, user_id, room_name, style, furniture_theme'}, 400
        
        # Validate enums
        try:
            style_enum = StyleEnum(style)
            furniture_enum = FurnitureThemeEnum(furniture_theme)
        except ValueError as e:
            return {'error': f'Invalid enum value: {str(e)}'}, 400
        
        # Create staging parameters
        staging_params = StagingParameters(
            role=request.form.get('role', 'professional interior designer'),
            style=style_enum,
            furniture_theme=furniture_enum,
            color_scheme=color_scheme,
            specific_request=specific_request
        )
        
        # Generate session
        session_id = generate_session_id()
        staging = vs_service.create_staging_session(
            session_id=session_id,
            property_id=property_id,
            user_id=user_id,
            room_name=room_name,
            original_image_key=image_path,
            staging_parameters=staging_params
        )
        
        if not staging:
            return {'error': 'Failed to create staging session'}, 500
        
        return {
            'message': 'Session created successfully',
            'session_id': session_id,
            'image_path': image_path,
            'staging': staging.to_dict()
        }, 201
    
    except Exception as e:
        return {'error': f'Error creating session: {str(e)}'}, 500


@virtual_staging_bp.route('/generate', methods=['POST'])
def generate_staging() -> Tuple[Dict[str, Any], int]:
    """
    Generate virtual staging with Gemini using uploaded image
    
    Form data (multipart/form-data):
    {
        "session_id": str,
        "image": file (uploaded image - required),
        "custom_prompt": str (required - prompt for Gemini to edit the image),
        "image_mask": file (optional - second image to specify specific area/point),
        "style": str (optional),
        "furniture_theme": str (optional),
        "color_scheme": str (optional),
        "specific_request": str (optional)
    }
    """
    try:
        # Check if image file is present
        if 'image' not in request.files:
            return {'error': 'No image file provided'}, 400
        
        file = request.files['image']
        if file.filename == '':
            return {'error': 'No image file selected'}, 400
        
        # Validate and save main image
        image_path = save_uploaded_file(file)
        if not image_path:
            return {'error': 'Invalid image format. Allowed: png, jpg, jpeg, gif, webp'}, 400
        
        # Get custom_prompt (required)
        custom_prompt = request.form.get('custom_prompt', type=str)
        if not custom_prompt or custom_prompt.strip() == '':
            return {'error': 'Missing required field: custom_prompt'}, 400
        
        # Handle optional mask image for specific area/point
        mask_image_path = None
        if 'image_mask' in request.files:
            mask_file = request.files['image_mask']
            if mask_file and mask_file.filename != '':
                mask_image_path = save_uploaded_file(mask_file)
                if not mask_image_path:
                    return {'error': 'Invalid mask image format. Allowed: png, jpg, jpeg, gif, webp'}, 400
        
        # Get form data
        session_id = request.form.get('session_id', type=str)
        style = request.form.get('style', type=str)
        furniture_theme = request.form.get('furniture_theme', type=str)
        color_scheme = request.form.get('color_scheme', type=str)
        specific_request = request.form.get('specific_request', type=str)
        
        # Validate required fields
        if not session_id:
            return {'error': 'Missing required field: session_id'}, 400
        
        # Validate enums if provided
        style_enum = None
        furniture_enum = None
        if style:
            try:
                style_enum = StyleEnum(style)
            except ValueError as e:
                return {'error': f'Invalid style enum value: {str(e)}'}, 400
        
        if furniture_theme:
            try:
                furniture_enum = FurnitureThemeEnum(furniture_theme)
            except ValueError as e:
                return {'error': f'Invalid furniture_theme enum value: {str(e)}'}, 400
        
        # Create staging parameters
        staging_params = None
        if style_enum and furniture_enum:
            staging_params = StagingParameters(
                role=request.form.get('role', 'professional interior designer'),
                style=style_enum,
                furniture_theme=furniture_enum,
                color_scheme=color_scheme,
                specific_request=specific_request
            )
        
        # Generate staging with custom prompt
        response = vs_service.generate_staging(
            session_id=session_id,
            original_image_url=image_path,
            staging_parameters=staging_params,
            custom_prompt=custom_prompt,
            mask_image_url=mask_image_path
        )
        
        if not response:
            return {'error': 'Failed to generate staging'}, 500
        
        # Get the generated image path from response
        generated_image_path = response.image_url
        
        if generated_image_path and os.path.exists(generated_image_path):
            # Read generated image from disk and convert to base64
            with open(generated_image_path, 'rb') as f:
                image_bytes = f.read()
            image_base64 = base64.standard_b64encode(image_bytes).decode('utf-8')
            image_data_url = f"data:image/png;base64,{image_base64}"
        else:
            # Fallback to original image if generation failed
            pil_image = Image.open(image_path)
            from io import BytesIO
            img_buffer = BytesIO()
            pil_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            image_base64 = base64.standard_b64encode(img_buffer.getvalue()).decode('utf-8')
            image_data_url = f"data:image/png;base64,{image_base64}"
        
        return {
            'message': 'Virtual staging generated successfully',
            'session_id': session_id,
            'staging_type': 'AI-Generated (gemini-2.5-flash-image)',
            'custom_prompt_used': custom_prompt,
            'prompt_used': response.prompt_used
        }, 200
    
    except Exception as e:
        return {'error': f'Error generating staging: {str(e)}'}, 500


@virtual_staging_bp.route('/session/<session_id>', methods=['GET'])
def get_session(session_id: str) -> Tuple[Dict[str, Any], int]:
    """Get a staging session with all metadata"""
    try:
        response = vs_service.get_session_response(session_id)
        
        if not response:
            return {'error': 'Session not found'}, 404
        
        return {
            'message': 'Session retrieved successfully',
            'session': response.model_dump()
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
        "specific_request": str (optional)
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
        
        # Validate required fields
        if not all([session_id, style, furniture_theme]):
            return {'error': 'Missing required fields: session_id, style, furniture_theme'}, 400
        
        # Validate enums
        try:
            style_enum = StyleEnum(style)
            furniture_enum = FurnitureThemeEnum(furniture_theme)
        except ValueError as e:
            return {'error': f'Invalid enum value: {str(e)}'}, 400
        
        # Create new staging parameters
        new_params = StagingParameters(
            role=request.form.get('role', 'professional interior designer'),
            style=style_enum,
            furniture_theme=furniture_enum,
            color_scheme=color_scheme,
            specific_request=specific_request
        )
        
        # Refine staging
        response = vs_service.refine_staging(
            session_id=session_id,
            original_image_url=image_path,
            new_staging_parameters=new_params
        )
        
        if not response:
            return {'error': 'Failed to refine staging'}, 500
        
        return {
            'message': 'Staging refined successfully',
            'image_url': response.image_url,
            'image_path': image_path,
            'version': response.version,
            'updated_at': response.updated_at.isoformat(),
            'prompt_used': response.prompt_used
        }, 200
    
    except Exception as e:
        return {'error': f'Error refining staging: {str(e)}'}, 500


@virtual_staging_bp.route('/property/<int:property_id>', methods=['GET'])
def get_property_sessions(property_id: int) -> Tuple[Dict[str, Any], int]:
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
