"""
Response models for Virtual Staging API
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class StagingMetadata(BaseModel):
    """Metadata about a staging result"""
    session_id: str = Field(..., description="Unique staging session identifier")
    property_id: int = Field(..., description="Associated property ID")
    user_id: int = Field(..., description="Associated user ID")
    room_name: str = Field(..., description="Room name/identifier")
    version: int = Field(..., description="Staging version/iteration number")
    
    style: str = Field(..., description="Applied staging style")
    furniture_theme: str = Field(..., description="Applied furniture theme")
    color_scheme: Optional[str] = Field(None, description="Applied color scheme (hex)")
    specific_request: Optional[str] = Field(None, description="Applied specific request")
    
    created_at: datetime = Field(..., description="When session was created")
    updated_at: datetime = Field(..., description="When this version was created")
    completed_at: Optional[datetime] = Field(None, description="When staging was completed")


class VirtualStagingResponse(BaseModel):
    """Response for virtual staging request with image and metadata"""
    image_url: str = Field(..., description="URL to the generated virtual staged image")
    metadata: StagingMetadata = Field(..., description="Metadata about the staging")
    prompt_used: Optional[str] = Field(None, description="The prompt used to generate this staging")


class StagingSessionResponse(BaseModel):
    """Response for getting a staging session"""
    session_id: str = Field(..., description="Unique staging session identifier")
    property_id: int = Field(..., description="Associated property ID")
    user_id: int = Field(..., description="Associated user ID")
    room_name: str = Field(..., description="Room name/identifier")
    
    original_image_url: str = Field(..., description="URL to the original image")
    generated_image_url: Optional[str] = Field(None, description="URL to the generated staged image")
    
    staging_parameters: Dict[str, Any] = Field(..., description="Current staging parameters")
    version: int = Field(..., description="Current version")
    prompts_count: int = Field(..., description="Number of prompts used so far")
    
    created_at: datetime = Field(..., description="When session was created")
    updated_at: datetime = Field(..., description="When session was last updated")
    completed_at: Optional[datetime] = Field(None, description="When staging was completed")
    error_message: Optional[str] = Field(None, description="Error message if staging failed")


class RefinementResponse(BaseModel):
    """Response for staging refinement"""
    image_url: str = Field(..., description="URL to the refined virtual staged image")
    version: int = Field(..., description="New version number after refinement")
    updated_at: datetime = Field(..., description="When the refinement was applied")
    prompt_used: str = Field(..., description="The prompt used for this refinement")
