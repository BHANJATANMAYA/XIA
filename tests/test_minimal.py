import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.llm import LLMClient
from core.prompt import PromptBuilder

def test():
    llm = LLMClient(model="qwen3.5:4b")
    builder = PromptBuilder()
    sys_prompt = builder.build_chat_prompt()
    
    questions = [
        "hi",
        "do we need ssl for local testing?",
        "who are you?",
        "how do i delete a file in python?"
    ]
    
    history = []
    print(f"Testing with model: {llm.model}")
    print("---")
    
    for q in questions:
        print(f"User: {q}")
        start = time.time()
        resp = llm.chat(q, history=history, system_prompt=sys_prompt)
        elapsed = time.time() - start
        
        print(f"XIA: {resp.content}")
        print(f"Time: {elapsed:.2f}s | Tokens: {resp.total_tokens} (prompt: {resp.prompt_tokens}, completion: {resp.completion_tokens})")
        print("---")
        
        # update history
        history = resp.updated_history

if __name__ == "__main__":
    test()
