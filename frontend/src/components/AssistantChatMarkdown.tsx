import ReactMarkdown from 'react-markdown'

type Props = {
  content: string
}

/** Renderiza respuestas del asistente con Markdown (negritas, listas, enlaces). */
export function AssistantChatMarkdown({ content }: Props) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
        li: ({ children }) => <li>{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ className, children }) =>
          className ? (
            <code className="mt-2 block overflow-x-auto rounded-md bg-black/[0.06] p-2 font-mono text-xs">
              {children}
            </code>
          ) : (
            <code className="rounded bg-black/[0.06] px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
          ),
        pre: ({ children }) => <pre className="mb-2 overflow-x-auto last:mb-0">{children}</pre>,
        a: ({ href, children }) => (
          <a
            href={href}
            className="font-medium text-primary underline underline-offset-2 hover:no-underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
        h1: ({ children }) => <p className="mb-2 font-semibold text-ink">{children}</p>,
        h2: ({ children }) => <p className="mb-2 font-semibold text-ink">{children}</p>,
        h3: ({ children }) => <p className="mb-1 font-semibold text-ink">{children}</p>,
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
