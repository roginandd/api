"""Buyer controller for lightweight property endpoints"""
from flask import Blueprint, request, jsonify
from typing import List, Dict, Any, Optional
from service.property_service import PropertyService
from models.property import PropertyCardPayload, PropertyDetailsPayload, FilterPayload, PropertyImagePayload
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

buyer_bp = Blueprint('buyer', __name__, url_prefix='/api/buyer')
property_service = PropertyService()


def _convert_to_property_card_payload(property_id: str, property_data: Dict[str, Any]) -> PropertyCardPayload:
    """Convert full property data to lightweight card payload"""
    # Get primary image URL
    image_url = ""
    if property_data.get('images') and len(property_data['images']) > 0:
        # Use the first regular image or any image as fallback
        for img in property_data['images']:
            if img.get('imageType') == 'regular':
                image_url = img.get('url', '')
                break
        if not image_url and property_data['images']:
            image_url = property_data['images'][0].get('url', '')

    return PropertyCardPayload(
        propertyId=property_id,
        name=property_data.get('name', ''),
        address=property_data.get('address', ''),
        price=property_data.get('price', 0),
        priceNegotiable=property_data.get('priceNegotiable', False),
        listingType=property_data.get('listingType', ''),
        bedrooms=property_data.get('bedrooms'),
        bathrooms=property_data.get('bathrooms'),
        floorArea=property_data.get('floorArea'),
        propertyType=property_data.get('propertyType', ''),
        furnishing=property_data.get('furnishing'),
        imageUrl=property_data.get('image').get('url')
    )


def _convert_to_property_details_payload(property_id: str, property_data: Dict[str, Any]) -> PropertyDetailsPayload:
    """Convert full property data to detailed payload"""
    # Convert images to simplified format
    images = []
    if property_data.get('images'):
        for img in property_data['images']:
            images.append(PropertyImagePayload(
                id=img.get('id', ''),
                url=img.get('url', ''),
                imageType=img.get('imageType', 'regular')
            ))

    return PropertyDetailsPayload(
        propertyId=property_id,
        name=property_data.get('name', ''),
        listingType=property_data.get('listingType', ''),
        propertyType=property_data.get('propertyType', ''),
        status=property_data.get('status'),
        address=property_data.get('address', ''),
        price=property_data.get('price', 0),
        priceNegotiable=property_data.get('priceNegotiable', False),
        associationDues=property_data.get('associationDues'),
        bedrooms=property_data.get('bedrooms'),
        bathrooms=property_data.get('bathrooms'),
        floorArea=property_data.get('floorArea'),
        parkingSlots=property_data.get('parkingSlots'),
        description=property_data.get('description'),
        furnishing=property_data.get('furnishing'),
        condition=property_data.get('condition'),
        lotArea=property_data.get('lotArea'),
        yearBuilt=property_data.get('yearBuilt'),
        storeys=property_data.get('storeys'),
        interiorFeatures=property_data.get('interiorFeatures', []),
        amenities=property_data.get('amenities', []),
        buildingAmenities=property_data.get('buildingAmenities', []),
        images=images,
        agentName=property_data.get('agentName'),
        agentPhone=property_data.get('agentPhone'),
        agentEmail=property_data.get('agentEmail'),
        agentExperience=property_data.get('agentExperience')
    )


@buyer_bp.route('/properties', methods=['GET'])
def get_property_cards():
    """Get lightweight property cards for marketplace listings"""
    try:
        # Get query parameters for filtering
        filters = FilterPayload(
            location=request.args.get('location'),
            propertyType=request.args.get('propertyType'),
            minPrice=float(request.args.get('minPrice')) if request.args.get('minPrice') else None,
            maxPrice=float(request.args.get('maxPrice')) if request.args.get('maxMax') else None,
            bedrooms=int(request.args.get('bedrooms')) if request.args.get('bedrooms') else None
        )

        # Get pagination parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))

        # Get all published properties (for buyer marketplace)
        all_properties = property_service.get_all_properties()

        # Filter properties
        filtered_properties = []
        for prop_id, prop in all_properties:
            prop_dict = prop.model_dump()

            # Only include published properties
            if prop_dict.get('status') != 'published':
                continue

            # Apply filters
            if filters.location and filters.location.lower() not in prop_dict.get('address', '').lower():
                continue
            if filters.propertyType and prop_dict.get('propertyType') != filters.propertyType:
                continue
            if filters.minPrice and prop_dict.get('price', 0) < filters.minPrice:
                continue
            if filters.maxPrice and prop_dict.get('price', 0) > filters.maxPrice:
                continue
            if filters.bedrooms and prop_dict.get('bedrooms') != filters.bedrooms:
                continue

            filtered_properties.append((prop_id, prop_dict))

        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_properties = filtered_properties[start_idx:end_idx]

        # Convert to card payloads
        property_cards = []
        for prop_id, prop_dict in paginated_properties:
            try:
                card = _convert_to_property_card_payload(prop_id, prop_dict)
                property_cards.append(card.model_dump())
            except Exception as e:
                logger.warning(f"Failed to convert property {prop_id} to card: {str(e)}")
                continue

        return jsonify({
            'success': True,
            'properties': property_cards,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': len(filtered_properties),
                'pages': (len(filtered_properties) + limit - 1) // limit
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting property cards: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get property cards'
            }
        }), 500


@buyer_bp.route('/<property_id>', methods=['GET'])
def get_property_details(property_id: str):
    """Get detailed property information for property details view"""
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

        prop_dict = property_obj.model_dump()

        # Convert to details payload
        details = _convert_to_property_details_payload(property_id, prop_dict)

        return jsonify({
            'success': True,
            'property': details.model_dump()
        }), 200

    except Exception as e:
        logger.error(f"Error getting property details {property_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get property details'
            }
        }), 500


@buyer_bp.route('/properties/search', methods=['POST'])
def search_properties():
    """Search properties with advanced filters"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': {
                    'code': 'INVALID_REQUEST',
                    'message': 'Request body is required'
                }
            }), 400

        # Parse filter payload
        filters = FilterPayload(**data)

        # Get all published properties
        all_properties = property_service.get_all_properties()

        # Apply filters
        filtered_properties = []
        for prop_id, prop in all_properties:
            prop_dict = prop.model_dump()

            # Only include published properties
            if prop_dict.get('status') != 'published':
                continue

            # Apply filters
            if filters.location and filters.location.lower() not in prop_dict.get('address', '').lower():
                continue
            if filters.propertyType and prop_dict.get('propertyType') != filters.propertyType:
                continue
            if filters.minPrice and prop_dict.get('price', 0) < filters.minPrice:
                continue
            if filters.maxPrice and prop_dict.get('price', 0) > filters.maxPrice:
                continue
            if filters.bedrooms and prop_dict.get('bedrooms') != filters.bedrooms:
                continue

            filtered_properties.append((prop_id, prop_dict))

        # Convert to card payloads (limit to first 50 for search results)
        property_cards = []
        for prop_id, prop_dict in filtered_properties[:50]:
            try:
                card = _convert_to_property_card_payload(prop_id, prop_dict)
                property_cards.append(card.model_dump())
            except Exception as e:
                logger.warning(f"Failed to convert property {prop_id} to card: {str(e)}")
                continue

        return jsonify({
            'success': True,
            'properties': property_cards,
            'total': len(filtered_properties)
        }), 200

    except Exception as e:
        logger.error(f"Error searching properties: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to search properties'
            }
        }), 500


@buyer_bp.route('/properties-view', methods=['GET'])
def get_properties_in_buyer_side():
    """Get properties for buyer dashboard/marketplace view"""
    try:
        # Get query parameters for filtering
        user_id = request.args.get('user_id')  # Optional: for personalized recommendations
        location = request.args.get('location')
        property_type = request.args.get('propertyType')
        min_price = request.args.get('minPrice')
        max_price = request.args.get('maxPrice')
        bedrooms = request.args.get('bedrooms')

        # Get all properties (no status filter)
        all_properties = property_service.get_all_properties()

        # Filter properties for buyer view
        filtered_properties = []
        for prop_id, prop in all_properties:
            prop_dict = prop.model_dump()

            # Apply filters
            if location and location.lower() not in prop_dict.get('address', '').lower():
                continue
            if property_type and prop_dict.get('propertyType') != property_type:
                continue
            if min_price and prop_dict.get('price', 0) < float(min_price):
                continue
            if max_price and prop_dict.get('price', 0) > float(max_price):
                continue
            if bedrooms and prop_dict.get('bedrooms') != int(bedrooms):
                continue

            filtered_properties.append((prop_id, prop_dict))

        # Convert to PropertyCardPayload objects (no pagination)
        properties_list = []
        for prop_id, prop_dict in filtered_properties:
            try:
                card = _convert_to_property_card_payload(prop_id, prop_dict)
                properties_list.append(card.model_dump())
            except Exception as e:
                logger.warning(f"Failed to convert property {prop_id} to card: {str(e)}")
                continue

        return jsonify({
            'success': True,
            'properties': properties_list,
            'total': len(filtered_properties),
            'filters': {
                'location': location,
                'propertyType': property_type,
                'minPrice': min_price,
                'maxPrice': max_price,
                'bedrooms': bedrooms
            }
        }), 200

    except Exception as e:
        logger.error(f"Error getting buyer properties view: {str(e)}")
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Failed to get buyer properties view'
            }
        }), 500