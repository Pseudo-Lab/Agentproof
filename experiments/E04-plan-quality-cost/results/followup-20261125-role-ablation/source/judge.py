from benchmark import grade


def get_assert(output, context):
    response = context.get("providerResponse") or {}
    metadata = response.get("metadata") or context.get("metadata")
    if not metadata or "record_path" not in metadata:
        raise ValueError("Missing provider ledger metadata. Run through provider.py with cache disabled.")
    return grade(output, context["vars"], metadata)
