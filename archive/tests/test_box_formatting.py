import re

def clean_for_latex(text):
    if not text: return ""
    return text.replace('&', '\\&').replace('%', '\\%').replace('#', '\\#')

def format_content_with_boxes(text):
    translated = clean_for_latex(text)
    
    mappings = [
        (["DEFINITION", "PROPOSITION", "THEOREM", "제명", "정의", "명제", "정리"], "definitionbox"),
        (["EXAMPLE", "예시", "예제"], "examplebox"),
        (["EXERCISE", "문제", "연습"], "exercisebox"),
        (["REMARK", "비고", "주석"], "remarkbox")
    ]
    
    for keywords, env in mappings:
        for kw in keywords:
            # The current regex being tested
            # pattern = rf'\[\s*{kw}\s*(.*?)\](.*?)\[\s*(?:END_{kw}|{kw}\s+끝|제명\s+끝|끝)\s*\]'
            # Let's try to find why it fails for Remark 1.31
            pattern = rf'\[\s*{kw}\s*(.*?)\](.*?)\[\s*(?:END_{kw}|{kw}\s+끝|제명\s+끝|끝|END_{kw.upper()})\s*\]'
            
            def replace_with_box(m):
                label = m.group(1).strip()
                content = m.group(2).strip()
                return f"\n\\begin{{{env}}}[{label}]\n{content}\n\\end{{{env}}}\n"
                
            translated = re.sub(
                pattern,
                replace_with_box,
                translated, flags=re.DOTALL | re.IGNORECASE
            )
    return translated

# --- Test Cases ---
test_cases = [
    {
        "name": "Standard English Remark",
        "input": "[REMARK Remark 1.31]\nThis is a remark.\n[END_REMARK]",
        "expected": "\\begin{remarkbox}[Remark 1.31]\nThis is a remark.\n\\end{remarkbox}"
    },
    {
        "name": "Korean Remark (Translated)",
        "input": "[비고 1.31]\n이것은 비고입니다.\n[비고 끝]",
        "expected": "\\begin{remarkbox}[1.31]\n이것은 비고입니다.\n\\end{remarkbox}"
    },
    {
        "name": "Whitespace Variation",
        "input": "[  REMARK   Label  ] Content [  END_REMARK  ]",
        "expected": "\\begin{remarkbox}[Label]\nContent\n\\end{remarkbox}"
    },
    {
        "name": "Multiple Blocks",
        "input": "[DEFINITION Def 1]\nDef content\n[END_DEFINITION]\n\n[REMARK Rem 1]\nRem content\n[END_REMARK]",
        "expected": "definitionbox"
    }
]

def run_tests():
    print("Running Box Formatting Tests (Fixed Syntax)...\n")
    success_count = 0
    for case in test_cases:
        output = format_content_with_boxes(case["input"])
        passed = (case["expected"] in output) or (case["expected"] == "definitionbox" and "definitionbox" in output and "remarkbox" in output)
        if passed:
            print(f"✅ PASSED: {case['name']}")
            success_count += 1
        else:
            print(f"❌ FAILED: {case['name']}")
            print(f"   Input: {case['input']}")
            print(f"   Output: {output}")
            print("-" * 30)
    
    print(f"\nSummary: {success_count}/{len(test_cases)} passed.")

if __name__ == "__main__":
    run_tests()
