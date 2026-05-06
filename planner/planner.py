"""
J.A.R.V.I.S. Planner
Breaks complex tasks into steps and executes them sequentially.

Example:
  User: "Build a Flask app"
  Plan: ["Create project structure", "Write app.py", "Install dependencies"]
  Execute: each step through the orchestrator's tool pipeline
"""


class Planner:
    """Executes multi-step plans from the LLM."""

    def __init__(self, orchestrator):
        self._orch = orchestrator

    def execute_plan(self, steps, messages):
        """
        Execute a list of plan steps.
        Each step is sent back to the LLM with context of prior results.
        Returns a summary of what was accomplished.
        """
        results = []
        for i, step in enumerate(steps):
            print(f"  [Plan step {i+1}/{len(steps)}: {step[:60]}]", flush=True)

            # Ask LLM to execute this specific step
            step_messages = list(messages) + [
                {"role": "user", "content":
                    f"Execute step {i+1} of the plan: {step}\n"
                    f"Previous results: {'; '.join(results[-3:]) if results else 'none'}\n"
                    "Use a tool if needed, or provide the output directly."
                }
            ]
            response = self._orch.llm.chat(step_messages)
            if not response:
                results.append(f"Step {i+1} failed (no response)")
                continue

            # Check if step needs a tool call
            tool_name, tool_args = self._orch._parse_action(response)
            if tool_name:
                tool_result = self._orch.tools.execute(tool_name, tool_args)
                results.append(f"Step {i+1}: {tool_result[:150]}")
                print(f"  [Plan step {i+1} tool: {tool_name} → {tool_result[:80]}]", flush=True)
            else:
                # LLM provided direct output
                clean = self._orch._clean_response(response)
                results.append(f"Step {i+1}: {clean[:150]}")

        # Summarize
        if len(results) <= 3:
            return " ".join(results)

        # Ask LLM for a brief summary
        summary_messages = messages + [
            {"role": "user", "content":
                f"Summarize what was done in 1-2 sentences:\n" +
                "\n".join(results)
            }
        ]
        summary = self._orch.llm.chat(summary_messages, max_tokens=100)
        return self._orch._clean_response(summary) if summary else " ".join(results[-2:])
