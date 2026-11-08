"""TEST DOUBLE: a minimal Ollama-compatible HTTP server for end-to-end tests.

It lets the e2e suite exercise MEDI-GENIUS's real Ollama provider code path
(HTTP, NDJSON streaming, JSON-schema output) without downloading a model.
It is never used by the application itself.

    python tests/e2e/fake_ollama.py --port 11500
"""
from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANSWER = """## The mitral valve

From your documents: oxygenated blood crosses the **mitral (bicuspid) valve** from the left atrium into the left ventricle [1].

- The left ventricle has the thickest myocardium because it pumps into the systemic circulation [1].

### Additional explanation (AI-generated)
Think of the valves as one-way doors that keep blood moving forward.

*Try asking: "What happens when the mitral valve is stenosed?"*"""


def quiz(n_sources: int) -> dict:
    s2 = min(2, n_sources)
    return {"questions": [
        {"type": "sba", "prompt": "Which valve separates the left atrium from the left ventricle?",
         "options": ["Tricuspid valve", "Mitral valve", "Pulmonary valve", "Aortic valve", "Eustachian valve"],
         "correct_options": [1], "true_false_answer": "n/a", "accepted_answers": [], "model_answer": "",
         "key_points": [], "explanation": "Blood crosses the mitral (bicuspid) valve into the left ventricle [1].",
         "topic": "Heart valves", "source_ids": [1], "image_ref": ""},
        {"type": "true_false", "prompt": "The SA node is the natural pacemaker of the heart.", "options": [],
         "correct_options": [], "true_false_answer": "true", "accepted_answers": [], "model_answer": "",
         "key_points": [], "explanation": "The SA node is described as the natural pacemaker.", "topic": "Conduction",
         "source_ids": [s2], "image_ref": ""},
        {"type": "short", "prompt": "Explain why the left ventricle has the thickest myocardium.", "options": [],
         "correct_options": [], "true_false_answer": "n/a", "accepted_answers": [],
         "model_answer": "It must generate high pressure to perfuse the systemic circulation.",
         "key_points": ["high pressure", "systemic circulation"], "explanation": "See [1].", "topic": "Heart valves",
         "source_ids": [1], "image_ref": ""},
    ]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            self._json({"models": [{"name": "llama3.1:8b"}, {"name": "llava:7b"}]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = payload["messages"][-1]["content"]
        n = len(re.findall(r'<source id="\d+"', prompt)) or 1
        fmt = payload.get("format")
        if isinstance(fmt, dict):
            props = fmt.get("properties", {})
            if "questions" in props:
                content = json.dumps(quiz(n))
            elif "cards" in props:
                content = json.dumps({"cards": [{"front": "Which valve lies between the left atrium and ventricle?",
                                                 "back": "The mitral (bicuspid) valve.", "topic": "Heart valves",
                                                 "source_id": 1}]})
            else:
                idx = [int(i) for i in re.findall(r'<item index="(\d+)"', prompt)]
                content = json.dumps({"grades": [{"question_index": i, "score": 0.75, "feedback": "Covers the key idea.",
                                                  "missing_points": []} for i in idx]})
            self._json({"model": payload["model"], "message": {"role": "assistant", "content": content}, "done": True})
            return
        text = ANSWER if "images" not in payload["messages"][-1] else "The diagram shows labels Aorta and Left Ventricle [1]."
        if not payload.get("stream"):
            self._json({"model": payload["model"], "message": {"role": "assistant", "content": text}, "done": True})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for i in range(0, len(text), 24):
            self.wfile.write((json.dumps({"message": {"content": text[i:i + 24]}, "done": False}) + "\n").encode())
            self.wfile.flush()
        self.wfile.write((json.dumps({"model": payload["model"], "message": {"content": ""}, "done": True,
                                      "done_reason": "stop", "eval_count": 42}) + "\n").encode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11500)
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
