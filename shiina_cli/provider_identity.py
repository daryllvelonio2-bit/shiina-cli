"""Provider identity: the canonical alias table and its models-semantics normalizer.

Split out of ``shiina_cli.models_catalog_static`` so callers on the model-picker path can
normalize a provider id without importing the full static catalog. Pure data + one function —
imports no modules.
"""

from __future__ import annotations


_PROVIDER_ALIASES = dict((
    ("agy", "antigravity"), ("google-antigravity", "antigravity"), ("jetski", "antigravity"),
    ("glm", "zai"), ("z-ai", "zai"), ("z.ai", "zai"), ("zhipu", "zai"), ("github", "copilot"),
    ("github-copilot", "copilot"), ("github-models", "copilot"), ("github-model", "copilot"),
    ("github-copilot-acp", "copilot-acp"), ("copilot-acp-agent", "copilot-acp"), ("google", "gemini"),
    ("google-gemini", "gemini"), ("google-ai-studio", "gemini"), ("google-vertex", "vertex"), ("vertex-ai", "vertex"),
    ("gcp-vertex", "vertex"), ("vertexai", "vertex"), ("kimi", "kimi-coding"), ("moonshot", "kimi-coding"),
    ("kimi-cn", "kimi-coding-cn"), ("moonshot-cn", "kimi-coding-cn"), ("step", "stepfun"),
    ("stepfun-coding-plan", "stepfun"), ("arcee-ai", "arcee"), ("arceeai", "arcee"), ("gmi-cloud", "gmi"),
    ("gmicloud", "gmi"), ("fireworks-ai", "fireworks"), ("fw", "fireworks"), ("actual-computer", "actual"),
    ("actualcomputer", "actual"), ("aci", "actual"), ("nebius", "nebius-token-factory"),
    ("nebius-tokenfactory", "nebius-token-factory"), ("nebius-tf", "nebius-token-factory"),
    ("token-factory", "nebius-token-factory"), ("tokenfactory", "nebius-token-factory"),
    ("minimax-china", "minimax-cn"), ("minimax_cn", "minimax-cn"), ("minimax-portal", "minimax-oauth"),
    ("minimax-global", "minimax-oauth"), ("minimax_oauth", "minimax-oauth"), ("claude", "anthropic"),
    ("claude-code", "anthropic"), ("deep-seek", "deepseek"), ("opencode", "opencode-zen"), ("zen", "opencode-zen"),
    ("go", "opencode-go"), ("opencode-go-sub", "opencode-go"), ("aigateway", "ai-gateway"), ("vercel", "ai-gateway"),
    ("vercel-ai-gateway", "ai-gateway"), ("kilo", "kilocode"), ("kilo-code", "kilocode"),
    ("kilo-gateway", "kilocode"), ("dashscope", "alibaba"), ("aliyun", "alibaba"), ("qwen", "alibaba"),
    ("alibaba-cloud", "alibaba"), ("qwen-portal", "qwen-oauth"), ("hf", "huggingface"),
    ("hugging-face", "huggingface"), ("huggingface-hub", "huggingface"), ("novita-ai", "novita"),
    ("novitaai", "novita"), ("mimo", "xiaomi"), ("xiaomi-mimo", "xiaomi"), ("tencent", "tencent-tokenhub"),
    ("tokenhub", "tencent-tokenhub"), ("tencent-cloud", "tencent-tokenhub"), ("tencentmaas", "tencent-tokenhub"),
    ("tokenplan", "tencent-tokenplan"), ("tencent-lkeap", "tencent-tokenplan"), ("aws", "bedrock"),
    ("aws-bedrock", "bedrock"), ("amazon-bedrock", "bedrock"), ("amazon", "bedrock"), ("grok", "xai"),
    ("grok-oauth", "xai-oauth"), ("xai-oauth", "xai-oauth"), ("x-ai-oauth", "xai-oauth"),
    ("xai-grok-oauth", "xai-oauth"), ("x-ai", "xai"), ("x.ai", "xai"), ("nim", "nvidia"), ("nvidia-nim", "nvidia"),
    ("build-nvidia", "nvidia"), ("nemotron", "nvidia"), ("lmstudio", "lmstudio"), ("lm-studio", "lmstudio"),
    ("lm_studio", "lmstudio"),
    ("ollama", "custom"),  # bare "ollama" = local; use "ollama-cloud" for cloud
    ("ollama_cloud", "ollama-cloud"),
))


def normalize_provider(provider: Optional[str]) -> str:
    """Normalize provider aliases to canonical ids. ``"auto"`` passes through — use
    ``shiina_cli.auth.resolve_provider()`` to resolve it from credentials."""
    normalized = (provider or "openrouter").strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)
