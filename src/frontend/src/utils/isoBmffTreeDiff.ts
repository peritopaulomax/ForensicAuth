export type TreeNode = {
  id: string;
  type: string;
  size: number;
  offset: number;
  end?: number;
  path: string;
  description?: string;
  fields?: Record<string, unknown>;
  children?: TreeNode[];
};

export type NodeDiffStatus = "only_a" | "only_b" | "size_diff" | "same";

export type TreeDiffSummary = {
  onlyA: number;
  onlyB: number;
  sizeDiff: number;
  same: number;
};

export type TreeDiffResult = {
  leftStatus: Map<string, NodeDiffStatus>;
  rightStatus: Map<string, NodeDiffStatus>;
  summary: TreeDiffSummary;
};

type FlatNode = { type: string; size: number; offset: number };

export function flattenIsoBmffTree(nodes: TreeNode[]): Map<string, FlatNode> {
  const map = new Map<string, FlatNode>();

  function walk(node: TreeNode) {
    map.set(node.path, { type: node.type, size: node.size, offset: node.offset });
    for (const child of node.children || []) walk(child);
  }

  for (const root of nodes) walk(root);
  return map;
}

export function computeIsoBmffTreeDiff(treeA: TreeNode[], treeB: TreeNode[]): TreeDiffResult {
  const flatA = flattenIsoBmffTree(treeA);
  const flatB = flattenIsoBmffTree(treeB);
  const leftStatus = new Map<string, NodeDiffStatus>();
  const rightStatus = new Map<string, NodeDiffStatus>();

  let onlyA = 0;
  let onlyB = 0;
  let sizeDiff = 0;
  let same = 0;

  for (const [path, nodeA] of flatA) {
    const nodeB = flatB.get(path);
    if (!nodeB) {
      leftStatus.set(path, "only_a");
      onlyA += 1;
      continue;
    }
    if (nodeA.size !== nodeB.size) {
      leftStatus.set(path, "size_diff");
      rightStatus.set(path, "size_diff");
      sizeDiff += 1;
    } else {
      leftStatus.set(path, "same");
      rightStatus.set(path, "same");
      same += 1;
    }
  }

  for (const path of flatB.keys()) {
    if (!flatA.has(path)) {
      rightStatus.set(path, "only_b");
      onlyB += 1;
    }
  }

  return {
    leftStatus,
    rightStatus,
    summary: { onlyA, onlyB, sizeDiff, same },
  };
}

export function collectRootPaths(nodes: TreeNode[]): string[] {
  return nodes.map((n) => n.path);
}

export const DIFF_ROW_BG: Record<NodeDiffStatus, string> = {
  only_a: "#fef2f2",
  only_b: "#eff6ff",
  size_diff: "#fffbeb",
  same: "transparent",
};

export const DIFF_ROW_BORDER: Record<NodeDiffStatus, string> = {
  only_a: "#fecaca",
  only_b: "#bfdbfe",
  size_diff: "#fde68a",
  same: "transparent",
};
