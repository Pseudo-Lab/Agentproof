"""Bind strict deadlines and patch recovery to mini's unchanged batch CLI.

Mini owns the loop, prompts, parsing, accounting, files and resume. Its native
wall limit only checks between turns. asyncio bounds the library request; GNU
timeout bounds the command inside Docker, including child processes.
"""
import asyncio
import time

import litellm
from anyio.from_thread import BlockingPortalProvider
from minisweagent.exceptions import Submitted, TimeExceeded
from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.utils.actions_toolcall import BASH_TOOL
from minisweagent.run.benchmarks import swebench
from minisweagent.run.benchmarks.utils.common import ProgressTrackingAgent


def time_exceeded():
    return TimeExceeded({"role": "exit", "content": "TimeExceeded",
                         "extra": {"exit_status": "TimeExceeded", "submission": ""}})


class DeadlineModel(LitellmModel):
    # Retry sleeps can exceed the deadline. Keep native parsing and accounting,
    # but end failed requests without retrying.
    abort_exceptions = [BaseException]
    deadline = float("inf")
    portal_provider = BlockingPortalProvider()

    def _query(self, messages, **kwargs):
        async def request():
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise time_exceeded()
            try:
                async with asyncio.timeout(remaining):
                    return await litellm.acompletion(
                        model=self.config.model_name, messages=messages, tools=[BASH_TOOL],
                        **(self.config.model_kwargs | kwargs | {"num_retries": 0}),
                    )
            except TimeoutError:
                raise time_exceeded() from None
        with self.portal_provider as portal:
            return portal.call(request)


class DeadlineEnvironment:
    """Delegate to the native Docker environment; bound its interpreter only."""
    def __init__(self, environment, deadline):
        self.environment = environment
        self.deadline = deadline

    def __getattr__(self, name):
        return getattr(self.environment, name)

    def execute(self, action):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise time_exceeded()
        limit = min(remaining, self.config.timeout)
        original = self.config.interpreter
        self.config.interpreter = ["timeout", "--signal=KILL", f"{limit:.6f}", *original]
        try:
            # Work ends at limit; grace only collects the killed command's output.
            result = self.environment.execute(action, timeout=limit + 2)
        except Submitted:
            if time.monotonic() >= self.deadline:
                raise time_exceeded() from None
            raise
        finally:
            self.config.interpreter = original
        if time.monotonic() >= self.deadline:
            raise time_exceeded()
        return result


class BudgetAgent(ProgressTrackingAgent):
    def run(self, task="", **kwargs):
        self._start_time = time.time()
        seconds = self.config.wall_time_limit_seconds
        deadline = time.monotonic() + seconds if seconds else float("inf")
        self.model.deadline = deadline
        original_env = self.env
        self.env = DeadlineEnvironment(original_env, deadline)
        try:
            try:
                info = super().run(task, **kwargs)
            finally:
                # Persist mini's existing timer before recovery and cleanup.
                if self.messages and self.messages[-1].get("role") == "exit":
                    self.messages[-1].setdefault("extra", {})["elapsed_seconds"] = (
                        self.get_template_vars()["elapsed_seconds"]
                    )
            if info.get("exit_status") in {"TimeExceeded", "LimitsExceeded"}:
                # Include new nonignored files; exclude mini's patch output artifact.
                result = original_env.execute({"command": "git add -N . && git diff --binary HEAD -- . ':!patch.txt'"}, timeout=30)
                if result["returncode"] != 0:
                    raise RuntimeError(f"Could not recover patch after budget exhaustion: {result['output']}")
                info.update(submission=result["output"], autosubmitted=True)
            return info
        finally:
            self.env = original_env
            # Native batch relies on __del__; retained references can keep its last container alive.
            original_env.cleanup()


def main():
    # The native batch script fixes its agent class internally. Bind that class;
    # leave its CLI, dataset loading, workers and persistence intact.
    original = swebench.ProgressTrackingAgent
    swebench.ProgressTrackingAgent = BudgetAgent
    try:
        # The configured model is imported by its canonical module, even under -m.
        from minisweagent.run.benchmarks.aci import DeadlineModel as ConfiguredModel
        with ConfiguredModel.portal_provider:
            swebench.app()
    finally:
        swebench.ProgressTrackingAgent = original


if __name__ == "__main__":
    main()
