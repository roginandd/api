from config.gemini_config import get_gemini_client
from typing import Optional, Dict, Any, List
import base64
import os
import io
import json
import uuid
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
import requests
from io import BytesIO
from google.genai import types
from google.genai.types import Tool, FunctionDeclaration, Schema, Type
from repositories.property_repository import PropertyRepository

# Static furniture inventory (placeholder data)
FURNITURE_INVENTORY = [
    {"id": "F001", "name": "Modern Office Chair", "color": "Black", "type": "Chair", "style": "Modern", "material": "Leather"},
    {"id": "F002", "name": "Velvet Lounge Seat", "color": "Red", "type": "Chair", "style": "Contemporary", "material": "Velvet"},
    {"id": "F003", "name": "Oak Dining Table", "color": "Brown", "type": "Table", "style": "Traditional", "material": "Oak"},
    {"id": "F004", "name": "Glass Coffee Table", "color": "Clear", "type": "Table", "style": "Modern", "material": "Glass"},
    {"id": "F005", "name": "L-Shape Sectional Sofa", "color": "Gray", "type": "Sofa", "style": "Contemporary", "material": "Fabric"},
    {"id": "F006", "name": "White Leather Couch", "color": "White", "type": "Sofa", "style": "Modern", "material": "Leather"},
    {"id": "F007", "name": "Wooden Bookshelf", "color": "Walnut", "type": "Storage", "style": "Scandinavian", "material": "Wood"},
    {"id": "F008", "name": "Metal Floor Lamp", "color": "Black", "type": "Lighting", "style": "Industrial", "material": "Metal"},
    {"id": "F009", "name": "Ceramic Table Lamp", "color": "White", "type": "Lighting", "style": "Contemporary", "material": "Ceramic"},
    {"id": "F010", "name": "Industrial Desk", "color": "Black and Brown", "type": "Desk", "style": "Industrial", "material": "Metal and Wood"},
]

furniture = {
    "furniture_id": str,
    "color": str,
    "type": str,
    "price": float,
    "image_url": str,
    "shop_url": str
}


class GeminiService:
    """Service to interact with Gemini API"""

    def __init__(self):
        self.client = get_gemini_client()
        self.repo = PropertyRepository()


    def find_furniture_by_prompt(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Find a furniture item with STRICT validation. 
        It will reject "Brown Santa Claus" but accept "Brown Chair".
        """
        try:
            # STRICTER PROMPT
            search_prompt = f"""
            You are a strict inventory matcher for a furniture store.
            Inventory:
            {json.dumps(FURNITURE_INVENTORY, indent=2)}

            User Request: "{prompt}"

            Instructions:
            1. **Validation Step**: First, analyze if the User Request is actually asking for a piece of furniture that exists in our inventory categories (e.g., Chair, Table, Sofa).
            2. **Rejection Rule**: If the user asks for a person (e.g., "Santa Claus"), an animal, food, or an object NOT in the inventory, return {{"error": "Request is not furniture"}}, EVEN IF the color matches.
            3. **Matching Step**: Only if the object type matches, find the specific item based on color, style, or material.
            4. **Output**: Return ONLY the JSON object of the match, or the error JSON.
            """
            
            # Call Gemini with JSON Mode enabled (No need to parse markdown manually)
            response = self.client.models.generate_content(
                model="gemini-2.5-flash", # or gemini-1.5-flash
                contents=search_prompt,
                config={ 
                        "response_mime_type": "application/json" 
                    }
            )
            
            # Parse result directly
            result = json.loads(response.text)
            
            # Handle the logic
            if "error" in result:
                print(f"[FURNITURE] Blocked invalid request: {result['error']}")
                return None
                
            print(f"[FURNITURE] Found: {result.get('name')} (ID: {result.get('id')})")
            return result

        except Exception as e:
            print(f"[FURNITURE] System Error: {str(e)}")
            return None
    
    def get_furniture_inventory(self) -> List[Dict[str, Any]]:
        """
        Get the complete furniture inventory.
        
        Returns:
            List of all furniture items in the inventory
        """
        return FURNITURE_INVENTORY

    def generate_content(self, model: str, contents: str) -> str:
        """Generate content using Gemini model"""
        response = self.client.models.generate_content(
            model=model,
            contents=contents
        )
        return response.text

    @staticmethod
    def encode_image_to_base64(image_path: str) -> str:
        """
        Read an image file and encode it to base64
        
        Args:
            image_path: Path to the image file or S3 URL
        
        Returns:
            Base64 encoded string of the image
        
        Raises:
            FileNotFoundError: If image file doesn't exist
            IOError: If file cannot be read
        """
        # Check if it's an S3 URL
        if image_path.startswith('http://') or image_path.startswith('https://'):
            # Download from S3
            from service.aws_service import AWSService
            download_result = AWSService.download_image_bytes(image_path)
            if not download_result["success"]:
                raise IOError(f"Failed to download image from S3: {download_result['error']}")
            image_bytes = download_result["bytes"]
        else:
            # Local file
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            with open(image_path, 'rb') as image_file:
                image_bytes = image_file.read()
        
        return base64.standard_b64encode(image_bytes).decode('utf-8')

    @staticmethod
    def apply_staging_filters(image: Image.Image, style: str = "modern") -> Image.Image:
        """
        Apply visual filters to simulate staging (as fallback for image generation)
        This enhances the image to make it look more staged/professional
        """
        try:
            # Create a copy to avoid modifying original
            enhanced = image.copy()
            
            # Enhance colors (saturation)
            color_enhancer = ImageEnhance.Color(enhanced)
            enhanced = color_enhancer.enhance(1.15)  # 15% more saturation
            
            # Enhance contrast
            contrast_enhancer = ImageEnhance.Contrast(enhanced)
            enhanced = contrast_enhancer.enhance(1.1)  # 10% more contrast
            
            # Enhance brightness slightly
            brightness_enhancer = ImageEnhance.Brightness(enhanced)
            enhanced = brightness_enhancer.enhance(1.05)  # 5% brighter
            
            # Apply subtle sharpening
            enhanced = enhanced.filter(ImageFilter.SHARPEN)
            
            print(f"[STAGING] Applied professional staging filters ({style} style)")
            return enhanced
        except Exception as e:
            print(f"[STAGING] Error applying filters: {str(e)}")
            return image

    @staticmethod
    def _generate_image_with_fallback(input_image: Image.Image, style: str = "modern") -> bytes:
        """Generate image bytes with professional enhancement as fallback"""
        enhanced = GeminiService.apply_staging_filters(input_image, style)
        img_io = BytesIO()
        enhanced.save(img_io, format='PNG')
        img_io.seek(0)
        return img_io.getvalue()

    @staticmethod
    def get_image_mime_type(image_path: str) -> str:
        """
        Determine MIME type from image file extension or S3 URL
        
        Args:
            image_path: Path to the image file or S3 URL
        
        Returns:
            MIME type string (e.g., 'image/jpeg', 'image/png')
        """
        # Check if it's an S3 URL
        if image_path.startswith('http://') or image_path.startswith('https://'):
            # Try to get MIME type from URL extension first
            _, ext = os.path.splitext(image_path.lower())
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            # If we can't determine from extension, try to download and check
            if ext == '':
                from service.aws_service import AWSService
                download_result = AWSService.download_image_bytes(image_path)
                if download_result["success"]:
                    mime_type = download_result.get("content_type", "image/png")
            
            return mime_type
        else:
            # Local file - use extension
            _, ext = os.path.splitext(image_path.lower())
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            return mime_types.get(ext, 'image/jpeg')

    def generate_image_from_text(self, model: str, prompt: str) -> Optional[str]:
        """
        Generate an image from text prompt using Gemini
        Returns text response from the model
        
        Args:
            model: Gemini model to use (e.g., "gemini-2.0-flash")
            prompt: Text prompt for image generation
        
        Returns:
            Response text or None if generation fails
        """
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt
            )
            return response.text if hasattr(response, 'text') else None
        except Exception as e:
            print(f"Error generating content: {str(e)}")
            return None

    def generate_image_from_image(self, model: str, prompt: str, session=None, image_path: str = None, mask_image_path: Optional[str] = None) -> Optional[bytes]:
        """
        Generate virtually staged image using gemini-2.5-flash-image
        Native multimodal model that returns both text (reasoning) and image (inline_data)
        
        Args:
            model: Model name (overridden to gemini-2.5-flash-image)
            prompt: Staging parameters (style, furniture, colors, etc)
            session: VirtualStaging session object to get the latest image from (preferred)
            image_path: S3 URL to the input room image - used as fallback if session not provided
            mask_image_path: Optional path to mask image for specifying a specific area/point
        
        Returns:
            Image bytes (PNG) of the virtually staged room
        
        Raises:
            FileNotFoundError: If image file doesn't exist
            Exception: If API call fails
        """
        try:
            # Determine image path - get from session if provided, otherwise use image_path parameter
            image_to_use = None
            
            if session:
                # Get the latest image from session (prefer current_image_path/url, fallback to original)
                if session.current_image_path:
                    image_to_use = session.current_image_path
                    print(f"[STAGING] Using current image from session: {session.current_image_path}")
                elif session.current_image_url:
                    image_to_use = session.current_image_url
                    print(f"[STAGING] Using current image URL from session: {session.current_image_url[:50]}...")
                elif session.original_image_path:
                    image_to_use = session.original_image_path
                    print(f"[STAGING] Using original image from session: {session.original_image_path}")
                elif session.original_image_url:
                    image_to_use = session.original_image_url
                    print(f"[STAGING] Using original image URL from session: {session.original_image_url[:50]}...")
                else:
                    print(f"[STAGING] WARNING: Session has no image paths set")
                    print(f"  Session current_image_path: {session.current_image_path}")
                    print(f"  Session current_image_url: {session.current_image_url}")
                    print(f"  Session original_image_path: {session.original_image_path}")
                    print(f"  Session original_image_url: {session.original_image_url}")
            else:
                # Fallback to image_path parameter if no session provided
                image_to_use = image_path
                if image_to_use:
                    print(f"[STAGING] Using image_path parameter: {image_to_use}")
            
            # Validate image_path is provided
            if not image_to_use:
                error_msg = "Image path is required. Either provide a session object with images or image_path parameter"
                print(f"[STAGING] ❌ {error_msg}")
                raise FileNotFoundError(error_msg)
            
            # Load image from S3 (remove local file dependency for deployment)
            try:
                if not isinstance(image_to_use, str) or not (image_to_use.startswith('http://') or image_to_use.startswith('https://')):
                    raise ValueError(f"Image must be an S3 URL for deployment. Received: {image_to_use}")
                
                # Download from S3 URL
                response = requests.get(image_to_use, timeout=30)
                response.raise_for_status()
                input_image = Image.open(BytesIO(response.content))
                print(f"[STAGING] Downloaded image from S3: {image_to_use[:50]}...")
            except Exception as e:
                print(f"[STAGING] ❌ Error loading image from S3: {str(e)}")
                raise
            
            # Build comprehensive staging prompt
            staging_prompt = f"""
You are VistaAI, an elite Interior Design Architect and Virtual Staging Specialist with an obsessive eye for photorealism.

### INPUT CONTEXT
User Request: "{prompt}"
**Image Type:** Equirectangular 360° Panorama (Spherical Projection).

### INSTRUCTIONS FOR TRANSFORMATION
You must interpret the User Request not just literally, but architecturally.
If the request is vague (e.g., "make it blue"), you must infer the most sophisticated, high-end interpretation (e.g., "Navy Blue matte finish with velvet textures").

1. **Strict Isolation:** Identify ONLY the specific elements mentioned in the User Request. Do NOT touch the flooring, ceiling, structural beams, or unmentioned furniture unless explicitly asked.
2. **Material Physics:** Apply realistic texture mapping. If changing a door, specify the wood grain, gloss level, and hardware reflection. If changing a wall, define the paint finish (eggshell, matte, venetian plaster).
3. **Lighting Integration:** Any color or furniture change must interact realistically with existing light sources. Calculate global illumination, cast shadows, and ambient occlusion accurately.
4. **Resolution & Detail:** The output must be indistinguishable from a high-resolution photograph (8k, hyper-detailed).

### EXECUTION STEPS
1. **Analyze:** Scan the original room for lighting direction, perspective, and identify the Zenith (top) and Nadir (bottom) of the spherical projection.
2. **Expand:** Translate the vague User Request into technical design specifications (e.g., "change walls to green" -> "Sage Green #77896C paint with a matte finish").
3. **Generate:** Apply the changes while strictly masking unaltered areas to preserve original integrity.

### MANDATORY CONSTRAINTS
* **360° Continuity:** This is a spherical image. Ensure seamless wrapping between the left and right edges.
* **Nadir/Bottom Preservation:** Do NOT place complex geometry or furniture legs directly on the extreme bottom edge pixels unless they are correctly warped for spherical projection. Avoid "smearing" artifacts at the bottom pole.
* **ZERO Geometric Distortion:** The perspective, straight lines, and proportions of the original room architecture must remain flawless. Do not warp walls or furniture.
* **Format Preservation:** The output image must exactly maintain the original input's aspect ratio, pixel dimensions, and composition. No cropping.
* NO artifacts, smudges, or AI hallucinations.
* NO cartoonish or over-saturated colors; use commercially viable, real-world palettes.

**Action:** Transform the image now with meticulous adherence to spherical projection and photorealism.
"""
            
            print("[STAGING] Sending to gemini-2.5-flash-image for transformation...")
            
            # Prepare content list with main image
            contents = [staging_prompt, input_image]
            
            # Add mask image if provided for specific area guidance
            if mask_image_path and isinstance(mask_image_path, str) and len(mask_image_path) > 0:
                mask_image = None
                if mask_image_path.startswith('http://') or mask_image_path.startswith('https://'):
                    # Download mask from URL
                    response = requests.get(mask_image_path)
                    response.raise_for_status()
                    mask_image = Image.open(BytesIO(response.content))
                    print(f"[STAGING] Downloaded mask image from URL")
                elif os.path.exists(mask_image_path):
                    mask_image = Image.open(mask_image_path)
                    print(f"[STAGING] Using mask image to focus on specific area: {mask_image_path}")
                
                if mask_image:
                    mask_instruction = "\n\nFocus the transformation primarily on the area highlighted in this mask image:"
                    contents = [staging_prompt + mask_instruction, input_image, mask_image]
            
            # Native multimodal call - no response_modalities needed
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=contents
            )
            
            # Extract both text (reasoning) and image (transformed room)
            image_bytes = None
            model_comment = None
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    
                    # Extract text explanation from model
                    if hasattr(part, 'text') and part.text:
                        model_comment = part.text
                        print(f"[STAGING] Model: {model_comment[:100]}...")
                    
                    # Extract generated image
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_bytes = part.inline_data.data
                        print(f"[STAGING] ✅ Image generated! Size: {len(image_bytes)} bytes")
            
            if image_bytes:
                return image_bytes
            else:
                print("[STAGING] ⚠️  No image in response - model may have only provided text/analysis")
                print("[STAGING] 📋 Model comment:", model_comment[:200] if model_comment else "None")
                print("[STAGING] 💡 Gemini-2.5-flash-image is designed for image analysis, not generation")
                print("[STAGING] ℹ️  Applying professional staging filters as fallback...")
                
                # Fallback: Return the input image with professional enhancement filters
                fallback_bytes = self._generate_image_with_fallback(input_image, style="modern")
                print(f"[STAGING] ✅ Returning enhanced image with professional filters: {len(fallback_bytes)} bytes")
                return fallback_bytes
            
        except FileNotFoundError as e:
            print(f"[STAGING] ❌ Image file error: {str(e)}")
            raise
        except Exception as e:
            print(f"[STAGING] ❌ Error during staging: {str(e)}")
            raise

    def chat_with_mark(self, user_query: str, history: list = None):
        """
        Production-ready chatbot logic with Property Search Tool.
        """
        if history is None:
            history = []

        # 1. Define the Property Search Tool
        search_tool = Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="search_properties",
                    description="Search for properties based on user criteria like price, location, type, and amenities.",
                    parameters=Schema(
                        type=Type.OBJECT,
                        properties={
                            "keyword": Schema(
                                type=Type.STRING, 
                                description="Fuzzy search for address, name, or description"
                            ),
                            "propertyType": Schema(
                                type=Type.STRING,
                                description="Type of property",
                                enum=["House", "Condo", "Apartment", "Lot", "Commercial"]
                            ),
                            "listingType": Schema(
                                type=Type.STRING,
                                description="Listing category",
                                enum=["For Sale", "For Rent", "For Lease"]
                            ),
                            "minPrice": Schema(type=Type.NUMBER, description="Minimum price budget"),
                            "maxPrice": Schema(type=Type.NUMBER, description="Maximum price budget"),
                            "bedrooms": Schema(type=Type.NUMBER, description="Minimum number of bedrooms"),
                            "bathrooms": Schema(type=Type.NUMBER, description="Minimum number of bathrooms"),
                            "priceNegotiable": Schema(type=Type.BOOLEAN, description="If price is negotiable"),
                            "parkingAvailable": Schema(type=Type.BOOLEAN, description="If parking is required"),
                            "petPolicy": Schema(
                                type=Type.STRING,
                                enum=["Pets allowed", "No pets allowed", "Pets allowed with restrictions"]
                            ),
                            "amenities": Schema(
                                type=Type.ARRAY,
                                items=Schema(type=Type.STRING),
                                description="List of required amenities (e.g., 'Swimming Pool', 'Gym')"
                            ),
                            "interiorFeatures": Schema(
                                type=Type.ARRAY,
                                items=Schema(type=Type.STRING),
                                description="Interior features (e.g. 'Marble Floors')"
                            ),
                            "utilities": Schema(
                                type=Type.ARRAY,
                                items=Schema(type=Type.STRING),
                                description="Utilities (e.g. 'Internet readiness')"
                            ),
                            "furnishing": Schema(
                                type=Type.STRING,
                                description="Furnishing status",
                                enum=["Fully furnished", "Semi-furnished", "Unfurnished"]
                            ),
                            "storeys": Schema(
                                type=Type.NUMBER, 
                                description="Minimum number of storeys/floors"
                            )
                        },
                    )
                )
            ]
        )

        # 2. Define the System Instruction
        system_instruction = """
        You are Mark, the AI Real Estate Assistant for Vista.
        
        ### YOUR DATA CONTEXT
        You have access to a database of properties with the following schema. 
        Use these field definitions and Enums to understand user requests.

        {
            "property": {
                "name": "String",
                "description": "String",
                "propertyType": "Enum: ['House', 'Condo', 'Apartment', 'Lot', 'Commercial']",
                "listingType": "Enum: ['For Sale', 'For Rent', 'For Lease']",
                "price": "Number (Float)",
                "priceNegotiable": "Boolean",
                "address": "String (City, Province, Street)",
                "floorArea": "Number (sqm)",
                "lotArea": "Number (sqm)",
                "bedrooms": "Number",
                "bathrooms": "Number",
                "storeys": "Number",
                "furnishing": "Enum: ['Fully furnished', 'Semi-furnished', 'Unfurnished']",
                "condition": "Enum: ['New', 'Well-maintained', 'Renovated', 'Needs repair']",
                "parkingAvailable": "Boolean",
                "parkingSlots": "Number",
                "availabilityDate": "Date (YYYY-MM-DD)",
                "petPolicy": "Enum: ['Pets allowed', 'No pets allowed', 'Pets allowed with restrictions', 'Pets allowed with deposit', 'Service animals only']",
                "smokingPolicy": "Enum: ['No smoking allowed', 'Smoking allowed outdoors only', 'Smoking allowed in designated areas', 'No restrictions']",
                "amenities": "Array of Strings: ['Swimming Pool', 'Gym', 'Security (24/7)', 'Garden', 'Playground', 'Elevator', 'Generator', 'Clubhouse']",
                "interiorFeatures": "Array of Strings: ['Air-conditioning', 'Built-in cabinets', 'Balcony', 'Kitchen appliances', 'Walk-in closet', 'Smart home system', 'Marble Floors', 'Floor-to-Ceiling Windows']",
                "utilities": "Array of Strings: ['Water', 'Electricity', 'Internet readiness', 'Gas line', 'Sewage system']",
                "ownershipStatus": "Enum: ['Free and Clear', 'Mortgaged', 'Under Foreclosure', 'Bank Owned', 'Government Owned', 'Private Owned']",
                "terms": "Array of Strings (e.g., 'No smoking allowed', 'Minimum 1 year lease')",
                "agentName": "String",
                "developerName": "String"
            }
        }

        ### RULES
        1. If the user asks to find, search, or look for a property, CALL the `search_properties` function with the relevant filters.
        2. Do NOT hallucinate listings. If you are not calling the function, only discuss Vista features or general real estate advice.
        3. If the user mentions "good internet", map it to "utilities" containing "Internet readiness".
        4. If the user mentions "cheap" or "affordable", ask for a specific price range before searching.
        5. Be concise.
        """

        current_user_message = {"role": "user", "parts": [{"text": user_query}]}
        full_contents = history + [current_user_message]

        try:
            # 3. Call Gemini with Tools
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                    tools=[search_tool],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True 
                    )
                )
            )

            # 4. Handle Function Calls
            if response.function_calls:
                function_call = response.function_calls[0]
                if function_call.name == "search_properties":
                    filters = function_call.args
                    print(f"🔍 AI extracted filters: {filters}")
                    
                    # --- REAL DB LOOKUP ---
                    # Call the repository directly using the filters from AI
                    properties_found = self.repo.search_properties(filters)
                    
                    if not properties_found:
                        return "I searched for properties matching those criteria, but I couldn't find any listings right now."

                    # Return structured data for the Controller to handle
                    return {
                        "type": "search_results",
                        "data": properties_found,
                        "text": f"I found {len(properties_found)} properties that match your criteria:"
                    }

            return response.text

        except Exception as e:
            print(f"Chat Error: {str(e)}")
            return "I'm having trouble connecting right now. Let's try again in a moment."