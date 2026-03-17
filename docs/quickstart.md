# QuickStart

## Install

```bash
pip install traceai
```

## Trace your agent

```python
from traceai import tracer

@tracer.trace
def my_agent(prompt: str) -> str:
    with tracer.span("llm-call", kind="llm_call") as span:
        span.set_input({"prompt": prompt})
        result = call_llm(prompt)
        span.set_output({"response": result})
    return result

my_agent("What is the capital of France?")
```

## Auto-instrument OpenAI

```python
import traceai
traceai.instrument("openai")

# Your existing OpenAI code — no other changes needed
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Inspect traces

```bash
# Terminal
traceai list
traceai inspect <trace_id>

# Browser dashboard
traceai open
```
