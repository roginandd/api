from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime


class Inquiry(BaseModel):
    """Inquiry model for property inquiries"""
    inquiryId: Optional[str] = Field(None, description="Unique inquiry ID")
    propertyId: str = Field(..., description="Property ID being inquired about")
    buyerId: str = Field(..., description="User ID of the buyer/inquirer")
    sellerName: Optional[str] = Field(None, description="Seller name for reference")
    buyerName: Optional[str] = Field(None, description="Buyer name")
    buyerEmail: Optional[str] = Field(None, description="Buyer email")
    buyerPhone: Optional[str] = Field(None, description="Buyer phone number")
    message: Optional[str] = Field(None, description="Inquiry message")
    inquiryType: str = Field("general", description="Type of inquiry: general, viewing, offer, etc.")
    status: str = Field("new", description="Status: new, read, replied, closed")
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    repliedAt: Optional[datetime] = Field(None, description="When the inquiry was replied to")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firestore"""
        data = self.model_dump()
        data['createdAt'] = self.createdAt.isoformat()
        data['updatedAt'] = self.updatedAt.isoformat()
        if self.repliedAt:
            data['repliedAt'] = self.repliedAt.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Inquiry':
        """Create from Firestore dictionary"""
        if isinstance(data.get('createdAt'), str):
            data['createdAt'] = datetime.fromisoformat(data['createdAt'])
        if isinstance(data.get('updatedAt'), str):
            data['updatedAt'] = datetime.fromisoformat(data['updatedAt'])
        if isinstance(data.get('repliedAt'), str) and data['repliedAt']:
            data['repliedAt'] = datetime.fromisoformat(data['repliedAt'])
        return cls(**data)


class PropertyView(BaseModel):
    """Property view tracking"""
    viewId: Optional[str] = Field(None, description="Unique view ID")
    propertyId: str = Field(..., description="Property ID")
    userId: Optional[str] = Field(None, description="User ID if logged in")
    viewedAt: datetime = Field(default_factory=datetime.utcnow)
    ipAddress: Optional[str] = Field(None, description="IP address of viewer")
    referrer: Optional[str] = Field(None, description="Referrer source")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firestore"""
        data = self.model_dump()
        data['viewedAt'] = self.viewedAt.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PropertyView':
        """Create from Firestore dictionary"""
        if isinstance(data.get('viewedAt'), str):
            data['viewedAt'] = datetime.fromisoformat(data['viewedAt'])
        return cls(**data)
