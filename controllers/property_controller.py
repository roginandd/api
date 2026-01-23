"""Property controller for handling property-related API endpoints"""
from flask import Blueprint, request, jsonify
from typing import Dict, Any
from service.property_service import PropertyService, ValidationError
from service.inquiry_service import InquiryService
from models.property import PropertyImage
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

property_bp = Blueprint('property', __name__, url_prefix='/api/properties')
property_service = PropertyService()
inquiry_service = InquiryService()


@property_bp.route('', methods=['POST'])
def create_property():
    """Create a new property"""
    try:
        # Get form data
        data = request.form.to_dict()

        # Get uploaded files
        files = {}
        if 'regularImages' in request.files:
            files['regularImages'] = request.files.getlist('regularImages')
        if 'panoramicImages' in request.files:
            files['panoramicImages'] = request.files.getlist('panoramicImages')
        if 'image' in request.files:
            files['image'] = request.files.getlist('image')

        # TODO: Get user_id from authentication
        # For now, use a placeholder
        user_id = data.get('user_id', 'user_123456')

        # Create property
        property_id, property_obj, images = property_service.create_property(data, user_id, files)

        response = {
            'success': True,
            'property': {
                'id': property_id,
                'name': property_obj.name,
                'status': property_obj.status,
                'created_at': property_obj.createdAt.isoformat(),
                'images': [
                    {
                        'id': img.id,
                        'url': img.url,
                        'type': img.imageType
                    } for img in images
                ]
            }
        }

        logger.info(f"Property created successfully: {property_obj.name}")
        return jsonify(response), 201

    except ValidationError as e:
        logger.warning(f"Validation error: {e.message}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': e.message,
                'details': {
                    'field': e.field,
                    'message': e.message
                }
            }
        }), 400
    except Exception as e:
        logger.error(f"Error creating property: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to create property'
            }
        }), 500


@property_bp.route('/<property_id>', methods=['GET'])
def get_property(property_id: str):
    """Get property by ID"""
    try:
        property_obj = property_service.get_property(property_id)
        if not property_obj:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'PROPERTY_NOT_FOUND',
                    'message': 'Property not found'
                }
            }), 404

        return jsonify({
            'success': True,
            'property': property_obj.model_dump()
        }), 200

    except Exception as e:
        logger.error(f"Error getting property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get property'
            }
        }), 500


@property_bp.route('/seller/properties-view', methods=['GET'])
def get_properties_in_seller_side():
    """Get properties for seller dashboard with views and inquiries count"""
    try:
        # TODO: Get user_id from authentication
        # For now, use a placeholder
        user_id = request.args.get('user_id', 'user_123456')

        # Get all properties for the seller
        properties = property_service.get_properties_by_user(user_id)

        properties_list = []
        for prop_id, prop in properties:
            # Get view count for this property
            view_count = inquiry_service.get_property_view_count(prop_id)
            
            # Get inquiry count for this property
            inquiry_count = inquiry_service.get_inquiry_count_for_property(prop_id)
            
            # Build seller-side property response
            property_data = {
                'id': prop_id,
                'propertyId': prop_id,
                'name': prop.name,
                'address': prop.address,
                'image': prop.image.url if prop.image else None,
                'status': prop.status,
                'views': view_count,
                'inquiries': inquiry_count,
                'price': prop.price,
                'bedrooms': prop.bedrooms,
                'bathrooms': prop.bathrooms,
                'createdAt': prop.createdAt.isoformat(),
            }
            properties_list.append(property_data)

        return jsonify({
            'success': True,
            'properties': properties_list,
            'total': len(properties_list)
        }), 200

    except Exception as e:
        logger.error(f"Error getting seller properties: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get seller properties'
            }
        }), 500


@property_bp.route('', methods=['GET'])
def get_properties():
    """Get all properties or properties for a user"""
    try:
        user_id = request.args.get('user_id')
        if user_id:
            properties = property_service.get_properties_by_user(user_id)
        else:
            properties = property_service.get_all_properties()

        properties_list = []
        for prop_id, prop in properties:
            prop_dict = prop.model_dump()
            prop_dict['id'] = prop_id
            properties_list.append(prop_dict)

        return jsonify({
            'success': True,
            'properties': properties_list
        }), 200

    except Exception as e:
        logger.error(f"Error getting properties: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get properties'
            }
        }), 500


@property_bp.route('/<property_id>', methods=['PUT'])
def update_property(property_id: str):
    """Update an existing property"""
    try:
        # Get form data (for file uploads) or JSON data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form.to_dict()
            # Get uploaded files
            files = {}
            if 'regularImages' in request.files:
                files['regularImages'] = request.files.getlist('regularImages')
            if 'panoramicImages' in request.files:
                files['panoramicImages'] = request.files.getlist('panoramicImages')
            if 'image' in request.files:
                files['image'] = request.files.getlist('image')
        else:
            data = request.get_json()
            files = None

        if not data:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'No data provided'
                }
            }), 400

        # TODO: Get user_id from authentication
        user_id = data.get('user_id', 'user_123456')

        updated_property = property_service.update_property(property_id, data, user_id, files)

        return jsonify({
            'success': True,
            'property': updated_property.model_dump()
        }), 200

    except ValidationError as e:
        logger.warning(f"Validation error updating property {property_id}: {e.message}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': e.message,
                'details': {
                    'field': e.field,
                    'message': e.message
                }
            }
        }), 400
    except Exception as e:
        logger.error(f"Error updating property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to update property'
            }
        }), 500


@property_bp.route('/<property_id>', methods=['PATCH'])
def patch_property(property_id: str):
    """Partially update an existing property"""
    try:
        # Get form data (for file uploads) or JSON data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form.to_dict()
            # Get uploaded files
            files = {}
            if 'regularImages' in request.files:
                files['regularImages'] = request.files.getlist('regularImages')
            if 'panoramicImages' in request.files:
                files['panoramicImages'] = request.files.getlist('panoramicImages')
            if 'image' in request.files:
                files['image'] = request.files.getlist('image')
        else:
            data = request.get_json()
            files = None

        if not data and not files:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'No data or files provided'
                }
            }), 400

        # TODO: Get user_id from authentication
        user_id = data.get('user_id', 'user_123456') if data else 'user_123456'

        updated_property = property_service.update_property(property_id, data or {}, user_id, files)

        return jsonify({
            'success': True,
            'property': updated_property.model_dump()
        }), 200

    except ValidationError as e:
        logger.warning(f"Validation error patching property {property_id}: {e.message}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': e.message,
                'details': {
                    'field': e.field,
                    'message': e.message
                }
            }
        }), 400
    except Exception as e:
        logger.error(f"Error patching property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to patch property'
            }
        }), 500


@property_bp.route('/<property_id>', methods=['DELETE'])
def delete_property(property_id: str):
    """Delete a property"""
    try:
        # TODO: Get user_id from authentication
        user_id = request.args.get('user_id', 'user_123456')

        success = property_service.delete_property(property_id, user_id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Property deleted successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'DELETE_FAILED',
                    'message': 'Failed to delete property'
                }
            }), 500

    except ValidationError as e:
        logger.warning(f"Validation error deleting property {property_id}: {e.message}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': e.message
            }
        }), 400
    except Exception as e:
        logger.error(f"Error deleting property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to delete property'
            }
        }), 500


@property_bp.route('/property-types', methods=['GET'])
def get_property_types():
    """Get available property and listing types"""
    try:
        types_data = property_service.get_property_types()
        return jsonify({
            'success': True,
            **types_data
        }), 200

    except Exception as e:
        logger.error(f"Error getting property types: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get property types'
            }
        }), 500


@property_bp.route('/amenities', methods=['GET'])
def get_amenities_options():
    """Get available amenities options"""
    try:
        amenities_data = property_service.get_amenities_options()
        return jsonify({
            'success': True,
            **amenities_data
        }), 200

    except Exception as e:
        logger.error(f"Error getting amenities options: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get amenities options'
            }
        }), 500


@property_bp.route('/<property_id>/images', methods=['POST'])
def upload_property_images(property_id: str):
    """Upload additional images for a property"""
    try:
        # Check if property exists
        property_obj = property_service.get_property(property_id)
        if not property_obj:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'PROPERTY_NOT_FOUND',
                    'message': 'Property not found'
                }
            }), 404

        # Get uploaded files
        files = {}
        if 'regularImages' in request.files:
            files['regularImages'] = request.files.getlist('regularImages')
        if 'panoramicImages' in request.files:
            files['panoramicImages'] = request.files.getlist('panoramicImages')
        if 'image' in request.files:
            files['image'] = request.files.getlist('image')

        if not files:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'No images provided'
                }
            }), 400

        # Upload images
        images = property_service._handle_image_uploads(files, property_id)

        # Handle main image update if provided
        if 'image' in files and files['image']:
            main_image_result = property_service.aws_service.upload_property_image(files['image'][0], property_id, 'regular')
            if main_image_result.get('success', True):
                property_obj.image = PropertyImage(**main_image_result)
            else:
                raise Exception(f"Failed to upload main image: {main_image_result.get('error', 'Unknown error')}")

        # Update property with new images
        property_obj.images.extend(images)
        property_obj.regularImageCount = len([img for img in property_obj.images if img.imageType == "regular"])
        property_obj.panoramicImageCount = len([img for img in property_obj.images if img.imageType == "panoramic"])

        # TODO: Get user_id from authentication
        user_id = request.form.get('user_id', 'user_123456')
        property_service.repository.update_property(property_id, property_obj)

        return jsonify({
            'success': True,
            'images': [
                {
                    'id': img.id,
                    'url': img.url,
                    'type': img.imageType
                } for img in images
            ]
        }), 201

    except Exception as e:
        logger.error(f"Error uploading images for property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'FILE_UPLOAD_ERROR',
                'message': 'Failed to upload images'
            }
        }), 500