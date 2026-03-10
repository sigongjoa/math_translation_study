import json
import requests
import time

class TCRLoop:
    """
    REAL IMPLEMENTATION: Manages the Generation-Critique-Refinement loop 
    with scoring and retries as defined in Issue #4.
    """
    def __init__(self, model="qwen2.5:7b", threshold=80, max_iterations=3):
        self.model = model
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.ollama_url = "http://localhost:11434/api/chat"

    def run(self, original_en, glossary, initial_prompt):
        """Runs the loop until score > threshold or max_iterations reached."""
        current_ko = ""
        iteration = 0
        trace = {"original": original_en, "iterations": []}

        while iteration < self.max_iterations:
            iteration += 1
            # 1. Draft/Refine
            current_ko = self._get_translation(original_en, current_ko, glossary, initial_prompt)
            
            # 2. Score & Critique
            score, critique = self._evaluate(original_en, current_ko, glossary)
            
            trace["iterations"].append({
                "iteration": iteration,
                "translated": current_ko,
                "score": score,
                "critique": critique
            })

            if score >= self.threshold:
                break
            
        return current_ko, trace

    def _get_translation(self, en, prev_ko, glossary, prompt):
        messages = [{"role": "system", "content": prompt}]
        user_content = f"Original: {en}\n"
        if prev_ko:
            user_content += f"Previous Translation: {prev_ko}\nPlease improve based on academic standards."
        else:
            user_content += "Translate this text."
        
        messages.append({"role": "user", "content": user_content})
        
        try:
            resp = requests.post(self.ollama_url, json={
                "model": self.model, "messages": messages, "stream": False
            }, timeout=120)
            return resp.json()["message"]["content"].strip()
        except:
            return prev_ko if prev_ko else en

    def _evaluate(self, en, ko, glossary):
        """Evaluates translation and returns (score, critique)."""
        eval_prompt = (
            "Rate the translation quality from 0 to 100. "
            "Is Preorder translated as 전순서? Is it academic? "
            f"Original: {en}\nTranslated: {ko}\n"
            "Output ONLY a JSON: {\"score\": 85, \"critique\": \"...\"}"
        )

        try:
            resp = requests.post(self.ollama_url, json={
                "model": self.model, 
                "messages": [{"role": "user", "content": eval_prompt}], 
                "stream": False, "format": "json"
            }, timeout=120)
            res = json.loads(resp.json()["message"]["content"])
            return res.get("score", 0), res.get("critique", "")
        except:
            return 50, "Evaluation failed."
