/**
 * Line-level LCS diff for comparing LLM outputs.
 */

export type DiffType = "equal" | "add" | "remove";

export interface DiffLine {
  type: DiffType;
  text: string;
}

/**
 * Compute a line-level diff between two strings using LCS.
 */
export function diffLines(textA: string, textB: string): DiffLine[] {
  if (textA === textB) {
    return textA.split("\n").map((text) => ({ type: "equal" as const, text }));
  }

  const aLines = textA.split("\n");
  const bLines = textB.split("\n");
  const m = aLines.length;
  const n = bLines.length;

  // Build LCS table
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        aLines[i - 1] === bLines[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  // Backtrack to produce diff
  const result: DiffLine[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aLines[i - 1] === bLines[j - 1]) {
      result.push({ type: "equal", text: aLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.push({ type: "add", text: bLines[j - 1] });
      j--;
    } else {
      result.push({ type: "remove", text: aLines[i - 1] });
      i--;
    }
  }

  return result.reverse();
}

/**
 * Similarity ratio (0–1) based on LCS line count.
 */
export function similarity(textA: string, textB: string): number {
  if (textA === textB) return 1;
  if (!textA && !textB) return 1;
  if (!textA || !textB) return 0;

  const aLines = textA.split("\n");
  const bLines = textB.split("\n");
  const m = aLines.length;
  const n = bLines.length;

  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        aLines[i - 1] === bLines[j - 1]
          ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  return (2 * dp[m][n]) / (m + n);
}
