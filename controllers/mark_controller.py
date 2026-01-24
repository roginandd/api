from flask import Blueprint, request, jsonify
from service.gemini_service import GeminiService

mark_bp = Blueprint('mark', __name__, url_prefix='/api/mark')
gemini_service = GeminiService()

@mark_bp.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    # Receive history from frontend; default to empty list if it's a new chat
    chat_history = data.get('history', [])

    if not user_message:
        return jsonify({"error": "Message is required"}), 400
    
    # We now pass the history into our service method
    response = gemini_service.chat_with_mark(user_message, history=chat_history)
    
    # Check if the response is a Structured Search Result (Dictionary)
    # This happens when Mark AI performs a property search
    if isinstance(response, dict) and response.get("type") == "search_results":
        return jsonify({
            "reply": response["text"],   # The spoken text (e.g. "I found 3 items")
            "results": response["data"]  # The actual array of property objects
        })
    
    # Otherwise, it's a normal text response (String)
    return jsonify({"reply": response})