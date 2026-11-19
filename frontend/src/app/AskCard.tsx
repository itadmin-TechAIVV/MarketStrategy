import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AnswerMap, Ask } from "../api";
import { IconArrowRight, IconCheck, IconChat } from "../components/Icons";

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

  const n = ask.questions.length;

  return (
    <div className="ask">
      <div className="ask-head">
        <IconChat size={15} /> {n > 1 ? `${n} quick questions` : "Quick question"}
      </div>
      <div className="ask-body">
        {ask.intro && (
          <div className="md" style={{ color: "var(--text-2)" }}>
            <ReactMarkdown>{ask.intro}</ReactMarkdown>
          </div>
        )}
        {ask.questions.map((q, i) => (
          <div key={q.id} className="ask-q">
            <div className="ask-q-text md">
              {n > 1 && <span className="ask-q-num">{i + 1}.</span>}
              <ReactMarkdown>{q.text}</ReactMarkdown>
            </div>
            {q.options.length > 0 && (
              <div className="opts" role={q.multi_select ? "group" : "radiogroup"}>
                {q.options.map((opt) => {
                  const on = answers[q.id].selected.includes(opt);
                  return (
                    <button
                      type="button"
                      key={opt}
                      role={q.multi_select ? "checkbox" : "radio"}
                      aria-checked={on}
                      className={`opt ${on ? "on" : ""}`}
                      onClick={() => toggle(q.id, opt, q.multi_select)}
                    >
                      <span className="tick">{on && <IconCheck size={11} strokeWidth={3} />}</span>
                      {opt}
                    </button>
                  );
                })}
              </div>
            )}
            {(q.allow_free_text || q.options.length === 0) && (
              <input
                className="input"
                placeholder={q.options.length ? "Add detail or a correction (optional)" : "Your answer"}
                value={answers[q.id].text}
                onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: { ...a[q.id], text: e.target.value } }))}
              />
            )}
          </div>
        ))}
      </div>
      <div className="ask-foot">
        <span className="muted small">Suggested answers are pre-selected.</span>
        <button className="btn primary" onClick={submit}>
          Send answers <IconArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
