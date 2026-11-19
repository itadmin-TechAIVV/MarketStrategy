import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import type { AnswerMap, Ask, TranscriptItem } from "../api";
import { IconCheck } from "../components/Icons";
import { LogoMark } from "../components/Logo";
import AskCard from "./AskCard";
import type { LiveState } from "./ChatView";

interface Props {
  transcript: TranscriptItem[];
  live: LiveState;
  busy: boolean;
  error: string;
  pendingAsk: Ask | null;
  onAnswer: (answers: AnswerMap, summary: string) => void;
}

function Ai({ children }: { children: React.ReactNode }) {
  return (
    <div className="m-ai">
      <LogoMark size={30} />
      <div className="m-ai-body">{children}</div>
    </div>
  );
}

export default function Thread({ transcript, live, busy, error, pendingAsk, onAnswer }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [transcript.length, live.text, live.activity, live.crawl, pendingAsk, error]);

  const lastAskSeq = [...transcript].reverse().find((i) => i.kind === "ask")?.seq;

  return (
    <div className="thread">
      <div className="thread-inner">
        {transcript.map((item, i) => {
          if (item.kind === "ask" && item.ask) {
            if (pendingAsk && item.seq === lastAskSeq) return null;
            return (
              <Ai key={i}>
                <div className="m-ask-past">
                  <div className="m-label">Asked you</div>
                  {item.ask.intro && <div className="md"><ReactMarkdown>{item.ask.intro}</ReactMarkdown></div>}
                  {item.ask.questions.map((q) => (
                    <div key={q.id} className="md"><ReactMarkdown>{q.text}</ReactMarkdown></div>
                  ))}
                </div>
              </Ai>
            );
          }
          if (item.role === "user") {
            return (
              <div key={i} className={`m-user ${item.kind === "answer" ? "answer" : ""}`}>
                {item.kind === "answer" && (
                  <div className="m-label"><IconCheck size={13} /> Your answer</div>
                )}
                <div className="md"><ReactMarkdown>{item.text ?? ""}</ReactMarkdown></div>
              </div>
            );
          }
          return (
            <Ai key={i}>
              <div className="md"><ReactMarkdown>{item.text ?? ""}</ReactMarkdown></div>
            </Ai>
          );
        })}

        {(busy || live.text) && (
          <Ai>
            {live.text && <div className="md"><ReactMarkdown>{live.text}</ReactMarkdown></div>}
            {busy && (live.crawl || live.activity) ? (
              <span className="activity"><span className="spinner" /> {live.crawl ?? live.activity}</span>
            ) : busy && !live.text ? (
              <span className="typing"><i /><i /><i /></span>
            ) : null}
          </Ai>
        )}

        {pendingAsk && !busy && (
          <Ai>
            <AskCard ask={pendingAsk} onSubmit={onAnswer} />
          </Ai>
        )}
        {error && <div className="alert error">{error}</div>}
        <div ref={endRef} />
      </div>
    </div>
  );
}
