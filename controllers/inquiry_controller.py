"""Inquiry controller for handling inquiry-related API endpoints"""
from flask import Blueprint, request, jsonify
import logging
from service.inquiry_service import InquiryService
from service.property_service import PropertyService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

inquiry_bp = Blueprint('inquiry', __name__, url_prefix='/api/inquiries')
inquiry_service = InquiryService()
property_service = PropertyService()


@inquiry_bp.route('', methods=['POST'])
def create_inquiry():
    """Create a new inquiry for a property"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'No data provided'
                }
            }), 400

        property_id = data.get('propertyId')
        buyer_id = data.get('buyerId', 'user_123456')  # TODO: From auth

        if not property_id:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'propertyId is required'
                }
            }), 400

        # Verify property exists
        property_obj = property_service.get_property(property_id)
        if not property_obj:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'PROPERTY_NOT_FOUND',
                    'message': 'Property not found'
                }
            }), 404

        inquiry_id, inquiry = inquiry_service.create_inquiry(property_id, buyer_id, data)

        return jsonify({
            'success': True,
            'inquiry': {
                'id': inquiry_id,
                'propertyId': inquiry.propertyId,
                'buyerId': inquiry.buyerId,
                'status': inquiry.status,
                'created_at': inquiry.createdAt.isoformat()
            }
        }), 201

    except Exception as e:
        logger.error(f"Error creating inquiry: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to create inquiry'
            }
        }), 500


@inquiry_bp.route('/<inquiry_id>', methods=['GET'])
def get_inquiry(inquiry_id: str):
    """Get inquiry by ID"""
    try:
        inquiry = inquiry_service.get_inquiry(inquiry_id)
        if not inquiry:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'INQUIRY_NOT_FOUND',
                    'message': 'Inquiry not found'
                }
            }), 404

        return jsonify({
            'success': True,
            'inquiry': inquiry.model_dump()
        }), 200

    except Exception as e:
        logger.error(f"Error getting inquiry {inquiry_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get inquiry'
            }
        }), 500


@inquiry_bp.route('/property/<property_id>', methods=['GET'])
def get_inquiries_by_property(property_id: str):
    """Get all inquiries for a property"""
    try:
        inquiries = inquiry_service.get_inquiries_by_property(property_id)

        inquiries_list = []
        for inq_id, inq in inquiries:
            inq_dict = inq.model_dump()
            inq_dict['id'] = inq_id
            inquiries_list.append(inq_dict)

        return jsonify({
            'success': True,
            'inquiries': inquiries_list,
            'total': len(inquiries_list)
        }), 200

    except Exception as e:
        logger.error(f"Error getting inquiries for property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get inquiries'
            }
        }), 500


@inquiry_bp.route('/<inquiry_id>/status', methods=['PUT'])
def update_inquiry_status(inquiry_id: str):
    """Update inquiry status"""
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'status is required'
                }
            }), 400

        seller_id = data.get('seller_id')  # TODO: From auth
        status = data.get('status')

        updated_inquiry = inquiry_service.update_inquiry_status(inquiry_id, status, seller_id)
        if not updated_inquiry:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'INQUIRY_NOT_FOUND',
                    'message': 'Inquiry not found'
                }
            }), 404

        return jsonify({
            'success': True,
            'inquiry': updated_inquiry.model_dump()
        }), 200

    except Exception as e:
        logger.error(f"Error updating inquiry {inquiry_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to update inquiry'
            }
        }), 500


@inquiry_bp.route('/<inquiry_id>', methods=['DELETE'])
def delete_inquiry(inquiry_id: str):
    """Delete an inquiry"""
    try:
        success = inquiry_service.delete_inquiry(inquiry_id)
        if not success:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'INQUIRY_NOT_FOUND',
                    'message': 'Inquiry not found'
                }
            }), 404

        return jsonify({
            'success': True,
            'message': 'Inquiry deleted successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error deleting inquiry {inquiry_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to delete inquiry'
            }
        }), 500


@inquiry_bp.route('/property/<property_id>/view', methods=['POST'])
def record_property_view(property_id: str):
    """Record a property view"""
    try:
        data = request.get_json() or {}
        user_id = data.get('userId')
        ip_address = request.remote_addr
        referrer = data.get('referrer')

        view_id, view = inquiry_service.record_property_view(
            property_id,
            user_id=user_id,
            ip_address=ip_address,
            referrer=referrer
        )

        return jsonify({
            'success': True,
            'view': {
                'id': view_id,
                'propertyId': view.propertyId,
                'viewed_at': view.viewedAt.isoformat()
            }
        }), 201

    except Exception as e:
        logger.error(f"Error recording view for property {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to record view'
            }
        }), 500
