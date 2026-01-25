"""Service layer for VirtualStaging entity with versioning and save/revert functionality"""
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from models.virtual_staging import VirtualStaging, StagingParameters
from models.virtual_staging_response import (
    VirtualStagingResponse, 
    StagingMetadata, 
    RefinementResponse, 
    StagingSessionResponse,
    SaveChangeResponse,
    RevertChangeResponse,
    VersionHistoryResponse,
    VersionHistoryItem
)
from repositories.virtual_staging_repository import VirtualStagingRepository
from service.gemini_service import GeminiService
from service.aws_service import AWSService
from service.virtual_staging_chat_history_service import VirtualStagingChatHistoryService
from config.prompt_config import build_staging_prompt, build_refinement_context
from pathlib import Path
import os
import uuid


class VirtualStagingService:
    """Business logic for virtual staging sessions with versioning support"""
    
    def __init__(self, gemini_model: str = "gemini-2.5-flash-image"):
        self.repository = VirtualStagingRepository()
        self.gemini_service = GeminiService()
        self.aws_service = AWSService()
        self.chat_history_service = VirtualStagingChatHistoryService()
        self.gemini_model = gemini_model
        self.base_url = "https://vista-resources.s3.ap-southeast-2.amazonaws.com/"
    
    def create_staging_session_from_s3(self,
                              session_id: str,
                              property_id: str,
                              original_image_url: str,
                              panoramic_images: List[str],
                              staging_parameters: StagingParameters) -> Optional[VirtualStaging]:
        """
        Create a new virtual staging session with S3 image URL
        
        Args:
            session_id: Unique session identifier
            property_id: Property ID
            original_image_url: S3 URL to the original image (first panoramic)
            panoramic_images: List of all panoramic image URLs from the property
            staging_parameters: Staging parameters for customization
            
        Returns:
            Created VirtualStaging session or None if failed
        """
        if not self._validate_staging(session_id, property_id):
            return None
        
        try:
            # Validate S3 URL
            if not original_image_url or not (original_image_url.startswith('http://') or original_image_url.startswith('https://')):
                print(f"Error: Invalid S3 URL: {original_image_url}")
                return None
            
            print(f"[SESSION] Using original image from S3: {original_image_url[:50]}...")
            
            # Extract S3 key from URL
            s3_key = self.aws_service.get_s3_key_from_url(original_image_url)
            
            print(f"[SESSION] Uploaded original image to S3: {original_image_url}")
            
            # Create chat history for this session
            chat_history_id = f"chat_{session_id}"
            chat_history = self.chat_history_service.create_chat_history(
                history_id=chat_history_id,
                session_id=session_id,
                property_id=property_id,
                user_id="default"
            )
            
            if not chat_history:
                print(f"[SESSION] Failed to create chat history for session {session_id}")
                return None
            
            print(f"[SESSION] Chat history created: {chat_history_id}")
            
            # Create session in database with S3 URLs (no local paths for deployment)
            staging = VirtualStaging(
                session_id=session_id,
                property_id=property_id,
                panoramic_images=panoramic_images,
                current_image_index=0,
                chat_history_id=chat_history_id,
                orignal_image_key=s3_key,  # S3 key
                original_image_url=original_image_url,  # S3 URL
                current_parameters=staging_parameters
            )
            
            print(f"[SESSION] VirtualStaging created with S3 URL: {staging.original_image_url}")
            
            created_session = self.repository.create_session(staging)
            
            if created_session:
                print(f"[SESSION] Session {session_id} created with chat history")
                print(f"[SESSION] S3 key: {created_session.orignal_image_key}")
            
            return created_session
        
        except Exception as e:
            print(f"Error creating staging session: {str(e)}")
            return None
    
    def create_staging_session(self,
                              session_id: str,
                              property_id: str,
                              user_id: str,
                              room_name: str,
                              original_image_path: str,
                              staging_parameters: StagingParameters) -> Optional[VirtualStaging]:
        """
        DEPRECATED: Use create_staging_session_from_s3 instead.
        Create a new virtual staging session with local image file (for backward compatibility)
        """
        print("[SESSION] WARNING: create_staging_session with local file is deprecated. Use create_staging_session_from_s3")
        # For now, return None to force use of new S3 method
        return None
    
    def generate_staging(self,
                        session_id: str,
                        image_index: int = 0,
                        staging_parameters: Optional[StagingParameters] = None,
                        custom_prompt: Optional[str] = None,
                        mask_image_url: Optional[str] = None,
                        user_message: Optional[str] = None,
                        image_path_override: Optional[str] = None) -> Optional[VirtualStagingResponse]:
        """
        Generate virtual staging with Gemini.
        Uses the panoramic image at the specified index.
        
        Args:
            session_id: Session ID
            image_index: Index of panoramic image to generate on
            staging_parameters: Staging parameters (optional, uses session defaults if not provided)
            custom_prompt: Custom prompt for Gemini (optional)
            mask_image_url: Optional mask image URL for specific area editing
            user_message: Optional user message for chat history
            image_path_override: Optional image path to use instead of session's stored image
        
        Returns:
            VirtualStagingResponse with unsaved working image, or None if failed
        """
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"Session {session_id} not found")
                return None
            
            # Determine which image to use based on image_index
            # Validate image_index
            if image_index < 0 or image_index >= len(session.panoramic_images):
                print(f"Error: Invalid image_index {image_index}. Available: 0-{len(session.panoramic_images)-1}")
                return None
            
            # Get the image to generate on:
            # If there's a working version for this index, use it (continue editing)
            # Otherwise, use the panoramic image at this index (start fresh)
            if image_index in session.current_image_urls and session.current_image_urls[image_index]:
                # Continue generating on the unsaved working version for this index
                image_url = session.current_image_urls[image_index]
                print(f"[STAGING] Generating on unsaved working version for index {image_index}")
            else:
                # Start fresh generation on this index's panoramic image (original or previously saved)
                image_url = session.panoramic_images[image_index]
                print(f"[STAGING] Generating on panoramic image at index {image_index}")
            
            # Update current index being worked on
            session.current_image_index = image_index
            
            # Validate and prepare image for processing
            if not image_url:
                print(f"Error: No image URL found for session {session_id}")
                return None
            
            # If it's an S3 URL, we'll pass it to gemini_service which will download it
            # If it's a local path (for backward compatibility), validate it exists
            if not (image_url.startswith('http://') or image_url.startswith('https://')):
                # Local path - check if it exists (backward compatibility)
                if not os.path.exists(image_url):
                    print(f"Error: Local image not found: {image_url}")
                    return None
                print(f"[STAGING] Using local image: {image_url}")
            else:
                print(f"[STAGING] Using S3 image URL: {image_url}")
            
            # Note: image_url is now guaranteed to be valid (either existing local path or S3 URL)
            
            # Use provided parameters or fall back to session parameters
            params = staging_parameters or session.current_parameters
            
            # Build prompt - enhance if mask is provided
            if custom_prompt:
                prompt = custom_prompt
                # If mask is provided, enhance the custom prompt with mask-specific context
                if mask_image_url:
                    prompt = f"{prompt}\n\nMASK IMAGE INSTRUCTION:\nThe mask image shows a specific region of interest overlaid on the original room image. Use ONLY the mask to identify WHERE to apply changes - disregard the mask image's visual content itself. Apply your staging modifications ONLY to the region indicated by the mask while maintaining the ORIGINAL IMAGE FORMAT. The output must preserve the room layout, camera angle, and architecture of the original image."
            elif params:
                base_prompt = build_staging_prompt(
                    role=params.role,
                    style=params.style,
                    furniture_style=params.furniture_style,
                    color_scheme=params.color_scheme,
                    specific_request=params.specific_requests
                )
                
                # Add instruction to maintain original room format and structure
                format_preservation = "\n\nIMPORTANT FORMAT PRESERVATION:\nMaintain the exact layout, camera angle, and room structure of the original image. Only modify the staging elements (furniture, decor, colors) while keeping the architectural elements, walls, windows, doors, and spatial arrangement identical. The staging should feel like furniture and decor adjustments to the SAME room."
                base_prompt = f"{base_prompt}{format_preservation}"
                
                # If mask is provided, add specific instructions about the masked region
                if mask_image_url:
                    prompt = f"{base_prompt}\n\nMASK IMAGE INSTRUCTION:\nThe mask image shows a specific region of interest overlaid on the original room image. Use ONLY the mask to identify WHERE to apply changes - disregard the mask image's visual content itself. Focus your design modifications ONLY on the area indicated by the mask. The masked area should receive the full attention of the styling changes. The output must maintain the ORIGINAL IMAGE FORMAT - preserve the room layout, camera angle, and architecture exactly as shown in the first image."
                else:
                    prompt = base_prompt
            else:
                return None

            print(F"PROMPT GENERATED: {prompt}...")
            # Print the full prompt for debugging
            print(f"\n[STAGING] ========== FULL PROMPT FOR SESSION {session_id} ==========")
            print(f"{prompt}")
            print(f"[STAGING] ========== END PROMPT ==========\n")
            
            # Generate image using Gemini with the specific panoramic image at image_index
            generated_image_bytes = self.gemini_service.generate_image_from_image(
                model=self.gemini_model,
                prompt=prompt,
                session=None,  # Don't pass session - use specific image_url instead
                image_path=image_url,  # Use the specific panoramic image at this index
                mask_image_path=mask_image_url
            )
            
            if not generated_image_bytes:
                print(f"Failed to generate image for session {session_id}")
                return None
            
            # Upload generated image to S3 (working version - not yet saved permanently)
            upload_result = self.aws_service.upload_bytes(
                image_bytes=generated_image_bytes,
                filename=f"generated_{session_id}_{image_index}.png",
                folder=f"staging/{session_id}",
                content_type="image/png"
            )
            
            if not upload_result.get("success"):
                print(f"Failed to upload generated image to S3: {upload_result.get('error')}")
                return None
            
            print(f"[STAGING] Uploaded generated image to S3: {upload_result['url']}")
            
            # Store in session as unsaved working version for this index
            session.current_image_urls[image_index] = upload_result["url"]
            session.current_image_path = None  # No longer using local paths
            session.current_image_key = upload_result["key"]
            session.current_image_url = upload_result["url"]
            session.current_parameters = params
            session.current_prompt = prompt
            session.updated_at = datetime.utcnow()
            
            # Update panoramic_images at the current index with the latest generated S3 URL
            if image_index < len(session.panoramic_images):
                session.panoramic_images[image_index] = upload_result["url"]
                print(f"[STAGING] Updated panoramic_images[{image_index}] with generated image: {upload_result['url']}")
            
            # Add to generation history
            session.generation_history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "image_key": session.current_image_key,
                "image_index": image_index,
                "prompt": prompt,
                "parameters": params.model_dump() if params else None,
                "saved": False
            })
            
            self.repository.update_session(session)
            
            # Persist initial message to chat history
            if session.chat_history_id:
                # Add user message if provided
                if user_message:
                    self.chat_history_service.add_user_message(
                        history_id=session.chat_history_id,
                        message_id=f"msg_{uuid.uuid4().hex[:12]}",
                        content=user_message,
                        refinement_iteration=1
                    )
                
                # Add assistant message with the staging prompt and parameters
                self.chat_history_service.add_assistant_message(
                    history_id=session.chat_history_id,
                    message_id=f"msg_{uuid.uuid4().hex[:12]}",
                    content=f"Generated initial virtual staging with the specified parameters",
                    refinement_iteration=1,
                    staging_parameters=params.model_dump() if params else None
                )
                
                print(f"[STAGING] Chat history updated for session {session_id}")
            
            # Build response with S3 URL
            metadata = StagingMetadata(
                session_id=session_id,
                property_id=session.property_id,
                specific_request=params.specific_requests if params else None,
                created_at=session.created_at,
                updated_at=datetime.utcnow(),
                completed_at=session.completed_at
            )
            
            return VirtualStagingResponse(
                image_url=upload_result["url"],  # Use S3 URL instead of local base64
                metadata=metadata,
                prompt_used=prompt,
                furniture_list=None,
                can_revert=False  # No versions to revert to
            )
        
        except Exception as e:
            print(f"Error generating staging: {str(e)}")
            return None
    
    def save_change(self, session_id: str) -> Optional[SaveChangeResponse]:
        """
        Save the current working image to the session.
        Updates the panoramic_images array at the current index with the generated image URL.
        
        Args:
            session_id: Session ID
        
        Returns:
            SaveChangeResponse with success status, or None if failed
        """
        try:
            session = self.get_session(session_id)
            if not session:
                print(f"Session {session_id} not found")
                return None
            
            # Check if there's a current working image (S3 URL)
            if not session.current_image_url:
                print(f"No working image to save for session {session_id}")
                return None
            
            now = datetime.utcnow()
            
            # Update the panoramic image at current index with the current URL
            if session.current_image_index < len(session.panoramic_images):
                session.panoramic_images[session.current_image_index] = session.current_image_url
                print(f"[SAVE] Updated panoramic_images[{session.current_image_index}] with: {session.current_image_url}")
                
                # Clear the working version for this index
                if session.current_image_index in session.current_image_urls:
                    del session.current_image_urls[session.current_image_index]
                    print(f"[SAVE] Cleared working version for index {session.current_image_index}")
            
            # Update generation history
            if session.generation_history:
                session.generation_history[-1]["saved"] = True
                session.generation_history[-1]["saved_at"] = now.isoformat()
                session.generation_history[-1]["aws_key"] = session.current_image_key
                session.generation_history[-1]["aws_url"] = session.current_image_url
            
            session.updated_at = now
            
            # Update session
            self.repository.update_session(session)
            
            return SaveChangeResponse(
                success=True,
                message="Changes saved successfully",
                image_url=session.current_image_url,
                saved_at=now
            )
        
        except Exception as e:
            print(f"Error saving change: {str(e)}")
            return SaveChangeResponse(
                success=False,
                version=0,
                message=f"Error saving change: {str(e)}",
                image_url="",
                saved_at=datetime.utcnow()
            )
    
    def revert_change(self, session_id: str, version_to_revert_to: int) -> Optional[RevertChangeResponse]:
        """
        Revert is not supported since versioning is disabled.
        
        Args:
            session_id: Session ID
            version_to_revert_to: Version number (ignored)
        
        Returns:
            RevertChangeResponse with failure status
        """
        return RevertChangeResponse(
            success=False,
            version=1,
            message="Revert not supported - versioning is disabled",
            image_url="",
            reverted_at=datetime.utcnow()
        )
    
    def get_version_history(self, session_id: str) -> Optional[VersionHistoryResponse]:
        """
        Get version history for a session (returns empty since versioning is disabled)
        
        Args:
            session_id: Session ID
        
        Returns:
            VersionHistoryResponse with no versions
        """
        try:
            session = self.get_session(session_id)
            if not session:
                return None
            
            return VersionHistoryResponse(
                session_id=session_id,
                total_versions=0,
                current_version=1,
                has_unsaved_changes=session.current_image_url is not None,
                versions=[]
            )
        
        except Exception as e:
            print(f"Error getting version history: {str(e)}")
            return None
    
    def get_session(self, session_id: str) -> Optional[VirtualStaging]:
        """Get staging session by ID"""
        return self.repository.get_session(session_id)
    
    def get_sessions_by_property(self, property_id: str) -> List[Tuple[str, VirtualStaging]]:
        """Get all sessions for a property"""
        return self.repository.get_sessions_by_property(property_id)
    
    def get_panoramic_images_by_property(self, property_id: str) -> Optional[Dict[str, Any]]:
        """
        Get panoramic images for a property from the most recent virtual staging session
        
        Args:
            property_id: Property ID
            
        Returns:
            Dict with session_id and panoramic_images, or None if no session found
        """
        sessions = self.get_sessions_by_property(property_id)
        if not sessions:
            return None
            
        # Get the most recent session (assuming sessions are returned in some order, 
        # or we can sort by created_at if needed)
        session_id, session = sessions[0]  # For now, just take the first one
        
        return {
            'session_id': session_id,
            'panoramic_images': session.panoramic_images
        }
    
    def get_sessions_by_user(self, user_id: int) -> List[Tuple[str, VirtualStaging]]:
        """Get all sessions for a user"""
        return self.repository.get_sessions_by_user(user_id)
    
    def get_session_response(self, session_id: str) -> Optional[StagingSessionResponse]:
        """
        Get staging session as API response with all metadata
        """
        try:
            session = self.get_session(session_id)
            if not session:
                return None
            
            # Get panoramic images from the property
            panoramic_images = []
            try:
                from service.property_service import PropertyService
                property_service = PropertyService()
                property_obj = property_service.get_property(session.property_id)
                if property_obj:
                    panoramic_images = [
                        {
                            'id': img.id,
                            'url': img.url,
                            'filename': img.filename,
                            'imageType': img.imageType
                        }
                        for img in property_obj.images 
                        if img.imageType == "panoramic"
                    ]
                    
                    # Override URLs with latest staged versions from session.panoramic_images
                    for idx, staged_url in enumerate(session.panoramic_images):
                        if idx < len(panoramic_images) and staged_url:
                            panoramic_images[idx]['url'] = staged_url
                            print(f"[RESPONSE] Updated panoramic_images[{idx}] URL to staged version: {staged_url}")
                            
            except Exception as e:
                print(f"Warning: Could not load panoramic images for session {session_id}: {str(e)}")
            
            params_dict = session.current_parameters.model_dump() if session.current_parameters else {}
            

            response = StagingSessionResponse(
                session_id=session.session_id,
                property_id=session.property_id,
                original_image_url=session.original_image_url,
                current_image_url=session.current_image_url,
                panoramic_images=panoramic_images,
                staging_parameters=params_dict,
                has_unsaved_changes=session.current_image_url is not None,
                created_at=session.created_at,
                updated_at=session.updated_at,
                completed_at=session.completed_at,
                error_message=session.error_message
            )
            
            return response
        
        except Exception as e:
            print(f"Error getting session response: {str(e)}")
            return None
    
    def refine_staging(self,
                      session_id: str,
                      new_staging_parameters: StagingParameters,
                      user_message: Optional[str] = None,
                      mask_image_url: Optional[str] = None) -> Optional[RefinementResponse]:
        """
        Refine existing staging with new parameters.
        Creates a new unsaved working version and persists to chat history.
        
        Args:
            session_id: Session ID to refine
            new_staging_parameters: Updated staging parameters
            user_message: Optional user message for chat history
            mask_image_url: Optional mask image URL for specific area editing
        
        Returns:
            RefinementResponse with new unsaved working image, or None if failed
        """
        try:
            session = self.get_session(session_id)
            if not session:
                return None
            
            # Use current image (what's on screen) for refinement
            image_path = session.current_image_path or session.original_image_path
            
            # Validate image path - only validate local paths
            if image_path and not (image_path.startswith('http://') or image_path.startswith('https://')):
                # Local path - check if it exists
                if not os.path.exists(image_path):
                    # Try to reconstruct path from session_id
                    reconstructed_path = str(Path('uploads') / f"original_{session_id}.png")
                    if os.path.exists(reconstructed_path):
                        image_path = reconstructed_path
                        print(f"[REFINE] Using reconstructed path: {reconstructed_path}")
                    else:
                        print(f"Error: Original image not found for session {session_id}")
                        # Don't return None - gemini_service will validate and get from session if needed
                        image_path = None
            
            # Get chat history context
            chat_history_llm_context = None
            if session.chat_history_id:
                chat_history_llm_context = self.chat_history_service.get_llm_context(
                    session.chat_history_id,
                    include_full_history=False,
                    last_n_messages=6
                )
            
            # Build refinement prompt with context
            refinement_context = build_refinement_context(
                previous_parameters=session.current_parameters.model_dump() if session.current_parameters else {},
                new_parameters=new_staging_parameters.model_dump(),
                chat_history=chat_history_llm_context.split('\n') if chat_history_llm_context else []
            )
            
            # Build the new staging prompt
            refinement_prompt = build_staging_prompt(
                role=new_staging_parameters.role,
                style=new_staging_parameters.style,
                furniture_style=new_staging_parameters.furniture_style,
                color_scheme=new_staging_parameters.color_scheme,
                specific_request=new_staging_parameters.specific_requests
            )
            
            # Add instruction to maintain original room format and structure
            format_preservation = "\n\nIMPORTANT FORMAT PRESERVATION:\nMaintain the exact layout, camera angle, and room structure of the original image. Only modify the staging elements (furniture, decor, colors) while keeping the architectural elements, walls, windows, doors, and spatial arrangement identical to the original room format. The refinement should feel like staging adjustments to the SAME room, not a different room or angle."
            refinement_prompt = f"{refinement_prompt}{format_preservation}"
            
            # Enhance prompt if mask is provided
            if mask_image_url:
                refinement_prompt = f"{refinement_prompt}\n\nMASK IMAGE INSTRUCTION:\nThe mask image shows a specific region of interest overlaid on the original room image. Use ONLY the mask to identify WHERE to apply changes - disregard the mask image's visual content itself. Focus your refinement modifications ONLY on the area indicated by the mask. The masked area should receive the full attention of the styling changes. The refinement must maintain the ORIGINAL IMAGE FORMAT - preserve the room layout, camera angle, and architecture exactly as shown in the original image, changing only the staging elements in the masked region."
            
            # Add context
            full_refinement_prompt = f"{refinement_context}\n\n{refinement_prompt}"
            
            # Print the full prompt for debugging
            print(f"\n[REFINE] ========== FULL PROMPT FOR SESSION {session_id} ==========")
            print(f"{full_refinement_prompt}")
            print(f"[REFINE] ========== END PROMPT ==========\n")
            
            # Generate refined image using Gemini with session object (will get latest image)
            refined_image_bytes = self.gemini_service.generate_image_from_image(
                model=self.gemini_model,
                prompt=full_refinement_prompt,
                session=session,
                mask_image_path=mask_image_url
            )
            
            if not refined_image_bytes:
                print(f"Failed to generate refined image for session {session_id}")
                return None
            
            # Upload refined image to S3 (working version - not yet permanently saved)
            upload_result = self.aws_service.upload_bytes(
                image_bytes=refined_image_bytes,
                filename=f"refined_{session_id}_{image_index}.png",
                folder=f"staging/{session_id}",
                content_type="image/png"
            )
            
            if not upload_result.get("success"):
                print(f"Failed to upload refined image to S3: {upload_result.get('error')}")
                return None
            
            print(f"[REFINE] Uploaded refined image to S3: {upload_result['url']}")
            
            # Update session with new working version from S3
            session.current_image_path = None  # No longer using local paths
            session.current_image_key = upload_result["key"]
            session.current_image_url = upload_result["url"]
            session.current_parameters = new_staging_parameters
            session.current_prompt = full_refinement_prompt
            session.updated_at = datetime.utcnow()
            
            # Update panoramic_images at the current index with the latest refined S3 URL
            if session.current_image_index < len(session.panoramic_images):
                session.panoramic_images[session.current_image_index] = upload_result["url"]
                print(f"[REFINE] Updated panoramic_images[{session.current_image_index}] with refined image: {upload_result['url']}")
            
            # Add to generation history
            session.generation_history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "image_key": None,
                "image_path": str(local_path),
                "prompt": full_refinement_prompt,
                "parameters": new_staging_parameters.model_dump(),
                "saved": False,
                "type": "refinement"
            })
            
            self.repository.update_session(session)
            
            # Persist messages to chat history
            if session.chat_history_id:
                # Add user message if provided
                if user_message:
                    self.chat_history_service.add_user_message(
                        history_id=session.chat_history_id,
                        message_id=f"msg_{uuid.uuid4().hex[:12]}",
                        content=user_message,
                        refinement_iteration=1
                    )
                
                # Add assistant message with the refinement prompt and parameters
                self.chat_history_service.add_assistant_message(
                    history_id=session.chat_history_id,
                    message_id=f"msg_{uuid.uuid4().hex[:12]}",
                    content=f"Generated refined image with the following adjustments",
                    refinement_iteration=1,
                    staging_parameters=new_staging_parameters.model_dump()
                )
                
                # Increment iteration counter in chat history
                self.chat_history_service.repository.increment_iteration(session.chat_history_id)
                print(f"[REFINE] Chat history updated for session {session_id}")
            
            # Return refined image URL from S3 (instead of base64)
            return RefinementResponse(
                image_url=upload_result["url"],
                updated_at=session.updated_at,
                prompt_used=full_refinement_prompt
            )
        
        except Exception as e:
            print(f"Error refining staging: {str(e)}")
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """Delete staging session, associated chat history, and clean up AWS files"""
        try:
            session = self.get_session(session_id)
            if session:
                # Delete chat history if exists
                if session.chat_history_id:
                    self.chat_history_service.delete_history(session.chat_history_id)
                    print(f"[DELETE] Deleted chat history: {session.chat_history_id}")
                
                # Delete all versions from AWS
                # No versions to delete since versioning is disabled
                
                # Delete current working image
                if session.current_image_key:
                    self.aws_service.delete_file(session.current_image_key)
                
                # Delete original image
                if session.orignal_image_key:
                    self.aws_service.delete_file(session.orignal_image_key)
            
            return self.repository.delete_session(session_id)
        
        except Exception as e:
            print(f"Error deleting session: {str(e)}")
            return False
    
    def _validate_staging(self, session_id: str, property_id: str) -> bool:
        """Validate staging fields"""
        return (
            session_id and session_id.strip() and
            property_id and property_id.strip()
        )



