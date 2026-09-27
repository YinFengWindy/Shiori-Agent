import { ChatMarkdownContent } from "../chat/ChatMarkdownContent";
import type { RoleMemoryDocument, RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { MemoryFrame, MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";

type MemoryDocumentViewProps = {
  name: RoleMemoryDocument["name"];
  documents: { value: RoleMemoryDocumentsPayload | null; loading: boolean; error: string };
};

/** Read-only Markdown of one memory document, with distinct loading, empty, missing and error states. */
export function MemoryDocumentView({ name, documents }: MemoryDocumentViewProps) {
  const document = documents.value?.documents.find((item) => item.name === name);
  return <MemoryFrame label={name}>
    <p className="m-0 text-caption font-medium text-ink-muted">{name}</p>
    {documents.loading ? <MemoryStatusLine text={memoryStatusText.loading} />
      : documents.error ? <MemoryReadError error={documents.error} />
      : document?.status === "error" ? <MemoryReadError error={document.error ?? "未知错误"} />
      : !document || document.status === "missing" ? <MemoryStatusLine text={memoryStatusText.documentMissing} />
      : document.status === "empty" ? <MemoryStatusLine text={memoryStatusText.documentEmpty} />
      : <ChatMarkdownContent content={document.content} />}
  </MemoryFrame>;
}
