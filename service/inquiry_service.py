"""Service layer for Inquiry and PropertyView"""
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from models.inquiry import Inquiry, PropertyView
from repositories.inquiry_repository import InquiryRepository, PropertyViewRepository


class InquiryService:
    """Business logic for inquiry management"""

    def __init__(self):
        self.inquiry_repository = InquiryRepository()
        self.view_repository = PropertyViewRepository()

    def create_inquiry(self, property_id: str, buyer_id: str, data: Dict[str, Any]) -> Tuple[str, Inquiry]:
        """
        Create a new inquiry

        Args:
            property_id: Property ID
            buyer_id: Buyer/inquirer user ID
            data: Inquiry data (buyerName, buyerEmail, buyerPhone, message, inquiryType)

        Returns:
            Tuple of (inquiry_id, Inquiry)
        """
        # Generate inquiry ID
        inquiry_id = f"inq_{int(datetime.utcnow().timestamp() * 1000)}_{str(uuid.uuid4())[:9]}"

        inquiry = Inquiry(
            inquiryId=inquiry_id,
            propertyId=property_id,
            buyerId=buyer_id,
            buyerName=data.get('buyerName'),
            buyerEmail=data.get('buyerEmail'),
            buyerPhone=data.get('buyerPhone'),
            message=data.get('message'),
            inquiryType=data.get('inquiryType', 'general'),
            status='new',
            createdAt=datetime.utcnow(),
            updatedAt=datetime.utcnow()
        )

        created = self.inquiry_repository.create_inquiry(inquiry, inquiry_id)
        return inquiry_id, created

    def get_inquiry(self, inquiry_id: str) -> Optional[Inquiry]:
        """Get inquiry by ID"""
        return self.inquiry_repository.get_inquiry(inquiry_id)

    def get_inquiries_by_property(self, property_id: str) -> List[Tuple[str, Inquiry]]:
        """Get all inquiries for a property"""
        return self.inquiry_repository.get_inquiries_by_property(property_id)

    def get_inquiry_count_for_property(self, property_id: str) -> int:
        """Get inquiry count for a property"""
        inquiries = self.get_inquiries_by_property(property_id)
        return len(inquiries)

    def update_inquiry_status(self, inquiry_id: str, status: str, seller_id: str = None) -> Optional[Inquiry]:
        """
        Update inquiry status

        Args:
            inquiry_id: Inquiry ID
            status: New status (new, read, replied, closed)
            seller_id: Optional seller ID for authorization

        Returns:
            Updated Inquiry or None
        """
        inquiry = self.get_inquiry(inquiry_id)
        if not inquiry:
            return None

        inquiry.status = status
        inquiry.updatedAt = datetime.utcnow()
        
        if status == 'replied':
            inquiry.repliedAt = datetime.utcnow()

        return self.inquiry_repository.update_inquiry(inquiry_id, inquiry)

    def delete_inquiry(self, inquiry_id: str) -> bool:
        """Delete an inquiry"""
        return self.inquiry_repository.delete_inquiry(inquiry_id)

    def record_property_view(self, property_id: str, user_id: str = None, ip_address: str = None, referrer: str = None) -> Tuple[str, PropertyView]:
        """
        Record a property view

        Args:
            property_id: Property ID
            user_id: Optional user ID if logged in
            ip_address: Optional IP address
            referrer: Optional referrer source

        Returns:
            Tuple of (view_id, PropertyView)
        """
        view_id = f"view_{int(datetime.utcnow().timestamp() * 1000)}_{str(uuid.uuid4())[:9]}"

        view = PropertyView(
            viewId=view_id,
            propertyId=property_id,
            userId=user_id,
            ipAddress=ip_address,
            referrer=referrer,
            viewedAt=datetime.utcnow()
        )

        created = self.view_repository.create_view(view, view_id)
        return view_id, created

    def get_property_view_count(self, property_id: str) -> int:
        """Get total view count for a property"""
        return self.view_repository.get_property_view_count(property_id)

    def get_views_by_property(self, property_id: str) -> List[Tuple[str, PropertyView]]:
        """Get all views for a property"""
        return self.view_repository.get_views_by_property(property_id)
