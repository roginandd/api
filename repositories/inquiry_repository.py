"""Repository for Inquiry model"""
from typing import Dict, Any, List, Optional
from models.inquiry import Inquiry, PropertyView
from repositories.base_repository import BaseRepository


class InquiryRepository(BaseRepository[Inquiry]):
    """Repository for managing inquiries"""

    def __init__(self):
        super().__init__('inquiries')

    def to_model(self, data: Dict[str, Any]) -> Inquiry:
        """Convert Firestore document to Inquiry model"""
        return Inquiry.from_dict(data)

    def to_dict(self, model: Inquiry) -> Dict[str, Any]:
        """Convert Inquiry model to Firestore document"""
        return model.to_dict()

    def create_inquiry(self, inquiry_model: Inquiry, inquiry_id: str) -> Inquiry:
        """
        Create a new inquiry

        Args:
            inquiry_model: Inquiry model instance
            inquiry_id: Unique inquiry ID string

        Returns:
            Created Inquiry model
        """
        return self.create(inquiry_id, inquiry_model)

    def get_inquiry(self, inquiry_id: str) -> Optional[Inquiry]:
        """
        Get inquiry by ID

        Args:
            inquiry_id: Inquiry ID string

        Returns:
            Inquiry model or None
        """
        return self.get(inquiry_id)

    def get_inquiries_by_property(self, property_id: str) -> List[tuple[str, Inquiry]]:
        """
        Get all inquiries for a property

        Args:
            property_id: Property ID

        Returns:
            List of tuples (inquiry_id, Inquiry)
        """
        query = self.collection.where(field_path='propertyId', op_string='==', value=property_id)
        docs = query.stream()
        return [(doc.id, self.to_model(doc.to_dict())) for doc in docs]

    def get_inquiries_by_seller(self, seller_id: str, property_id: str = None) -> List[tuple[str, Inquiry]]:
        """
        Get all inquiries for properties of a seller

        Args:
            seller_id: Seller/user ID
            property_id: Optional property ID filter

        Returns:
            List of tuples (inquiry_id, Inquiry)
        """
        # This requires cross-collection query, handled in service layer
        docs = self.collection.stream()
        inquiries = [(doc.id, self.to_model(doc.to_dict())) for doc in docs]
        
        if property_id:
            return [(id, inq) for id, inq in inquiries if inq.propertyId == property_id]
        return inquiries

    def update_inquiry(self, inquiry_id: str, inquiry_model: Inquiry) -> Inquiry:
        """
        Update an existing inquiry

        Args:
            inquiry_id: Inquiry ID
            inquiry_model: Updated Inquiry model

        Returns:
            Updated Inquiry model
        """
        return self.update(inquiry_id, inquiry_model)

    def delete_inquiry(self, inquiry_id: str) -> bool:
        """
        Delete an inquiry

        Args:
            inquiry_id: Inquiry ID

        Returns:
            True if deleted
        """
        return self.delete(inquiry_id)


class PropertyViewRepository(BaseRepository[PropertyView]):
    """Repository for managing property views"""

    def __init__(self):
        super().__init__('property_views')

    def to_model(self, data: Dict[str, Any]) -> PropertyView:
        """Convert Firestore document to PropertyView model"""
        return PropertyView.from_dict(data)

    def to_dict(self, model: PropertyView) -> Dict[str, Any]:
        """Convert PropertyView model to Firestore document"""
        return model.to_dict()

    def create_view(self, view_model: PropertyView, view_id: str) -> PropertyView:
        """
        Record a property view

        Args:
            view_model: PropertyView model instance
            view_id: Unique view ID string

        Returns:
            Created PropertyView model
        """
        return self.create(view_id, view_model)

    def get_property_view_count(self, property_id: str) -> int:
        """
        Get total view count for a property

        Args:
            property_id: Property ID

        Returns:
            View count
        """
        query = self.collection.where(field_path='propertyId', op_string='==', value=property_id)
        docs = query.stream()
        return len(list(docs))

    def get_views_by_property(self, property_id: str) -> List[tuple[str, PropertyView]]:
        """
        Get all views for a property

        Args:
            property_id: Property ID

        Returns:
            List of tuples (view_id, PropertyView)
        """
        query = self.collection.where(field_path='propertyId', op_string='==', value=property_id)
        docs = query.stream()
        return [(doc.id, self.to_model(doc.to_dict())) for doc in docs]
