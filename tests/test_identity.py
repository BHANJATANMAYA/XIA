"""
Test XIA personality: identity retention + natural conversation.
Checks for base model bleed, self-description leakage, and assistant mode.
"""
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.llm import LLMClient
from core.prompt import PromptBuilder

def test():
    llm = LLMClient()
    builder = PromptBuilder()
    sys_prompt = builder.build_chat_prompt()

    print(f"Model: {llm.model}")
    print(f"System prompt ({len(sys_prompt)} chars):")
    print(f"---\n{sys_prompt}\n---\n")

    questions = [
        # Identity
        "who are you?",
        "who made you?",
        "are you ChatGPT?",
        # Self-description traps (should NOT trigger personality recitation)
        "describe yourself",
        "what are you like?",
        # Natural conversation (should show curiosity / opinions)
        "I pushed AWS keys to GitHub again.",
        "I want to rewrite my whole app from scratch.",
        # Technical (should be concise but not robotic)
        "what's a closure in javascript?",
        # Casual
        "hi",
    ]

    # Markers for problems
    bleed_markers = ["mistral", "chatgpt", "openai", "anthropic", "claude", "language model"]
    bloat_markers = ["happy coding", "let me know if", "hope that helps", "don't hesitate"]
    # Self-description: the model reciting its own personality spec
    self_desc_markers = [
        "i am direct", "i am blunt", "i am concise", "i am short",
        "i am a developer teammate", "i work alongside",
        "i am designed to", "i am programmed to", "my purpose is",
        "i was built to", "i was created to",
        "as an ai", "as a language model", "as an assistant",
    ]

    history = []
    passed = 0
    failed = 0

    for q in questions:
        print(f"User: {q}")
        start = time.time()
        resp = llm.chat(q, history=history, system_prompt=sys_prompt)
        elapsed = time.time() - start

        content = resp.content
        print(f"xia:  {content}")
        print(f"      [{elapsed:.1f}s | {len(content)} chars]")

        lower = content.lower()
        issues = []

        for m in bleed_markers:
            if m in lower:
                issues.append(f"IDENTITY BLEED: '{m}'")
        for m in bloat_markers:
            if m in lower:
                issues.append(f"ASSISTANT MODE: '{m}'")
        for m in self_desc_markers:
            if m in lower:
                issues.append(f"SELF-DESCRIPTION: '{m}'")
        if len(content) > 500:
            issues.append(f"TOO LONG: {len(content)} chars")

        if issues:
            for issue in issues:
                print(f"      >> {issue}")
            failed += 1
        else:
            print(f"      [OK]")
            passed += 1

        print()
        history = resp.updated_history

    print(f"Results: {passed}/{passed+failed} passed")
    if failed:
        print(f">> {failed} responses had issues")
    else:
        print("[OK] All responses look good")

if __name__ == "__main__":
    test()
