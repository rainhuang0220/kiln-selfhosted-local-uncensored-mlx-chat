import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { splitOpenFence } from "../lib/markdown";
import "highlight.js/styles/github-dark.css";

function urlTransform(url: string): string {
  try {
    const u = new URL(url, window.location.origin);
    if (!["http:", "https:", "mailto:"].includes(u.protocol)) return "";
    return url;
  } catch {
    return "";
  }
}

const components: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

export function Markdown({ text, streaming }: { text: string; streaming?: boolean }) {
  const { complete, openFence } = streaming
    ? splitOpenFence(text)
    : { complete: text, openFence: "" };
  const fenceBody = openFence.replace(/^```[^\n]*\n?/, "");
  return (
    <div className="md">
      {complete ? (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
          urlTransform={urlTransform}
          components={components}
        >
          {complete}
        </ReactMarkdown>
      ) : null}
      {openFence ? <pre>{fenceBody}</pre> : null}
      {streaming ? <span className="caret" aria-hidden="true" /> : null}
    </div>
  );
}
