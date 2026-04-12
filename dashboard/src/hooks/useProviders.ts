import { useEffect, useState } from "react";
import { fetchProviders, type ProviderMap } from "../api/client";

export type Providers = Record<string, boolean>;

const DEFAULT: Providers = {};

// Module-level cache — shared across all consumers.
let _cache: Providers | null = null;
let _promise: Promise<Providers> | null = null;

async function doFetch(): Promise<Providers> {
  _promise = fetchProviders()
    .then((data: ProviderMap) => {
      _cache = data;
      return data;
    })
    .catch(() => DEFAULT);
  return _promise;
}

/** Call after saving / deleting a key to force a re-fetch on next render. */
export function invalidateProviderCache(): void {
  _cache = null;
  _promise = null;
}

export function useProviders(): Providers {
  const [providers, setProviders] = useState<Providers>(_cache ?? DEFAULT);

  useEffect(() => {
    void doFetch().then(setProviders);
  }, []);

  return providers;
}
