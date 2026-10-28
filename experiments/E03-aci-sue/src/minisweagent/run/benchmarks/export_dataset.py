"""Export a pinned selection in the native Hugging Face JSON dataset format."""
import json
from pathlib import Path
import sys


def export_dataset(config_path, agent_output, evaluation_output):
    from datasets import Dataset, load_dataset

    cfg = json.loads(Path(config_path).read_text())
    dataset = load_dataset(cfg["dataset"], revision=cfg["revision"], split=cfg["split"])
    by_id = {row["instance_id"]: row for row in dataset}
    rows = [by_id[item["instance_id"]] for item in cfg["instances"]]
    # Agentless also needs repo; mini accepts the same gold-free dataset.
    agent = Dataset.from_list(rows).select_columns(["instance_id", "repo", "problem_statement", "base_commit"])
    folder = Path(agent_output)
    folder.mkdir(parents=True, exist_ok=True)
    agent.to_json(folder / "test.jsonl")
    path = Path(evaluation_output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(rows, stream, indent=2)


if __name__ == "__main__":
    export_dataset(*sys.argv[1:])
