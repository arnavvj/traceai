import { useRef, useState } from "react";
import { useProviders } from "../hooks/useProviders";
import { useModels } from "../hooks/useModels";

const CUSTOM_SENTINEL = "__custom__";

/** Capitalize a provider name for display. */
function formatProvider(p: string): string {
  const special: Record<string, string> = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    deepseek: "DeepSeek",
    groq: "Groq",
    openrouter: "OpenRouter",
    fireworks: "Fireworks",
    perplexity: "Perplexity",
  };
  return special[p] ?? p.charAt(0).toUpperCase() + p.slice(1);
}

interface Props {
  value: string;
  onChange: (model: string, provider?: string) => void;
  disabled?: boolean;
}

export function ModelPicker({ value, onChange, disabled = false }: Props) {
  const providers = useProviders();
  const models = useModels();
  const [customMode, setCustomMode] = useState(false);
  const [customValue, setCustomValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Build a flat set of all known model IDs to check membership
  const allModels = Object.values(models).flat();
  const isKnown = allModels.includes(value);
  const selectValue = isKnown ? value : CUSTOM_SENTINEL;

  /** Look up which provider a known model belongs to. */
  function findProvider(modelId: string): string | undefined {
    for (const [p, ms] of Object.entries(models)) {
      if (ms.includes(modelId)) return p;
    }
    return undefined;
  }

  function handleSelectChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value;
    if (v === CUSTOM_SENTINEL) {
      setCustomValue(value);
      setCustomMode(true);
      setTimeout(() => inputRef.current?.select(), 0);
    } else {
      setCustomMode(false);
      onChange(v, findProvider(v));
    }
  }

  function commitCustom() {
    const trimmed = customValue.trim();
    if (trimmed) onChange(trimmed);
    setCustomMode(false);
  }

  if (customMode) {
    return (
      <div className="flex items-center gap-1">
        <span className="text-[10px] text-text-muted">Model</span>
        <input
          ref={inputRef}
          autoFocus
          value={customValue}
          onChange={(e) => setCustomValue(e.target.value)}
          onBlur={commitCustom}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitCustom();
            if (e.key === "Escape") setCustomMode(false);
          }}
          placeholder="e.g. gpt-4-turbo"
          className="w-44 rounded border border-accent bg-panel px-1.5 py-0.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>
    );
  }

  // Build groups: only show providers that have models in the curated list
  const groups = Object.entries(models).filter(([, ms]) => ms.length > 0);

  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] text-text-muted">Model</span>
      <select
        value={selectValue}
        onChange={handleSelectChange}
        disabled={disabled}
        className="rounded border border-border bg-panel px-1.5 py-0.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
      >
        {groups.map(([provider, ms]) => {
          const hasKey = providers[provider] ?? false;
          const label = formatProvider(provider);
          return (
            <optgroup key={provider} label={hasKey ? label : `${label} 🔑`}>
              {ms.map((m) => (
                <option key={m} value={m}>
                  {hasKey ? m : `${m} (no key)`}
                </option>
              ))}
            </optgroup>
          );
        })}
        {!isKnown && value && (
          <optgroup label="Current">
            <option value={value}>{value}</option>
          </optgroup>
        )}
        <optgroup label="─────────">
          <option value={CUSTOM_SENTINEL}>Custom model…</option>
        </optgroup>
      </select>
    </div>
  );
}
