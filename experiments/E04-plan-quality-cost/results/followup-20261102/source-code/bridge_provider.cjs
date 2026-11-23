// Optional localhost transport for environments where Node cannot spawn Python.
module.exports = class PlanProvider {
  constructor(options) { this.config = options.config; }
  id() { return `plan-${this.config.group}`; }
  async callApi(prompt, context) {
    const response = await fetch(`${process.env.PLAN_BRIDGE_URL}/generate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.PLAN_BRIDGE_TOKEN}` },
      body: JSON.stringify({ prompt, group: this.config.group, context: {
        vars: context.vars, repeatIndex: context.repeatIndex ?? 0,
      } }),
    });
    if (!response.ok) throw new Error(`Python bridge: HTTP ${response.status}`);
    return await response.json();
  }
};
