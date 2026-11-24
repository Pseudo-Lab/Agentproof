module.exports = async (output, context) => {
  const response = await fetch(`${process.env.PLAN_BRIDGE_URL}/grade`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.PLAN_BRIDGE_TOKEN}` },
    body: JSON.stringify({ output, context: {
      vars: context.vars, providerResponse: context.providerResponse, metadata: context.metadata,
    } }),
  });
  if (!response.ok) throw new Error(`Python judge bridge: HTTP ${response.status}`);
  const result = await response.json();
  // Python's native assertion wrapper normally translates this field for us.
  if (result.named_scores) { result.namedScores = result.named_scores; delete result.named_scores; }
  return result;
};
