# Research and reuse basis

Checkpoint 1 deliberately reuses established interfaces and benchmark data.

- [OpenRouter Models API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) supplies provider-independent model metadata.
- [LiteLLM's OpenRouter integration](https://github.com/BerriAI/litellm-docs/blob/main/docs/providers/openrouter.md) supplies the async model-call client. This project still owns its normalized result contract and explicit retry policy.
- [GSM8K](https://github.com/openai/grade-school-math) supplies the objective grade-school math problems and canonical answers.
- [LLMRouterBench](https://aclanthology.org/2026.findings-acl.1881/) motivates separating collection, evaluation, and adaptation. No repository code is copied.
- [RouterBench](https://github.com/withmartian/routerbench) and [RouteLLM](https://github.com/lm-sys/RouteLLM) are later references for router evaluation and learned strong/weak model selection.
- [Jev](https://openrouter.ai/docs/guides/community/jev) is a later reference for typed decisions and confidence, not a natural-language generation model for this checkpoint.

Dynamic identities such as `openrouter/auto` and `openrouter/free` are intentionally excluded. A comparison baseline must know which model produced every output.
