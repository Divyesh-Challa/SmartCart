import { useParams } from "react-router-dom";
import { marked } from "marked";
import privacy from "../legal/privacy.md?raw";
import terms from "../legal/terms.md?raw";
import pricing from "../legal/pricing.md?raw";
import { Card } from "../components/ui";

// Only our own bundled documents are rendered here, never user content.
const DOCS: Record<string, string> = { privacy, terms, pricing };

export default function LegalPage() {
  const { doc = "" } = useParams();
  const source = DOCS[doc] ?? DOCS.terms;
  return (
    <Card>
      <article
        className="space-y-3 text-sm leading-relaxed [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mt-4 [&_h2]:font-semibold [&_ul]:list-disc [&_ul]:pl-5"
        dangerouslySetInnerHTML={{ __html: marked.parse(source, { async: false }) as string }}
      />
    </Card>
  );
}
