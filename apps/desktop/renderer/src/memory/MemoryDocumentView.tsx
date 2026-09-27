import { ChatMarkdownContent } from "../chat/ChatMarkdownContent";
import type { RoleMemoryDocumentName, RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { MemoryFrame, MemoryReadError, MemoryStatusLine, memoryStatusText } from "./MemoryStatus";
import type { MemoryReadState } from "./useMemoryRead";

type MemoryDocumentViewProps = {
  name: RoleMemoryDocumentName;
  documents: MemoryReadState<RoleMemoryDocumentsPayload>;
};

/** Read-only Markdown of one memory document, with distinct loading, empty, missing and error states. */
export function MemoryDocumentView({ name, documents }: MemoryDocumentViewProps) {
  const document = documents.value?.documents.find((item) => item.name === name);
  return <MemoryFrame label={name}>
    {documents.loading ? <MemoryStatusLine text={memoryStatusText.loading} />
      : documents.error ? <MemoryReadError error={documents.error} />
      : document?.status === "error" ? <MemoryReadError error={document.error} />
      : !document || document.status === "missing" ? <MemoryStatusLine text={memoryStatusText.documentMissing} />
      : document.status === "empty" ? <MemoryStatusLine text={memoryStatusText.documentEmpty} />
      : <ChatMarkdownContent content={document.content} />}
  </MemoryFrame>;
}
