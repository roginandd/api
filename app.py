from service.gemini_service import GeminiService

if __name__ == "__main__":
    gemini_service = GeminiService()

    print(gemini_service.generate_content("gemini-2.0-flash", "Who is SZA?!"))