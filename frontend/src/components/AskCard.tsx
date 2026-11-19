import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AnswerMap, Ask } from "../api";

export default function AskCard({ ask, onSubmit }: { ask: Ask; onSubmit: (a: AnswerMap, summary: string) => void }) {
  const [answers, setAnswers] = useState<AnswerMap>(() =>
    Object.fromEntries(ask.questions.map((q) => [q.id, { selected: q.options.length ? [q.options[0]] : [], text: "" }])),
  );

  function toggle(qid: string, option: string, multi: boolean) {
    setAnswers((a) => {
      const cur = a[qid];
      const selected = multi
        ? cur.selected.includes(option)
          ? cur.selected.filter((o) => o !== option)
          : [...cur.selected, option]
        : [option];
      return { ...a, [qid]: { ...cur, selected } };
    });
  }

  function submit() {
    const summary = ask.questions
      .map((q) => {
        const a = answers[q.id];
        const parts = [...a.selected, ...(a.text.trim() ? [a.text.trim()] : [])];
        return ask.questions.length > 1 ? `**${q.text}** ${parts.join("; ")}` : parts.join("; ");
      })
      .join("\n\n");
    onSubmit(answers, summary);
  }

  return (
    <div className="ask-card card">
      {ask.intro && (
        <div className="ask-intro">
          <ReactMarkdown>{ask.intro}</ReactMarkdown>
        </div>
      )}
      {ask.questions.map((q) => (
        <fieldset key={q.id} className="question">
          <legend>
            <ReactMarkdown>{q.text}</ReactMarkdown>
          </legend>
          <div className="options">
            {q.options.map((opt) => (
              <button
                type="button"
                key={opt}
                className={`option ${answers[q.id].selected.includes(opt) ? "selected" : ""}`}
                onClick={() => toggle(q.id, opt, q.multi_select)}
              >
                {opt}
              </button>
            ))}
          </div>
          {(q.allow_free_text || q.options.length === 0) && (
            <input
              placeholder="Add detail or a correction (optional)"
              value={answers[q.id].text}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: { ...a[q.id], text: e.target.value } }))}
            />
          )}
        </fieldset>
      ))}
      <button className="btn primary" onClick={submit}>
        Send answers
      </button>
    </div>
  );
}
