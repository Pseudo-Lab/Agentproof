from benchmark import generate


def call_api(prompt, options, context):
    variables = context["vars"]
    return generate(options["config"]["group"], prompt, variables["task_id"],
                    context.get("repeatIndex", 0))
