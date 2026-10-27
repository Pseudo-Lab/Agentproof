---
name: dialogue-graph
description: A library for building, validating, visualizing, and serializing dialogue graphs. Use this when parsing scripts or creating branching narrative structures.
---

# Dialogue Graph Skill

This skill provides a `dialogue_graph` module to easily build valid dialogue trees/graphs.

## When to use

*   **Script Parsers**: When converting text to data.
*   **Dialogue Editors**: When building tools to edit conversation flow.
*   **Game Logic**: When traversing a dialogue tree.


## How to use

Import the module:
```python
from dialogue_graph import Graph, Node, Edge
```

### 1. The `Graph` Class
The main container.

```python
graph = Graph()
```

### 2. Adding Nodes
Define content nodes.

```python
# Regular line
graph.add_node(Node(id="Start", speaker="Guard", text="Halt!", type="line"))

# Choice hub
graph.add_node(Node(id="Choices", type="choice"))
```

### 3. Adding Edges
Connect nodes (transitions).

```python
# Simple transition
graph.add_edge(Edge(source="Start", target="Choices"))

# Choice transition (with text)
graph.add_edge(Edge(source="Choices", target="End", text="1. Run away"))
```

### 4. Export
Serialize to JSON format for the engine.

```python
data = graph.to_dict()
# returns {"nodes": [...], "edges": [...]}
json_str = graph.to_json()
```

### 5. Validation
Check for integrity.

```python
errors = graph.validate()
# Returns list of strings, e.g., ["Edge 'Start'->'Unk' points to missing node 'Unk'"]
```


## Module source (`dialogue_graph.py`)

```python
import json
from typing import Any


class Node:
    def __init__(self, id: str, text: str = "", speaker: str = "", type: str = "line"):
        self.id = id
        self.text = text
        self.speaker = speaker
        self.type = type # 'line', 'choice'

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "speaker": self.speaker,
            "type": self.type
        }

class Edge:
    def __init__(self, source: str, target: str, text: str = ""):
        self.source = source
        self.target = target
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        d = {"from": self.source, "to": self.target}
        if self.text is not None:
            d["text"] = self.text
        return d

class Graph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []

    def add_node(self, node: Node):
        if node.id in self.nodes:
            raise ValueError(f"Node {node.id} already exists")
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def validate(self) -> list[str]:
        """Validate the graph structure."""
        errors = []
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source '{edge.source}' not found")
            if edge.target not in self.nodes and edge.target != "End":
                errors.append(f"Edge target '{edge.target}' not found")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

```
