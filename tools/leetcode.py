"""
tools/leetcode.py — LeetCode Agent Workflow

A specialized tool that orchestrates the full LeetCode solve cycle:
  1. Navigate to the problem
  2. Extract the problem description, constraints, examples
  3. Generate a Python solution using the LLM
  4. Submit and read the result
  5. If wrong — analyze the error, search for approaches, fix and retry
  6. Report final outcome

This tool is called as a single high-level action:

  {
    "tool": "leetcode",
    "input": {
      "action": "solve",
      "problem": "two-sum",
      "max_attempts": 5
    }
  }

Or to just fetch a problem without solving:
  {
    "tool": "leetcode",
    "input": {
      "action": "fetch",
      "problem": "two-sum"
    }
  }
"""

import re
import time
from typing import Optional, Tuple

from core.logger import get_logger
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)

LEETCODE_BASE = "https://leetcode.com"


class LeetCodeTool(BaseTool):

    name        = "leetcode"
    description = (
        "Solve LeetCode problems end-to-end: fetch the problem, generate a Python solution, "
        "submit it, debug if wrong, search for approaches if stuck, and resubmit until accepted."
    )

    def __init__(self, browser_tool=None, llm=None):
        self._browser = browser_tool
        self._llm     = llm

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("action",       "string",  "One of: solve, fetch, submit_code", required=True),
                ToolParam("problem",      "string",  "Problem slug or name (e.g. 'two-sum', 'reverse-linked-list')", required=True),
                ToolParam("max_attempts", "integer", "Max solve attempts before searching online (default: 3)", required=False, default=3),
                ToolParam("language",     "string",  "Programming language (default: python3)", required=False, default="python3"),
            ],
        )

    def execute(
        self,
        action: str,
        problem: str,
        max_attempts: int = 3,
        language: str = "python3",
        **_,
    ) -> ToolResult:

        if not self._browser:
            return self._err("Browser tool not available. Ensure BrowserTool is initialised.")

        action = action.lower().strip()
        problem_slug = self._normalise_slug(problem)

        if action == "fetch":
            return self._fetch_problem(problem_slug)
        elif action == "solve":
            return self._solve_problem(problem_slug, max_attempts, language)
        else:
            return self._err(f"Unknown action '{action}'. Use: fetch, solve")

    # ── Main solve loop ────────────────────────────────────────────────────

    def _solve_problem(self, slug: str, max_attempts: int, language: str) -> ToolResult:
        log.info("LeetCode: solving '%s' max_attempts=%d", slug, max_attempts)

        # Step 1: Fetch problem
        fetch_result = self._fetch_problem(slug)
        if not fetch_result.success:
            return fetch_result

        problem_text = fetch_result.output
        log.info("Problem fetched: %d chars", len(problem_text))

        attempt = 0
        last_error = ""
        solution_history = []

        while attempt < max_attempts:
            attempt += 1
            log.info("Attempt %d/%d", attempt, max_attempts)

            # Step 2: Generate solution
            solution = self._generate_solution(
                problem_text=problem_text,
                language=language,
                previous_attempts=solution_history,
                last_error=last_error,
            )

            if not solution:
                return self._err("LLM failed to generate a solution.")

            solution_history.append({
                "attempt": attempt,
                "code": solution,
                "error": last_error,
            })

            log.info("Solution generated (%d chars)", len(solution))

            # Step 3: Submit
            submit_result = self._submit_solution(slug, solution, language)

            if "Accepted" in submit_result:
                return self._ok(
                    f"✓ ACCEPTED on attempt {attempt}/{max_attempts}\n\n"
                    f"Problem: {slug}\n"
                    f"Language: {language}\n\n"
                    f"Solution:\n```python\n{solution}\n```\n\n"
                    f"Result: {submit_result}"
                )

            last_error = submit_result
            log.info("Attempt %d failed: %s", attempt, submit_result[:100])

            # If we've hit max attempts, search for approaches
            if attempt >= max_attempts:
                log.info("Max attempts reached — searching for approaches")
                return self._search_for_approaches(slug, problem_text, solution_history, last_error)

        return self._err(f"Could not solve '{slug}' after {max_attempts} attempts.\nLast error: {last_error}")

    # ── Problem fetching ───────────────────────────────────────────────────

    def _fetch_problem(self, slug: str) -> ToolResult:
        url = f"{LEETCODE_BASE}/problems/{slug}/"

        nav = self._browser.execute(action="navigate", url=url, timeout=15000)
        if not nav.success:
            return self._err(f"Could not navigate to problem: {nav.error}")

        # Wait for problem content to load
        time.sleep(3)

        # Try to extract problem description
        # LeetCode renders content in a div with data-track-load attribute
        selectors_to_try = [
            "[data-track-load='description_content']",
            ".elfjS",
            "[class*='description']",
            "div[class*='content']",
        ]

        problem_text = ""
        for sel in selectors_to_try:
            result = self._browser.execute(action="extract_text", selector=sel)
            if result.success and len(result.output) > 100:
                problem_text = result.output
                break

        if not problem_text:
            # Fall back to full page
            result = self._browser.execute(action="extract_text")
            if result.success:
                problem_text = result.output

        if not problem_text or len(problem_text) < 50:
            return self._err(
                f"Could not extract problem content from {url}\n"
                "LeetCode may require login or the page didn't load properly."
            )

        # Get title
        title_result = self._browser.execute(action="get_title")
        title = title_result.output if title_result.success else slug

        return self._ok(
            f"Problem: {title}\n"
            f"URL: {url}\n\n"
            f"{'─'*50}\n\n"
            f"{problem_text[:4000]}"
        )

    # ── Solution generation ────────────────────────────────────────────────

    def _generate_solution(
        self,
        problem_text: str,
        language: str,
        previous_attempts: list,
        last_error: str,
    ) -> Optional[str]:

        if not self._llm:
            return None

        if not previous_attempts:
            prompt = f"""Solve this LeetCode problem in {language}.

{problem_text}

Requirements:
- Write ONLY the solution code, no explanations
- Include the class Solution with the required method
- Handle all edge cases
- Aim for optimal time complexity
- Start your response with ```python and end with ```"""

        else:
            prev_code = previous_attempts[-1]["code"]
            prompt = f"""Your previous LeetCode solution was WRONG.

Problem:
{problem_text[:1500]}

Your previous solution:
```python
{prev_code}
```

Error/Wrong output:
{last_error[:500]}

Fix the solution. Requirements:
- Write ONLY the corrected code
- Address the specific error above
- Start with ```python and end with ```"""

        try:
            response = self._llm.chat(prompt)
            return self._extract_code(response.content)
        except Exception as e:
            log.error("Solution generation failed: %s", e)
            return None

    def _extract_code(self, response: str) -> str:
        """Extract code block from LLM response."""
        # Try ```python ... ``` block first
        pattern = r"```(?:python)?\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()

        # If no code block, return the whole response (model may have skipped fences)
        lines = response.strip().splitlines()
        # Remove any lines that look like explanations before 'class Solution'
        code_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("class Solution") or line.strip().startswith("def "):
                code_start = i
                break
        return "\n".join(lines[code_start:]).strip()

    # ── Solution submission ────────────────────────────────────────────────

    def _submit_solution(self, slug: str, code: str, language: str) -> str:
        """
        Submit a solution to LeetCode and return the result string.
        Returns "Accepted" if correct, error message otherwise.
        """
        url = f"{LEETCODE_BASE}/problems/{slug}/"

        # Make sure we're on the right page
        url_result = self._browser.execute(action="get_url")
        if url_result.success and slug not in url_result.output:
            self._browser.execute(action="navigate", url=url, timeout=15000)
            time.sleep(3)

        # Click on the code editor and clear it
        editor_selectors = [
            ".CodeMirror",
            "[class*='editor']",
            "div[class*='code-area']",
            ".monaco-editor",
        ]

        editor_found = False
        for sel in editor_selectors:
            result = self._browser.execute(action="wait", selector=sel, timeout=3000)
            if result.success:
                self._browser.execute(action="click", selector=sel)
                editor_found = True
                break

        if not editor_found:
            return "Could not find code editor on page"

        # Select all and replace with our solution
        time.sleep(0.5)
        self._browser.execute(action="evaluate",
            value="document.querySelector('.CodeMirror') && "
                  "document.querySelector('.CodeMirror').CodeMirror.setValue('')"
        )

        # Type the solution
        self._browser.execute(action="evaluate",
            value=f"const cm = document.querySelector('.CodeMirror')?.CodeMirror; "
                  f"if(cm) cm.setValue({repr(code)})"
        )

        time.sleep(1)

        # Click Submit button
        submit_selectors = [
            "[data-e2e-locator='console-submit-button']",
            "button[class*='submit']",
        ]

        submitted = False
        for sel in submit_selectors:
            result = self._browser.execute(action="click", selector=sel, timeout=5000)
            if result.success:
                submitted = True
                break

        if not submitted:
            # Try finding by text
            self._browser.execute(action="click", text="Submit", timeout=5000)

        # Wait for result (up to 30 seconds)
        log.info("Waiting for submission result...")
        for _ in range(30):
            time.sleep(1)
            result = self._browser.execute(action="extract_text",
                selector="[class*='result'], [data-e2e-locator*='result'], "
                         "[class*='submission'], [class*='status']"
            )
            if result.success and result.output.strip():
                text = result.output.strip()
                if any(kw in text for kw in ["Accepted", "Wrong Answer",
                                              "Time Limit", "Runtime Error",
                                              "Memory Limit", "Compile Error"]):
                    return text

        # Fall back — get full page text and look for result
        full = self._browser.execute(action="extract_text")
        if full.success:
            for line in full.output.splitlines():
                if any(kw in line for kw in ["Accepted", "Wrong Answer",
                                              "Time Limit", "Runtime Error"]):
                    return line.strip()

        return "Could not determine submission result (timeout)"

    # ── Search for approaches ──────────────────────────────────────────────

    def _search_for_approaches(
        self,
        slug: str,
        problem_text: str,
        solution_history: list,
        last_error: str,
    ) -> ToolResult:
        """
        When the agent is stuck after max attempts — search online for approaches
        and use them to generate a better solution.
        """
        log.info("Searching for approaches to: %s", slug)

        search_results = []

        # Search 1: LeetCode discuss
        try:
            discuss_url = f"{LEETCODE_BASE}/problems/{slug}/discuss/?currentPage=1&orderBy=most_votes"
            self._browser.execute(action="navigate", url=discuss_url, timeout=10000)
            time.sleep(2)
            discuss = self._browser.execute(action="extract_text")
            if discuss.success:
                search_results.append(f"LeetCode Discuss:\n{discuss.output[:2000]}")
        except Exception as e:
            log.warning("Discuss fetch failed: %s", e)

        # Search 2: General web search
        try:
            from tools.search import SearchTool
            searcher = SearchTool()
            query = f"leetcode {slug.replace('-', ' ')} python solution approach"
            result = searcher.execute(query=query, max_results=3)
            if result.success:
                search_results.append(f"Web search results:\n{result.output}")
        except Exception as e:
            log.warning("Web search failed: %s", e)

        combined = "\n\n".join(search_results) if search_results else "No results found"

        # Use LLM to synthesize a new solution from the search results
        if self._llm and search_results:
            prompt = f"""You failed to solve this LeetCode problem after multiple attempts.
Here are some approaches and hints found online:

{combined[:3000]}

Original problem:
{problem_text[:1000]}

Your previous errors:
{last_error[:300]}

Based on these approaches, write a correct Python solution.
Return ONLY the code, starting with ```python"""

            try:
                response = self._llm.chat(prompt)
                new_solution = self._extract_code(response.content)
                if new_solution:
                    # Try one more time with the new approach
                    submit_result = self._submit_solution(slug, new_solution, "python3")
                    if "Accepted" in submit_result:
                        return self._ok(
                            f"✓ ACCEPTED after searching for approaches!\n\n"
                            f"Problem: {slug}\n\n"
                            f"Solution (based on community approaches):\n"
                            f"```python\n{new_solution}\n```\n\n"
                            f"Result: {submit_result}"
                        )
                    else:
                        return self._ok(
                            f"✗ Still not solved after searching online.\n\n"
                            f"Problem: {slug}\n"
                            f"Last error: {submit_result}\n\n"
                            f"Approaches found:\n{combined[:1000]}\n\n"
                            f"Best attempt:\n```python\n{new_solution}\n```\n\n"
                            f"Suggestion: Try a different model (deepseek-coder) or "
                            f"solve manually using the approaches above."
                        )
            except Exception as e:
                log.error("Post-search solution generation failed: %s", e)

        return self._ok(
            f"Searched online for '{slug}' approaches.\n\n"
            f"Found:\n{combined[:2000]}\n\n"
            f"Could not auto-solve — use the approaches above to solve manually."
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _normalise_slug(self, problem: str) -> str:
        """Convert 'Two Sum' or 'two sum' to 'two-sum'."""
        slug = problem.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        slug = slug.strip("-")
        return slug
