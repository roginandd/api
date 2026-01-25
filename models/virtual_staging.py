from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class StyleEnum(str, Enum):
    """Available staging styles"""
    MODERN = "modern"
    CONTEMPORARY = "contemporary"
    MINIMALIST = "minimalist"
    TRADITIONAL = "traditional"
    INDUSTRIAL = "industrial"
    SCANDINAVIAN = "scandinavian"
    BOHEMIAN = "bohemian"
    RUSTIC = "rustic"
    LUXURY = "luxury"
    ECLECTIC = "eclectic"


class FurnitureThemeEnum(str, Enum):
    """Available furniture themes"""
    MINIMALIST = "minimalist"
    MAXIMALIST = "maximalist"
    MID_CENTURY = "mid_century"
    VINTAGE = "vintage"
    CONTEMPORARY = "contemporary"
    CLASSIC = "classic"
    SCANDINAVIAN = "scandinavian"
    INDUSTRIAL = "industrial"
    BOHEMIAN = "bohemian"
    TRANSITIONAL = "transitional"


class StagingParameters(BaseModel):
    """Parameters for customizing virtual staging"""
    role: str = Field(default="professional interior designer", description="Role description for the AI model")
    style: Optional[str] = Field(default=None, description="Staging style (e.g., modern, contemporary, minimalist)")
    furniture_style: Optional[str] = Field(default=None, description="Furniture style preference")
    color_scheme: Optional[str] = Field(default=None, description="Preferred color scheme")
    specific_requests: Optional[str] = Field(default=None, description="Additional customization requests")


class VirtualStaging(BaseModel):
    """Virtual staging session model"""
    
    session_id: str = Field(..., description="Unique identifier for the virtual staging session")
    property_id: str = Field(..., description="Identifier for the associated property")
    
    # Panoramic images from property
    panoramic_images: List[str] = Field(default_factory=list, description="List of panoramic image URLs from the property")
    current_image_index: int = Field(default=0, description="Index of the currently working panoramic image")
    
    # Chat history reference
    chat_history_id: Optional[str] = Field(default=None, description="Reference to the persistent virtual staging chat history")
    
    # Image storage
    orignal_image_key: Optional[str] = Field(default=None, description="S3 key of the original property image")
    original_image_url: Optional[str] = Field(default=None, description="Full URL of the original image in S3")
    original_image_path: Optional[str] = Field(default=None, description="Local file path of the original image")
    
    # Current state
    current_image_key: Optional[str] = Field(default=None, description="S3 key of current working image")
    current_image_url: Optional[str] = Field(default=None, description="Full URL of current working image")
    current_image_urls: Dict[int, str] = Field(default_factory=dict, description="Dictionary mapping panoramic image indices to their current working image URLs")
    current_image_path: Optional[str] = Field(default=None, description="Local file path of current working image")
    current_parameters: Optional[StagingParameters] = Field(default=None, description="Parameters for current working image")
    current_prompt: Optional[str] = Field(default=None, description="Prompt used for current working image")
    
    # Generation history
    generation_history: List[Dict[str, Any]] = Field(default_factory=list, description="All generation attempts in this session")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when session was created")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when session was last updated")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp when staging was completed")
    
    # Additional metadata
    error_message: Optional[str] = Field(default=None, description="Error message if staging failed")

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for Firestore"""
        # Explicitly include all fields to ensure nothing is lost
        data = {
            'session_id': self.session_id,
            'property_id': self.property_id,
            'panoramic_images': self.panoramic_images,
            'current_image_index': self.current_image_index,
            'chat_history_id': self.chat_history_id,
            'orignal_image_key': self.orignal_image_key,
            'original_image_url': self.original_image_url,
            'original_image_path': self.original_image_path,
            'current_image_key': self.current_image_key,
            'current_image_url': self.current_image_url,
            'current_image_urls': {str(k): v for k, v in self.current_image_urls.items()},  # Convert int keys to strings for Firestore
            'current_image_path': self.current_image_path,
            'current_prompt': self.current_prompt,
            'generation_history': self.generation_history,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'current_parameters': self.current_parameters.model_dump() if self.current_parameters else None
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VirtualStaging':
        """Create model from Firestore dictionary"""
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('completed_at'), str):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        
        # Handle current parameters
        if isinstance(data.get('current_parameters'), dict):
            data['current_parameters'] = StagingParameters(**data['current_parameters'])
        
        # Handle current_image_urls - convert string keys back to integers
        if isinstance(data.get('current_image_urls'), dict):
            data['current_image_urls'] = {int(k): v for k, v in data['current_image_urls'].items()}
        
        return cls(**data)