import re
from typing import Tuple
from app.core.config import settings
from groq import Groq

# Rejection text requested by the user
REJECTION_MESSAGE = (
    "I am ResearchPilot AI and can only assist with academic research, research papers, "
    "literature reviews, citations, and scholarly analysis. Please ask a research-related question."
)

class GuardService:
    @staticmethod
    def is_research_related_local(query: str) -> Tuple[bool, str]:
        """
        Fast heuristic check for obvious non-academic categories:
        Recipes, casual chat, jokes, sports.
        """
        q = query.lower().strip()
        
        # Match obvious non-academic patterns
        non_academic_keywords = [
            r"\b(recipe|cook|bake|ingredients|tablespoon|teaspoon|oven|fry|boil|saucepan)\b",
            r"\b(joke|riddle|funny story|tell me a joke|laugh|comedian)\b",
            r"\b(movie|film|actor|actress|cinema|director|hollywood|netflix|blockbuster)\b",
            r"\b(sports|football|basketball|soccer|baseball|cricket|tennis|olympics|nfl|nba|premier league|chelsea|manchester united)\b",
            r"\b(weather today|weather in|temperature outside)\b",
            r"\b(how are you|what is your name|do you like me|social media|tiktok|instagram|twitter|facebook)\b"
        ]
        
        for pattern in non_academic_keywords:
            if re.search(pattern, q):
                return False, REJECTION_MESSAGE
                
        return True, ""

    @staticmethod
    def classify_query(query: str) -> bool:
        """
        Query classifier using Groq Llama 3.3.
        Returns True if query is research-related, False otherwise.
        """
        # First check heuristics
        is_ok, _ = GuardService.is_research_related_local(query)
        if not is_ok:
            return False
            
        if not settings.GROQ_API_KEY:
            # In mock mode, if the query contains common academic keywords (paper, research, algorithm, study, etc.) or is complex, allow it.
            # Otherwise allow it if it does not match obvious casual questions.
            casual_words = ["hello", "hi", "hey", "who are you", "what's up", "howdy"]
            if any(word in query.lower().split() for word in casual_words):
                return False
            return True

        try:
            client = Groq(api_key=settings.GROQ_API_KEY)
            
            prompt = (
                f"You are a classification system for an academic research platform. "
                f"Determine if the user query is related to academic research, scientific studies, literature reviews, "
                f"research methodologies, citations, or academic topics.\n\n"
                f"User query: '{query}'\n\n"
                f"Respond with exactly one word: 'YES' if it is research-related/academic, or 'NO' if it is casual chat, jokes, sports, recipes, movies, or general non-scholarly topics. Do not add anything else."
            )
            
            completion = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a strict academic query classifier. Respond ONLY with YES or NO."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=5
            )
            
            response_text = completion.choices[0].message.content.strip().upper()
            return "YES" in response_text
            
        except Exception as e:
            print(f"Error calling Groq for query classification: {e}")
            # In case of API failure, fail-open for queries unless caught by local heuristics
            return True

guard_service = GuardService()
