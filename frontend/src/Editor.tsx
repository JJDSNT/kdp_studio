// The manuscript editor: CodeMirror over the section's exact text. What the
// author types is what is saved, byte for byte (ADR 0006).
import { useEffect, useRef } from "react";
import { EditorView, basicSetup } from "codemirror";
import { markdown } from "@codemirror/lang-markdown";

interface Props {
  value: string;
  onChange: (text: string) => void;
}

export default function Editor({ value, onChange }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const changed = useRef(onChange);
  changed.current = onChange;

  useEffect(() => {
    if (!host.current) return;
    view.current = new EditorView({
      doc: value,
      parent: host.current,
      extensions: [
        basicSetup,
        markdown(),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) changed.current(update.state.doc.toString());
        }),
      ],
    });
    return () => view.current?.destroy();
    // The editor owns the text once open; a new `value` comes with a new key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div className="editor" ref={host} />;
}
