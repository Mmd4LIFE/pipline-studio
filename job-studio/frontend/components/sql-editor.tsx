"use client";

import { sql } from "@codemirror/lang-sql";
import CodeMirror from "@uiw/react-codemirror";

export function SqlEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-[#0a1626]">
      <CodeMirror
        value={value}
        height="280px"
        theme="dark"
        extensions={[sql()]}
        onChange={onChange}
        basicSetup={{ lineNumbers: true, foldGutter: true }}
      />
    </div>
  );
}
