import { useEffect, useState } from "react";
import { fetchModels, type ModelMap } from "../api/client";

const DEFAULT: ModelMap = {};

// Module-level cache — shared across all ModelPicker instances.
let _cache: ModelMap | null = null;
let _promise: Promise<ModelMap> | null = null;

async function doFetch(): Promise<ModelMap> {
  _promise = fetchModels()
    .then((data) => {
      _cache = data;
      return data;
    })
    .catch(() => DEFAULT);
  return _promise;
}

/** Call after saving / deleting a key to force a re-fetch on next render. */
export function invalidateModelCache(): void {
  _cache = null;
  _promise = null;
}

export function useModels(): ModelMap {
  const [models, setModels] = useState<ModelMap>(_cache ?? DEFAULT);

  useEffect(() => {
    void doFetch().then(setModels);
  }, []);

  return models;
}
