import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from agent.session import Session
from core.llm import LLMClient
from tools.registry import build_default_registry
from core.paths import PATHS

def test_agent():
    # 1. Create a dummy file in the workspace
    workspace = PATHS.workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    test_file = workspace / "test_config.yaml"
    test_file.write_text("model: mistral-test-model\nversion: 1.0\n", encoding="utf-8")
    print(f"Created test file at: {test_file}")

    print("Initializing LLM Client and Session...")
    llm = LLMClient()
    registry = build_default_registry(llm=llm)
    
    session = Session(
        llm=llm,
        tool_registry=registry,
        on_step=lambda step: print(f"[{step.step_type.value}] {step.content} (Status: {step.status.value})")
    )
    
    task = "Read file test_config.yaml and report the value of the model key."
    print(f"\nRunning task: '{task}'")
    
    result = session.send(task)
    
    print("\n--- Result ---")
    print(f"Success: {result.success}")
    print(f"Final Answer: {result.final_answer}")
    print(f"Tools Used: {result.tools_used}")
    print(f"Error: {result.error}")

    # Clean up
    if test_file.exists():
        test_file.unlink()
        print("Cleaned up test file.")

if __name__ == "__main__":
    test_agent()
