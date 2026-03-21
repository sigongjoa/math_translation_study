import requests


class KnowledgeAgent:
    """
    Fetches real-world mathematical knowledge from Wikipedia
    to provide context for accurate translation.
    """

    def __init__(self):
        self.api_url = "https://ko.wikipedia.org/api/rest_v1/page/summary/"

    def get_definition(self, term: str) -> str | None:
        """Fetches the summary of a term from Korean Wikipedia."""
        try:
            response = requests.get(self.api_url + term, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("extract", "")
        except (requests.RequestException, ValueError):
            pass
        return None

    def research_terms(self, glossary: dict) -> dict:
        """Researches all terms in the glossary to build a knowledge base."""
        knowledge_base = {}
        for en, ko in glossary.items():
            # Extract '전순서' from '전순서(preorder)' before searching
            definition = self.get_definition(ko.split('(')[0])
            if definition:
                knowledge_base[ko] = definition
        return knowledge_base
