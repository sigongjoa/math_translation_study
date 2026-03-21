class ConsistencyManager:
    """
    Tracks and enforces terminology and stylistic consistency across different text blocks.
    """
    
    def __init__(self):
        self.translation_memory = {} # {original_term: translated_term}

    def update_memory(self, original_text, translated_text, glossary):
        """Extracts newly used terms and stores them in memory."""
        for en, ko in glossary.items():
            # Check if the term exists in both original and translation
            if en.lower() in original_text.lower() and ko in translated_text:
                self.translation_memory[en] = ko

    def get_consistency_prompt(self):
        """Returns a string to be added to the prompt to enforce consistency."""
        if not self.translation_memory:
            return ""
        
        items = [f"- {en} -> {ko}" for en, ko in self.translation_memory.items()]
        memory_str = "\n".join(items)
        return f"\nPREVIOUSLY USED TRANSLATIONS (Maintain consistency):\n{memory_str}\n"
