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
    
    def extract_furniture_from_the_image(self, session_id: str, image_index: int, budget: Optional[str] = None, furniture_items: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Extract furniture from an image and provide shopping recommendations.
        
        This function:
        1. Retrieves the virtual staging session and image
        2. Analyzes the image to identify furniture items
        3. Searches for top 3 real products per furniture type within budget
        4. Returns recommendations with exact prices and real retailer links
        
        Args:
            session_id: Virtual staging session ID
            image_index: Index of the panoramic image to analyze (0-based)
            budget: Optional total budget limit (e.g., "$2,000")
            furniture_items: Optional list of specific furniture types to search for
        
        Returns:
            Dict with schema:
            {
                "total_budget_limit": "string",
                "furniture_items": [
                    {
                        "item_type": "string",
                        "top_3_suggestions": [
                            {
                                "product_name": "string",
                                "retailer": "string",
                                "price": "string",
                                "link": "string",
                                "why_it_is_a_pick": "string"
                            }
                        ]
                    }
                ]
            }
        """
        try:
            from repositories.virtual_staging_repository import VirtualStagingRepository
            
            # Retrieve the session
            repository = VirtualStagingRepository()
            session = repository.get_session(session_id)
            
            if not session:
                print(f"[FURNITURE] ❌ Session not found: {session_id}")
                return {
                    "error": f"Session {session_id} not found",
                    "total_budget_limit": budget or "Not specified",
                    "furniture_items": []
                }
            
            # Get the image URL for the specified index
            image_url = None
            
            # Check current_image_urls dictionary first (working images)
            if image_index in session.current_image_urls:
                image_url = session.current_image_urls[image_index]
                print(f"[FURNITURE] Using current image at index {image_index}: {image_url[:50]}...")
            # Fallback to panoramic_images list
            elif image_index < len(session.panoramic_images):
                image_url = session.panoramic_images[image_index]
                print(f"[FURNITURE] Using panoramic image at index {image_index}: {image_url[:50]}...")
            else:
                print(f"[FURNITURE] ❌ Image index {image_index} not found in session")
                return {
                    "error": f"Image index {image_index} not found in session",
                    "total_budget_limit": budget or "Not specified",
                    "furniture_items": []
                }
            
            # Encode image to base64 for Gemini API
            image_base64 = self.encode_image_to_base64(image_url)
            mime_type = self.get_image_mime_type(image_url)
            
            # Clean and validate budget
            clean_budget = None
            if budget:
                # Remove commas and extra spaces, convert to number
                clean_budget = budget.replace(',', '').replace(' ', '').strip()
                try:
                    # Try to convert to float to validate it's a number
                    float(clean_budget)
                except ValueError:
                    print(f"[FURNITURE] ⚠️  Invalid budget format: {budget}, using None")
                    clean_budget = None
            
            # Validate that we have valid image data
            if not image_base64 or not isinstance(image_base64, str) or len(image_base64.strip()) == 0:
                print(f"[FURNITURE] ❌ Invalid image data: base64 is empty or not a string")
                return {
                    "error": "Failed to encode image for analysis",
                    "total_budget_limit": budget or "Not specified",
                    "furniture_items": []
                }
            
            # Validate mime_type
            if not mime_type or not isinstance(mime_type, str) or len(mime_type.strip()) == 0:
                print(f"[FURNITURE] ❌ Invalid mime_type: {mime_type}")
                mime_type = "image/jpeg"  # fallback
            
            # Single comprehensive prompt to analyze furniture and find real products
            system_prompt = f"""
                You are an expert Interior Sourcing Assistant specializing in the Philippine furniture market. Your goal is to analyze an uploaded image, identify furniture items, and generate dynamic search URLs for local shops based on a user-provided budget.

                ### **CORE CAPABILITIES**
                1. **Visual Analysis:** Extract every furniture item seen in the image (make it general) and disregard the color.
                2. **Budget Allocation:** Dynamically split the user's total budget across the identified items. Ensure the total of the 'highest' (.lte) values does not exceed the user's total budget.
                3. **URL Engineering:** Construct search URLs for each item using these specific templates:
                    * **Mandaue Foam:** `https://mandauefoam.ph/search?q={{type}}&type=product&sort_by=relevance&filter.v.price.gte={{lowest}}&filter.v.price.lte={{highest}}`
                    * **SM Home:** `https://smhome.ph/search?q={{type}}&type=product&sort_by=relevance&filter.v.price.gte={{lowest}}&filter.v.price.lte={{highest}}`
                    * **Uratex:** `https://uratex.com.ph/search?type=product&q={{type}}&filter.v.price.lte={{highest}}&filter.v.price.gte={{lowest}}`


                ### **MAPPING RULES**
                * **q**: Set to the name of the furniture type (e.g., "Sofa").
                * **.gte (lowest)**: The minimum price for that item's budget bracket.
                * **.lte (highest)**: The maximum price for that item's budget bracket.

                ### **RESPONSE FORMAT**
                You MUST respond strictly in JSON format. Do not include markdown prose outside of the JSON block. Do not include a "why_this_pick" or "reasoning" field.

                ```json
                {{
                "total_budget": {clean_budget if clean_budget else 0},
                "currency": "PHP",
                "extracted_furniture": [
                    {{
                    "item_type": "[Name of Furniture]",
                    "description": "[Brief visual description]",
                    "top_3_search_links": [
                        {{
                        "shop": "Mandaue Foam",
                        "price_bracket": "[lowest] - [highest]",
                        "search_url": "[Generated URL]"
                        }},
                        {{
                        "shop": "SM Home",
                        "price_bracket": "[lowest] - [highest]",
                        "search_url": "[Generated URL]"
                        }},
                        {{
                        "shop": "Uratex",
                        "price_bracket": "[lowest] - [highest]",
                        "search_url": "[Generated URL]"
                        }}
                    ]
                    }}
                ],
                "budget_summary": {{
                    "total_allocation": {clean_budget if clean_budget else 0},
                    "strategy": "[Explanation of how the budget was split]"
                }}
                }}

                TOTAL ALLOCATION MUST BE WITHIN THE USER'S BUDGET OF {clean_budget if clean_budget else 'Not Specified'}.
                """
            
            print("[FURNITURE] 📸 Analyzing room and searching for furniture recommendations...")
            print(f"[FURNITURE] Using image URL: {image_url[:50]}...")
            print(f"[FURNITURE] Using budget: {budget} (cleaned: {clean_budget})")
            print(f"[FURNITURE] Base64 length: {len(image_base64) if image_base64 else 0}")
            print(f"[FURNITURE] MIME type: {mime_type}")
            
            # Call Gemini with Google Search grounding for real product links

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                # --- ADD THINKING CONFIG HERE ---
            )
            # Call Gemini to analyze furniture in the image
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "text": system_prompt
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ],
                config=config
            )
            result = json.loads(response.text)
            
            print(f"[FURNITURE] ✅ Successfully extracted furniture from image")
            if "furniture_items" in result:
                print(f"[FURNITURE] 📊 Found {len(result['furniture_items'])} furniture types")
            
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"[FURNITURE] ⚠️  Failed to parse response: {str(e)}")
            return {
                "error": f"Invalid JSON response from Gemini: {str(e)}",
                "total_budget_limit": budget or "Not specified",
                "furniture_items": []
            }
        except Exception as e:
            print(f"[FURNITURE] ❌ Error extracting furniture: {str(e)}")
            return {
                "error": str(e),
                "total_budget_limit": budget or "Not specified",
                "furniture_items": []
            }


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
        For context here is Vista's full features:
        1. AI-Driven Custom Virtual Staging 
            • Instantly transform a property’s interior using AI—no physical staging, renovations, or redesign 
            costs. 
            • Modify furniture, wall art, layouts, color palettes, lighting, ambience, and overall “feel” of the 
            space. 
            • Changes are visualized directly on 360° panoramic images, helping users imagine the property as 
            their own. 
            • Eliminates the need for expensive physical staging while increasing emotional connection to the 
            property. 
        Echo – Voice-Driven Staging Partner 
            • An AI assistant users can talk to while viewing the property in VR or 360° mode. 
            • Users can say commands like: 
                o “Change the sofa to a modern style” 
                o “Make the room feel warmer” 
                o “Add minimalist paintings” 
            • Echo interprets voice commands and updates the space in real time, creating a hands-free, 
            immersive experience. 
        2. 360° Voice-Controlled VR Property Tours 
            • Provides full 360° panoramic tours of every part of the property. 
            • Works in multiple modes: 
                o VR Box Mode: Insert a smartphone into an affordable VR box for an immersive 
                walkthrough. 
                o Remote Viewing: Buyers can explore properties from home if they own a VR box. 
                o Standard 360° Mode: Users without VR hardware can still explore via touch and swipe, 
                similar to Google Street View. 
        • Reduces the need for repeated physical visits, saving time for both sellers and buyers. 
        3. Interactive Real Estate Marketplace (Mark – AI Chatbot Support) 
            • An AI chatbot embedded directly into the property listing experience. 
            • Users can ask natural questions such as: 
                o “How old is the property?” 
                o “Is this area flood-safe?” 
                o “What schools are nearby?” 
                o “Is the price negotiable?” 
            • Removes friction by replacing manual scrolling and information hunting with instant answers. 
            • Keeps users engaged and informed without overwhelming them. 
        4. Furniture & Upgrade Cost Approximation 
            • As users customize interiors, AI automatically estimates: 
                o Furniture prices 
                o Renovation or upgrade costs 
                o Budget ranges based on real online listings 
            • Suggests where items can be purchased and provides realistic cost expectations. 
            • Helps buyers validate ideas before committing—reducing financial uncertainty and regret. 

        
        STRICT RULES:
        - ONLY discuss this property, real estate trends, or Vista app features.
        - You can discuss about general real estate advice, market trends, or home buying tips.
        - If the user is rude or asks unrelated questions (politics, games, etc.), 
          redirect them: "I'm here to help with your property search. Let's focus on Vista." and append with suggestion messages.
        - Use the provided context for accurate answers. If data is missing, say so.
        - Do not overwhelm; keep answers under 3 sentences unless asked for details.
        
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
        5. If the user looks for properties in a location, use the "keyword" filter for fuzzy matching. 
        6. Be concise.
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

    def get_property_summary(self, property_id: str, history: list = None):
        """
        Fetches property details, injects them into context, and generates a summary.
        Returns the summary text and the raw property JSON object.
        """
        if history is None:
            history = []

        # 1. Fetch real data
        property_data = self.repo.get_property(property_id)
        if not property_data:
            return {
                "summary": "I'm sorry, I can't seem to load the details for that property right now.",
                "property": None
            }

        # 2. Serialize data for the AI prompt (Internal String)
        # We still need the string version to feed into the Gemini prompt
        prop_info_str = property_data.model_dump_json()
        
        # 3. Create the "Hidden Context" message for the AI
        # This acts as the AI's short-term memory for this specific turn
        context_message = f"""
        [SYSTEM INJECTION: User has clicked on property card]
        PROPERTY DATA: {prop_info_str}
        """

        # 4. Prepare the conversation for the summary generation
        conversation_context = history + [
            {"role": "user", "parts": [{"text": context_message}]}
        ]

        # 5. Prompt for the summary
        system_instruction = """
        You are Mark, a Real Estate AI. The user just opened a specific property.
        
        Task:
        1. Acknowledge the property choice enthusiastically.
        2. Give a 2-sentence summary of its key selling points (Location, Price, Amenities).
        3. Ask a relevant hook question.
        """

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=conversation_context,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                )
            )
            
            # Return the text summary AND the raw Property JSON object
            return {
                "summary": response.text,
                "property": property_data.model_dump() # Returns the dictionary (JSON)
            }
            
        except Exception as e:
            print(f"Summary Error: {str(e)}")
            return {
                "summary": "That's a great property! Would you like to know more details about it?",
                "property": property_data.model_dump() if property_data else None
            }