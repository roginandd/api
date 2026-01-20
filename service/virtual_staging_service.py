"""Service layer for VirtualStaging entity"""
from typing import Optional, List, Tuple
from datetime import datetime
from models.virtual_staging import VirtualStaging, StagingParameters
from models.virtual_staging_response import VirtualStagingResponse, StagingMetadata, RefinementResponse, StagingSessionResponse
from repositories.virtual_staging_repository import VirtualStagingRepository
from service.gemini_service import GeminiService
from config.prompt_config import build_staging_prompt, build_refinement_context


class VirtualStagingService:
    """Business logic for virtual staging sessions"""
    
    def __init__(self, gemini_model: str = "gemini-2.5-flash-image"):
        self.repository = VirtualStagingRepository()
        self.gemini_service = GeminiService()
        self.gemini_model = gemini_model
    
    def create_staging_session(self,
                              session_id: str,
                              property_id: int,
                              user_id: int,
                              room_name: str,
                              original_image_key: str,
                              staging_parameters: StagingParameters) -> Optional[VirtualStaging]:
        """Create a new virtual staging session"""
        if not self._validate_staging(session_id, property_id, user_id, room_name, original_image_key):
            return None
        
        staging = VirtualStaging(
            session_id=session_id,
            property_id=property_id,
            user_id=user_id,
            room_name=room_name,
            orignal_image_key=original_image_key,
            staging_parameters=staging_parameters
        )
        return self.repository.create_session(staging)
    
    def generate_staging(self,
                        session_id: str,
                        original_image_url: str,
                        staging_parameters: Optional[StagingParameters] = None,
                        custom_prompt: Optional[str] = None,
                        mask_image_url: Optional[str] = None) -> Optional[VirtualStagingResponse]:
        """
        Generate virtual staging with Gemini and return image + metadata
        
        Args:
            session_id: Session ID
            original_image_url: URL of original image
            staging_parameters: Staging parameters (style, furniture, color, request) - optional
            custom_prompt: Custom prompt for Gemini to edit the image - if provided, takes precedence
            mask_image_url: Optional mask image to specify a specific area/point for editing
        
        Returns:
            VirtualStagingResponse with image URL and metadata, or None if failed
        """
        try:
            # Use custom_prompt if provided, otherwise build from staging_parameters
            if custom_prompt:
                prompt = custom_prompt
            elif staging_parameters:
                prompt = build_staging_prompt(
                    role=staging_parameters.role,
                    style=staging_parameters.style.value,
                    furniture_theme=staging_parameters.furniture_theme.value,
                    color_scheme=staging_parameters.color_scheme,
                    specific_request=staging_parameters.specific_request
                )
            else:
                return None
            
            # Generate virtually staged image with optional mask
            generated_image_bytes = self.gemini_service.generate_image_from_image(
                model=self.gemini_model,
                image_path=original_image_url,
                prompt=prompt,
                mask_image_path=mask_image_url
            )
            
            generated_image_path = None
            if generated_image_bytes:
                # Save generated image to disk instead of storing in database
                import os
                from pathlib import Path
                
                # Create uploads directory if needed
                uploads_dir = 'uploads'
                Path(uploads_dir).mkdir(parents=True, exist_ok=True)
                
                # Create filename with session_id for tracking
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                generated_filename = f"{timestamp}staged_{session_id}.png"
                generated_image_path = os.path.join(uploads_dir, generated_filename)
                
                # Save image bytes to disk
                with open(generated_image_path, 'wb') as f:
                    f.write(generated_image_bytes)
                
                print(f"Generated image saved to: {generated_image_path}")
            
            # Store in session (only path, not full base64)
            staging = self.get_session(session_id)
            if staging:
                staging.prompts.append(prompt)
                # Store only the file path, not the entire image data
                if generated_image_path:
                    staging.generated_image_key = generated_image_path
                staging.updated_at = datetime.utcnow()
                self.repository.update_session(staging)
            
            # Build response with metadata
            if staging:
                metadata = StagingMetadata(
                    session_id=session_id,
                    property_id=staging.property_id,
                    user_id=staging.user_id,
                    room_name=staging.room_name,
                    version=staging.version,
                    style=staging_parameters.style.value if staging_parameters else "custom",
                    furniture_theme=staging_parameters.furniture_theme.value if staging_parameters else "custom",
                    color_scheme=staging_parameters.color_scheme if staging_parameters else None,
                    specific_request=staging_parameters.specific_request if staging_parameters else None,
                    created_at=staging.created_at,
                    updated_at=datetime.utcnow(),
                    completed_at=staging.completed_at
                )
            else:
                # Fallback metadata if session not found
                metadata = StagingMetadata(
                    session_id=session_id,
                    property_id=0,
                    user_id=0,
                    room_name="",
                    version=1,
                    style=staging_parameters.style.value if staging_parameters else "custom",
                    furniture_theme=staging_parameters.furniture_theme.value if staging_parameters else "custom",
                    color_scheme=staging_parameters.color_scheme if staging_parameters else None,
                    specific_request=staging_parameters.specific_request if staging_parameters else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    completed_at=None
                )
            
            return VirtualStagingResponse(
                image_url=generated_image_path or "generated_image.png",
                metadata=metadata,
                prompt_used=prompt
            )
        
        except Exception as e:
            print(f"Error generating staging: {str(e)}")
            return None
    
    def get_session(self, session_id: str) -> Optional[VirtualStaging]:
        """Get staging session by ID"""
        return self.repository.get_session(session_id)
    
    def get_sessions_by_property(self, property_id: int) -> List[tuple[str, VirtualStaging]]:
        """Get all sessions for a property"""
        return self.repository.get_sessions_by_property(property_id)
    
    def get_sessions_by_user(self, user_id: int) -> List[tuple[str, VirtualStaging]]:
        """Get all sessions for a user"""
        return self.repository.get_sessions_by_user(user_id)
    
    def get_session_response(self, session_id: str) -> Optional[StagingSessionResponse]:
        """
        Get staging session as API response with all metadata
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        params_dict = session.staging_parameters.model_dump()
        
        return StagingSessionResponse(
            session_id=session.session_id,
            property_id=session.property_id,
            user_id=session.user_id,
            room_name=session.room_name,
            original_image_url=session.orignal_image_key,
            generated_image_url=session.generated_image_key,
            staging_parameters=params_dict,
            version=session.version,
            prompts_count=len(session.prompts),
            created_at=session.created_at,
            updated_at=session.updated_at,
            completed_at=session.completed_at,
            error_message=session.error_message
        )
    
    def complete_staging(self, session_id: str, generated_image_key: str) -> bool:
        """Complete staging with generated image"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.generated_image_key = generated_image_key
        session.completed_at = datetime.utcnow()
        return self.repository.update_generated_image(session_id, generated_image_key)
    
    def add_refinement_prompt(self, session_id: str, prompt: str) -> bool:
        """Add refinement prompt to session"""
        return self.repository.add_prompt(session_id, prompt)
    
    def refine_staging(self,
                      session_id: str,
                      original_image_url: str,
                      new_staging_parameters: StagingParameters) -> Optional[RefinementResponse]:
        """
        Refine existing staging with new parameters
        
        Args:
            session_id: Session ID to refine
            original_image_url: Original image URL for transformation
            new_staging_parameters: Updated staging parameters
        
        Returns:
            RefinementResponse with new image and metadata, or None if failed
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        try:
            # Build refinement prompt with context
            chat_history = session.prompts[-3:] if len(session.prompts) > 0 else []
            refinement_context = build_refinement_context(
                previous_parameters=session.staging_parameters.model_dump(),
                new_parameters=new_staging_parameters.model_dump(),
                chat_history=chat_history
            )
            
            # Build the new staging prompt
            refinement_prompt = build_staging_prompt(
                role=new_staging_parameters.role,
                style=new_staging_parameters.style.value,
                furniture_theme=new_staging_parameters.furniture_theme.value,
                color_scheme=new_staging_parameters.color_scheme,
                specific_request=new_staging_parameters.specific_request
            )
            
            # Add context and history
            full_refinement_prompt = f"{refinement_context}\n\n{refinement_prompt}"
            
            # Generate refined image
            refined_image = self.gemini_service.generate_image_from_image(
                model=self.gemini_model,
                image_path=original_image_url,
                prompt=full_refinement_prompt
            )
            
            if not refined_image:
                refined_image = original_image_url  # Fallback
            
            # Update session
            session.prompts.append(full_refinement_prompt)
            session.generated_image_key = refined_image
            session.version += 1
            session.updated_at = datetime.utcnow()
            session.staging_parameters = new_staging_parameters
            
            self.repository.update_session(session)
            
            # Return refinement response
            return RefinementResponse(
                image_url=refined_image,
                version=session.version,
                updated_at=session.updated_at,
                prompt_used=full_refinement_prompt
            )
        
        except Exception as e:
            print(f"Error refining staging: {str(e)}")
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """Delete staging session"""
        return self.repository.delete_session(session_id)
    
    def _validate_staging(self, session_id: str, property_id: int, user_id: int,
                         room_name: str, original_image_key: str) -> bool:
        """Validate staging fields"""
        return (
            session_id and session_id.strip() and
            property_id > 0 and
            user_id > 0 and
            room_name and room_name.strip() and
            original_image_key and original_image_key.strip()
        )
