import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface LedgerMindConfig {
  storagePath: string;
  mode: "agent" | "core";
  namespace: string;
  maxContextItems: number;
  language: string;
}

interface SearchResult {
  title: string;
  target: string;
  rationale: string;
  score: number;
}

interface MemoryEvent {
  source: string;
  kind: string;
  content: string;
}

async function callLedgerMind(
  method: string,
  args: Record<string, unknown>,
  config: LedgerMindConfig
): Promise<unknown> {
  const payload = JSON.stringify({ method, args });
  try {
    const { stdout } = await execFileAsync("ledgermind-mcp", [
      "call",
      "--path", config.storagePath,
      "--method", method,
      "--args", JSON.stringify(args),
    ], { timeout: 10_000 });
    return JSON.parse(stdout.trim());
  } catch {
    return null;
  }
}

function extractKeywords(text: string): string[] {
  const stopWords = new Set([
    "what", "is", "the", "a", "an", "and", "or", "but", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out", "off",
    "over", "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "can", "will", "just", "don",
    "should", "now", "tell", "me", "about", "do", "you", "know",
    "could", "would", "please", "help", "find", "search", "look", "get",
  ]);

  return text
    .replace(/[^\w\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !stopWords.has(w.toLowerCase()))
    .map((w) => w.toLowerCase());
}

async function searchMemories(
  query: string,
  config: LedgerMindConfig
): Promise<SearchResult[]> {
  const keywords = extractKeywords(query);
  if (keywords.length === 0) return [];

  const results = await callLedgerMind(
    "search_decisions",
    { query, limit: config.maxContextItems, mode: "lite" },
    config
  );

  if (Array.isArray(results) && results.length > 0) {
    return results.map((r: any) => ({
      title: r.title ?? "",
      target: r.target ?? "",
      rationale: r.rationale ?? "",
      score: r.score ?? 0,
    }));
  }

  for (const keyword of keywords.slice(0, 3)) {
    const kwResults = await callLedgerMind(
      "search_decisions",
      { query: keyword, limit: config.maxContextItems, mode: "lite" },
      config
    );
    if (Array.isArray(kwResults) && kwResults.length > 0) {
      return kwResults.map((r: any) => ({
        title: r.title ?? "",
        target: r.target ?? "",
        rationale: r.rationale ?? "",
        score: r.score ?? 0,
      }));
    }
  }

  return [];
}

async function recordEvents(
  prompt: string,
  response: string,
  config: LedgerMindConfig
): Promise<void> {
  await callLedgerMind(
    "process_event",
    { source: "user", kind: "prompt", content: prompt },
    config
  );
  await callLedgerMind(
    "process_event",
    { source: "agent", kind: "result", content: response },
    config
  );
}

export default definePluginEntry({
  id: "ledgermind",
  name: "LedgerMind",
  description: "Autonomous memory management for AI agents",
  register(api) {
    const pluginConfig: LedgerMindConfig = {
      storagePath: "~/.ledgermind",
      mode: "agent",
      namespace: "default",
      maxContextItems: 5,
      language: "russian",
      ...((api as any).config ?? {}),
    };

    // --- BEFORE MODEL: inject relevant memories ---
    api.on("before_prompt_build", async (event) => {
      try {
        const prompt = event.prompt ?? "";
        if (!prompt) return;

        const memories = await searchMemories(prompt, pluginConfig);
        if (memories.length === 0) return;

        const contextBlock = [
          "[LEDGERMIND KNOWLEDGE BASE ACTIVE]",
          ...memories.map(
            (m) =>
              `- ${m.title} (${m.target}): ${m.rationale} [score: ${m.score}]`
          ),
        ].join("\n");

        return {
          appendSystemContext: contextBlock,
        };
      } catch {
        return undefined;
      }
    });

    // --- AFTER MODEL: capture summary ---
    api.on("agent_end", async (event) => {
      try {
        const messages = event.messages ?? [];
        if (messages.length === 0) return;

        const lastUser = [...messages]
          .reverse()
          .find((m: any) => m.role === "user");
        const lastAssistant = [...messages]
          .reverse()
          .find((m: any) => m.role === "assistant");

        if (!lastUser || !lastAssistant) return;

        const prompt =
          typeof lastUser.content === "string"
            ? lastUser.content
            : JSON.stringify(lastUser.content);
        const response =
          typeof lastAssistant.content === "string"
            ? lastAssistant.content
            : JSON.stringify(lastAssistant.content);

        if (!prompt || !response) return;

        await recordEvents(prompt, response, pluginConfig);
      } catch {
        // silent
      }
    });
  },
});
