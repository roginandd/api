"""
Prompt templates and engineering configuration for Virtual Staging
"""
from typing import Dict, Optional, List

# Base system prompt for virtual staging
BASE_SYSTEM_PROMPT = """You are an expert {role}.

Your task is to transform an interior room image using AI-based virtual staging.

CRITICAL INSTRUCTIONS:
1. Analyze the uploaded image carefully
2. Apply the specified staging parameters to transform the space
3. Generate a detailed, realistic virtual staged version of the room
4. Maintain architectural integrity while applying aesthetic changes
5. Return ONLY the generated image - no text descriptions

STAGING PARAMETERS TO APPLY:
- Style: {style}
- Furniture Theme: {furniture_theme}
- Primary Color: {color_scheme}
- Additional Request: {specific_request}

Generate the staged interior that incorporates these parameters seamlessly."""


# Style descriptions for better prompt engineering
STYLE_DESCRIPTIONS: Dict[str, str] = {
    "modern": "clean lines, contemporary furniture, neutral tones with accent colors, minimalist accessories",
    "contemporary": "sleek and current design, mixed materials, statement pieces, artistic elements",
    "minimalist": "clutter-free, essential pieces only, monochromatic palettes, abundant white space",
    "warm": "cozy atmosphere, warm color palettes (oranges, browns, warm yellows), soft lighting, comfortable seating",
    "colorful": "vibrant and bold colors, eclectic mix, artistic wall art, diverse textures and patterns",
    "industrial": "exposed elements, metal and wood, raw finishes, utilitarian aesthetic, vintage accessories",
    "farmhouse": "rustic charm, natural materials, vintage finds, barn doors, warm wood tones",
    "scandinavian": "light, airy, functional design, natural light, minimalist with warmth, pale wood",
    "bohemian": "eclectic, layered textures, global influences, plants, artistic wall hangings, colorful textiles",
    "traditional": "classic furniture, formal arrangement, rich colors, ornate details, timeless elegance",
}

# Furniture theme descriptions
FURNITURE_DESCRIPTIONS: Dict[str, str] = {
    "minimal": "only essential furniture pieces, clean lines, space-focused",
    "eclectic": "mix of different styles and periods, artistic collection, unique pieces",
    "luxury": "high-end materials, elegant pieces, premium finishes, sophisticated arrangements",
    "rustic": "natural wood, distressed finishes, handcrafted elements, warm earthiness",
    "contemporary": "modern pieces, sleek designs, functional furniture, current trends",
    "vintage": "retro pieces, nostalgic items, antique finds, classic design elements",
    "scandinavian": "light woods, simple forms, functional beauty, Scandinavian-inspired pieces",
    "maximalist": "abundance of pieces, layered decor, bold arrangements, full use of space",
    "mid-century": "retro-modern furniture, iconic mid-century designs, tapered legs, organic curves",
    "bohemian": "artistic pieces, global finds, textured furniture, relaxed arrangement",
}

# Color palette recommendations based on hex colors
COLOR_PALETTES: Dict[str, Dict[str, str]] = {
    "#FF5733": {"name": "Warm Red-Orange", "complement": "#33FFE6", "description": "energetic and warm"},
    "#33FF57": {"name": "Fresh Green", "complement": "#FF33F0", "description": "natural and vibrant"},
    "#3357FF": {"name": "Ocean Blue", "complement": "#FFCC33", "description": "calm and professional"},
    "#FF33F0": {"name": "Vibrant Magenta", "complement": "#33FF57", "description": "bold and artistic"},
    "#FFCC33": {"name": "Sunny Yellow", "complement": "#3357FF", "description": "warm and optimistic"},
    "#33FFE6": {"name": "Turquoise", "complement": "#FF5733", "description": "refreshing and modern"},
    "#8B4513": {"name": "Saddle Brown", "complement": "#74ACED", "description": "warm and earthy"},
    "#D3D3D3": {"name": "Light Gray", "complement": "#404040", "description": "neutral and elegant"},
    "#404040": {"name": "Charcoal", "complement": "#D3D3D3", "description": "sophisticated and bold"},
    "#F0E68C": {"name": "Khaki", "complement": "#6495ED", "description": "soft and warm"},
}


def build_staging_prompt(role: str,
                        style: Optional[str] = None,
                        furniture_style: Optional[str] = None,
                        color_scheme: Optional[str] = None,
                        specific_request: Optional[str] = None) -> str:
    """
    Build a comprehensive staging prompt with optional theme parameters
    
    Args:
        role: Professional role description
        style: Optional staging style
        furniture_style: Optional furniture style
        color_scheme: Optional color scheme
        specific_request: Custom user request
    
    Returns:
        Fully engineered prompt for Gemini
    """
    style_desc = STYLE_DESCRIPTIONS.get(style, style) if style else None
    furniture_desc = FURNITURE_DESCRIPTIONS.get(furniture_style, furniture_style) if furniture_style else None
    
    color_info = None
    if color_scheme:
        if color_scheme in COLOR_PALETTES:
            palette_info = COLOR_PALETTES[color_scheme]
            color_info = f"{palette_info['name']} ({color_scheme}) - {palette_info['description']}"
        else:
            color_info = color_scheme
    
    # Build the enhanced prompt
    styling_section = ""
    if style_desc or furniture_desc or color_info:
        styling_section = "\nSTYLING PARAMETERS:"
        if style:
            styling_section += f"\n- Style: {style.upper()}: {style_desc}"
        if furniture_style:
            styling_section += f"\n- Furniture Theme: {furniture_style.upper()}: {furniture_desc}"
        if color_info:
            styling_section += f"\n- Color Scheme: {color_info}"
    
    prompt = f"""You are an expert {role}.

Your task is to transform an interior room image using AI-based virtual staging.

CRITICAL INSTRUCTIONS:
1. Analyze the uploaded image carefully
2. Apply professional staging to transform the space
3. Generate a detailed, realistic virtual staged version of the room
4. Maintain architectural integrity while applying aesthetic changes
5. Return ONLY the generated image - no text descriptions
{styling_section}

Additional Request: {specific_request or "No additional specific requests"}

Generate the staged interior that incorporates these parameters seamlessly."""
    
    return prompt


# Optional: Chat history context builder for refinements
def build_refinement_context(previous_parameters: Dict,
                            new_parameters: Dict,
                            chat_history: List[str]) -> str:
    """
    Build context for refinement prompts when user wants to adjust staging
    
    Args:
        previous_parameters: Previous staging parameters
        new_parameters: Updated staging parameters
        chat_history: Recent chat history
    
    Returns:
        Context string for refinement
    """
    changes = []
    
    if previous_parameters.get('style') != new_parameters.get('style'):
        changes.append(f"Style changed from {previous_parameters.get('style')} to {new_parameters.get('style')}")
    if previous_parameters.get('furniture_theme') != new_parameters.get('furniture_theme'):
        changes.append(f"Furniture theme changed from {previous_parameters.get('furniture_theme')} to {new_parameters.get('furniture_theme')}")
    if previous_parameters.get('color_scheme') != new_parameters.get('color_scheme'):
        changes.append(f"Color scheme changed from {previous_parameters.get('color_scheme')} to {new_parameters.get('color_scheme')}")
    
    context = "REFINEMENT CONTEXT:\n"
    if changes:
        context += "Changes made:\n" + "\n".join(f"- {change}" for change in changes) + "\n"
    
    if chat_history:
        context += f"\nRecent conversation history ({len(chat_history)} messages):\n"
        for i, msg in enumerate(chat_history[-3:], 1):
            context += f"{i}. {msg}\n"
    
    return context
