import { ChatMarkdownContent } from "../chat/ChatMarkdownContent";
import type { RoleMemoryDocumentName, RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { ReadFrame, ReadError, ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import type { ScopedReadState } from "../shared/useScopedRead";

type MemoryDocumentViewProps = {
  name: RoleMemoryDocumentName;
  documents: ScopedReadState<RoleMemoryDocumentsPayload>;
};

/** Read-only Markdown of one memory document, with distinct loading, empty, missing and error states. */
export function MemoryDocumentView({ name, documents }: MemoryDocumentViewProps) {
  const document = documents.value?.documents.find((item) => item.name === name);
  return <ReadFrame label={name}>
    {documents.loading ? <ReadStatusLine text={memoryStatusText.loading} />
      : documents.error ? <ReadError error={documents.error} />
      : document?.status === "error" ? <ReadError error={document.error} />
      : !document || document.status === "missing" ? <ReadStatusLine text={memoryStatusText.documentMissing} />
      : document.status === "empty" ? <ReadStatusLine text={memoryStatusText.documentEmpty} />
      : <ChatMarkdownContent content={document.content} />}
  </ReadFrame>;
}
