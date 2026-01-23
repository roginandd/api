from flask import Blueprint, request, jsonify
from service.gemini_service import GeminiService

mark_bp = Blueprint('mark', __name__, url_prefix='/api/mark')
gemini_service = GeminiService()

@mark_bp.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')

    if not user_message:
        return jsonify({"error": "Message is required"}), 400
    
    response = gemini_service.chat_with_mark(user_message)
    
    return jsonify({"reply": response})