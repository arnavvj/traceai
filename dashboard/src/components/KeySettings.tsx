import { useCallback, useEffect, useState } from "react";
import { clearAllTraces, deleteKey, fetchKeys, setKey, type KeyStatus } from "../api/client";
import { invalidateProviderCache } from "../hooks/useProviders";
import { invalidateModelCache } from "../hooks/useModels";
import type { ThemeMode } from "../hooks/useTheme";

interface Props {
  open: boolean;
  onClose: () => void;
  theme: ThemeMode;
  onThemeChange: (mode: ThemeMode) => void;
  onDataCleared: () => void;
}

interface ClearProps {
  onCleared: () => void;
}

/** Capitalize a provider name for display. */
function formatLabel(provider: string): string {
  const special: Record<string, string> = {
    openai: "OpenAI",
    anthropic: "Anthropic",
    deepseek: "DeepSeek",
    groq: "Groq",
    openrouter: "OpenRouter",
    fireworks: "Fireworks",
    perplexity: "Perplexity",
  };
  return special[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1);
}

function ClearDataSection({ onCleared }: ClearProps) {
  const [confirm, setConfirm] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);

  async function handleClear() {
    setClearing(true);
    try {
      const { deleted } = await clearAllTraces();
      setCleared(deleted);
      setConfirm(false);
      onCleared();
    } finally {
      setClearing(false);
    }
  }

  if (cleared !== null) {
    return (
      <p className="text-[11px] text-text-muted">
        Deleted {cleared} trace{cleared !== 1 ? "s" : ""}.
      </p>
    );
  }

  if (!confirm) {
    return (
      <button
        onClick={() => setConfirm(true)}
        className="flex items-center gap-1.5 rounded border border-red-300 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
          <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
        Clear all trace history
      </button>
    );
  }

  return (
    <div className="rounded border border-red-300 bg-red-50 p-3 dark:border-red-800 dark:bg-red-900/10">
      <p className="mb-2 text-xs font-semibold text-red-700 dark:text-red-400">
        This will permanently delete all traces and spans. There is no undo.
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => void handleClear()}
          disabled={clearing}
          className="rounded bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
        >
          {clearing ? "Deleting…" : "Yes, delete everything"}
        </button>
        <button
          onClick={() => setConfirm(false)}
          className="rounded px-3 py-1 text-xs text-text-secondary hover:text-text-primary"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export function KeySettings({ open, onClose, theme, onThemeChange, onDataCleared }: Props) {
  const [keys, setKeys] = useState<KeyStatus[]>([]);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [clearing, setClearing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [newProvider, setNewProvider] = useState("");

  const load = useCallback(() => {
    void fetchKeys().then(setKeys).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  if (!open) return null;

  async function handleSave(provider: string) {
    const val = inputs[provider]?.trim();
    if (!val) return;
    setSaving(provider);
    setError(null);
    setSuccess(null);
    try {
      await setKey(provider, val);
      invalidateProviderCache();
      invalidateModelCache();
      setSuccess(`${formatLabel(provider)} key saved`);
      setInputs((prev) => ({ ...prev, [provider]: "" }));
      load(); // refresh status
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save key");
    } finally {
      setSaving(null);
    }
  }

  async function handleClearKey(provider: string) {
    setClearing(provider);
    setError(null);
    setSuccess(null);
    try {
      await deleteKey(provider);
      invalidateProviderCache();
      invalidateModelCache();
      setSuccess(`${formatLabel(provider)} key cleared`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear key");
    } finally {
      setClearing(null);
    }
  }

  function handleAddProvider() {
    const name = newProvider.trim().toLowerCase().replace(/\s+/g, "");
    if (!name) return;
    // Add a blank entry if not already present
    if (!keys.find((k) => k.provider === name)) {
      setKeys((prev) => [...prev, { provider: name, is_set: false, source: "none" }]);
    }
    setNewProvider("");
  }

  // Split into configured (keys set) and unconfigured
  const configured = keys.filter((k) => k.is_set);
  const unconfigured = keys.filter((k) => !k.is_set);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg border border-border bg-sidebar p-5 shadow-xl max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">API Keys</h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-secondary"
          >
            ✕
          </button>
        </div>

        <p className="mb-4 text-[11px] text-text-muted">
          Keys are saved locally to <span className="font-mono">~/.traceai/config.toml</span> and
          used for replay. Environment variables (
          <span className="font-mono">PROVIDER_API_KEY</span>) take priority if set.
        </p>

        {error && (
          <div className="mb-3 rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-3 rounded border border-green-300 bg-green-50 px-2 py-1 text-xs text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400">
            {success}
          </div>
        )}

        {/* Configured providers — full card with status */}
        {configured.length > 0 && (
          <div className="flex flex-col gap-3">
            {configured.map((status) => (
              <div key={status.provider} className="rounded border border-border/60 bg-panel/50 p-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs font-medium text-text-primary">
                    {formatLabel(status.provider)}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-green-400">
                      configured ({status.source})
                    </span>
                    {status.source === "config" && (
                      <button
                        onClick={() => void handleClearKey(status.provider)}
                        disabled={clearing === status.provider}
                        title="Remove saved key from config"
                        className="text-[10px] text-red-400 hover:text-red-600 disabled:opacity-50 dark:text-red-500 dark:hover:text-red-400"
                      >
                        {clearing === status.provider ? "…" : "Clear"}
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <input
                    type="password"
                    value={inputs[status.provider] ?? ""}
                    onChange={(e) =>
                      setInputs((prev) => ({ ...prev, [status.provider]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handleSave(status.provider);
                    }}
                    placeholder="Enter new key to replace"
                    className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <button
                    onClick={() => void handleSave(status.provider)}
                    disabled={saving === status.provider || !inputs[status.provider]?.trim()}
                    className="rounded bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-40"
                  >
                    {saving === status.provider ? "…" : "Save"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Unconfigured providers — compact cards */}
        {unconfigured.length > 0 && (
          <div className="mt-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
              Available providers
            </div>
            <div className="flex flex-col gap-2">
              {unconfigured.map((status) => (
                <div key={status.provider} className="rounded border border-border/40 bg-panel/30 p-2.5">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-xs font-medium text-text-secondary">
                      {formatLabel(status.provider)}
                    </span>
                    <span className="text-[10px] text-text-muted">not set</span>
                  </div>
                  <div className="flex gap-1.5">
                    <input
                      type="password"
                      value={inputs[status.provider] ?? ""}
                      onChange={(e) =>
                        setInputs((prev) => ({ ...prev, [status.provider]: e.target.value }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleSave(status.provider);
                      }}
                      placeholder="Paste API key…"
                      className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                    <button
                      onClick={() => void handleSave(status.provider)}
                      disabled={saving === status.provider || !inputs[status.provider]?.trim()}
                      className="rounded bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-40"
                    >
                      {saving === status.provider ? "…" : "Save"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Add custom provider */}
        <div className="mt-3 border-t border-border/40 pt-3">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
            Custom provider
          </div>
          <div className="flex items-center gap-1.5">
            <input
              value={newProvider}
              onChange={(e) => setNewProvider(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAddProvider();
              }}
              placeholder="e.g. cohere, ai21, anyscale…"
              className="flex-1 rounded border border-border bg-background px-2 py-1 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              onClick={handleAddProvider}
              disabled={!newProvider.trim()}
              className="rounded bg-panel px-3 py-1 text-xs font-medium text-text-secondary ring-1 ring-border hover:text-text-primary disabled:opacity-40"
            >
              + Add
            </button>
          </div>
        </div>

        <div className="mt-4 border-t border-border/60 pt-3">
          <h3 className="mb-2 text-xs font-semibold text-text-primary">Theme</h3>
          <div className="flex gap-1">
            {(["dark", "light", "system"] as const).map((m) => (
              <button
                key={m}
                onClick={() => onThemeChange(m)}
                className={`rounded px-3 py-1 text-xs capitalize ${
                  theme === m
                    ? "bg-accent text-white"
                    : "bg-background text-text-secondary hover:text-text-primary"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 border-t border-border/60 pt-3">
          <h3 className="mb-2 text-xs font-semibold text-text-primary">Data</h3>
          <ClearDataSection onCleared={onDataCleared} />
        </div>

        <p className="mt-4 text-[10px] text-text-muted">
          Or use env vars:{" "}
          <span className="font-mono">OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-...</span>
        </p>
      </div>
    </div>
  );
}
