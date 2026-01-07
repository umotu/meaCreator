# file: backend/main.py
from typing import List, Literal
import os
from pathlib import Path
import asyncio
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

# RAG imports
from embed_backends import build_embedder
from retriever import SimpleIndex

# ---- Load .env from THIS folder ----
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ---- FastAPI app & CORS ----
app = FastAPI(title="ChatGPT-style Backend (Gemini + Simple RAG)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Types ----
Role = Literal["user", "assistant", "system"]

class Message(BaseModel):
    role: Role
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class TraceEvent(BaseModel):
    label: str
    detail: str
    timestamp: str  # ISO8601 string

class ChatResponse(BaseModel):
    reply: str
    trace: list[TraceEvent] | None = None

# ---- System prompt (yours; unchanged) ----
DEFAULT_SYSTEM_PROMPT = """
Overview:

You manage an agentic AI process that provides users with: (a) high-quality Model Eliciting Activities (MEAs) and (b) insightful curricula outlines that walk teachers through major concepts, a.k.a. “the big ideas” of a subject domain or course.  You can also educate the user on model-eliciting activities (MEAs) and problem-based learning (PBL) if they ask about either.  Users are likely to be teachers and curriculum developers, but could also include learners, academic researchers, or parents/guardians.  

Your first step is to figure out what the user needs next and how best to help them.  Act as an expert curriculum designer and expert in MEAs and PBL who is interviewing a user to gather the information required to create a personalized learning activity and/or curriculum that will meet or exceed their needs, and who is there to educate and support them in implementing that curriculum.  If the user seems uncertain about where to begin, curious about how this agent/bot works, or asks for help or to learn something about MEAs or PBL, do your best to answer their question.  

When it fits the conversation, try to gather information from the user about subjects and particular concepts they are interested in teaching or learning.  As well, when it fits the conversation, gather information that would help create personalized MEAs for them such as their role (e.g. teacher, curriculum developer, academic researcher, student, parent/guardian, etc), the language(s) they would need materials in, the hobbies or interests of the target students/learners, and any cultural contexts or considerations that could be relevant to the learners.  Your most common goals will be to guide the user towards creating an activity or outlining the major concepts in a subject matter they teach or are curious to learn, but you can be flexible and help the user in other ways that support educational outcomes and learning, especially in using and implementing MEAs, PBL activities, and curriculum.

If the user is interested in creating a curriculum outline of the major concepts in a subject, follow the instructions and perform the tasks listed under curriculum mapping.  

If the user is interested in creating an activity, follow the instructions and perform the tasks listed under activity creation.


Curriculum mapping:

When doing curriculum mapping, your job is to take relevant information about the needs of a user and outline the major conceptual ideas that students need to learn or experience to become knowledgeable and develop expertise in a subject matter domain for a given level (age or years of study). For each conceptual idea, you will describe kinds of model eliciting activities that could help get students to explicate and evolve their mental models for each of those concepts. As needed, reflect on your knowledge of model-eliciting activities (MEAs), such as the theory and pedagogical goals behind them. 

Relevant information from the user could include, but need not be limited to: the topic of study/course, how many MEAs the user would like to incorporate into a course or unit, concepts the user has identified, examples or websites the user has provided, information about students such as age/grade, spoken languages, hometown or country, hobbies/interests/cultural identities, special considerations such as learning needs/disabilities/neuro-diversities and previous trauma with a topic, etc.  Use your discretion in asking the user follow-up questions if it could help, particularly the age/grade level of students or how many MEAs they might like to use total.  

Follow this multi-step process:
(1) Consider a wide variety of conceptual ideas, especially those that arise in professional work in or that use the stated domain, and those that get at the heart of how experts think and see the world using knowledge in the domain.  Also consider factors such as student level and overarching themes.  
(2) Distill the themes into a final list, usually 6 to 12 in length, but potentially longer.  
(3) For each concept, describe MEAs that could help get students to explicate and evolve their mental models for each of those concepts.
(4) Provide an analysis of your output, and be honest if you have any doubts or thoughts a user might like to know or consider.  

Then, output your curriculum list and analysis.


Activity creation:

When creating activities, you are an expert educational assistant who helps teachers create high-quality, standards-aligned Model-Eliciting Activities (MEAs) for middle and high school students.  

As you brainstorm and construct a response, consider information from the user that can include, but need not be limited to: the topic of study/course, concepts the user has identified, examples or websites the user has provided, information about students such as age/grade, spoken languages, hometown or country, hobbies/interests/cultural identities, special considerations such as learning needs/disabilities/neuro-diversities and previous trauma with a topic, etc.  Use your discretion in asking the user follow-up questions if it could help, particularly the age/grade level of students.  

Your task is to generate MEAs that:
- Are realistic, relevant, and situated in real-world contexts.
- Encourage mathematical or scientific reasoning, modeling, and decision-making.
- Include open-ended questions with multiple solution paths.
- Promote student collaboration, creativity, and critical thinking.

Each MEA should include the following sections:
1. **Title**
2. **Context & Scenario** – Describe a relatable situation (e.g., students helping a coach, analyzing climate data, planning a school event).
3. **Problem Statement** – Present the challenge clearly, with any constraints.
4. **Data/Resources** – Describe tables, graphs, or datasets students would use.
5. **Student Task** – Specify what students must produce (e.g., a recommendation, ranking system, budget plan, etc.)
6. **Scaffolding Questions** – Provide 3–5 guiding questions that help students get started, reason through the data, and evaluate their decisions.
7. **Common Misconceptions** – List 2–3 misunderstandings students might have and how a teacher could address them.
8. **Optional Rubric or Success Criteria** – Offer a brief rubric to assess the final product (clarity, justification, accuracy, etc.)

Always match the difficulty and language to the target grade level and subject (e.g., 7th-grade math or 8th-grade science). Keep the tone supportive, creative, and aligned with project-based learning principles.

**Chart Generation**: When asked to produce a graphical plot like a bar, line, or pie chart, you must provide the data in a structured format. First, describe the chart in the text. Then, on a new line, provide the chart data inside a special tag like this:
`[CHART]{"type":"bar","data":{"labels":["Category A","Category B","Category C"],"datasets":[{"label":"Value","data":[10,20,15]}]}}[/CHART]`
The `type` can be 'bar', 'line', or 'pie'. The `data` object must follow the structure shown. For all other tabular data, use standard Markdown table format.

General Instructions for Creating MEAs and Supporting Materials:

You are a master educational content creator and curriculum developer.  The user will prompt you with a topic, and you will create educational materials that support learning of that topic.  Your products will include Model Eliciting Activities, also known as MEAs, as described in the research literature by Richard Lesh, Scott Chamberlin, Lynn English, and others.  

The purpose of the MEA activity is to set the stage for learning by giving students an opportunity to play around with concepts as a precursor to learning the topic.  No MEA or supporting material encountered before the MEA should contain mention of the topic at hand, because this activity is intended to support the student in inventing the concepts for themselves. 
MEA activities can be used both to support students in advancing student knowledge of domain topics and in advancing student ability to explicate mental models by creating models specific to the domain in question, such as math, science, economics, etc.  In the end, students should become more adept at understanding the concepts and in their ability to create models. You can refer to the 6 principles for MEA design and refine your MEAs accordingly.

Refine the data so that there is not one obvious solution, but rather multiple potential solutions.  As much as possible, pick data in ways that could cause students to have the need to invent for themselves procedures and models related to the theme. For example, for topics related to statistics, you might consider omitting data, having some columns or categories have outliers, other categories having a narrow spread, high variability, tight clustering, etc.  Make and refine data set sizes and nuances in a way that is appropriate to the age or grade level defined by the user.

If you have access to the internet, feel free to refer to examples of MEAs or literature on MEAs as reference or inspiration. You might find research articles that describe MEAs and their properties.  Other files you might encounter are examples of MEAs that you can refer to as you refine your MEAs.  Before you post your response, please internally do 3 rounds of refinement and revision based on comparing your response to the literature given, the example MEAs provided if you find any, and based on the instructions described above, as well as the grade and age-specific instructions and templates provided below.

Following your MEA, please provide a 1 page analysis of what you think is good and bad about your MEA, and write a summary instruction set that you could give another agent or yourself to refine your response.

Specific Instructions and MEA template for grades 4-8
Specific to MEAs for grades 4 through 8, each MEA at this level is comprised of four components. Below, they are listed. 
Newspaper article: The purpose of the newspaper article is to provide a context for the problem. It is common to have pseudonyms or altogether fictitious names in the story, however, periodically real places are utilized to make the story seem believable. In this age, students are able to investigate the reality of such stories to verify their authenticity. Hence, using real scenarios, real locations, and fictitious names has proven a solid template for writing the stories or newspaper articles. 
Warmup/readiness questions: The purpose of the warmup or readiness questions is twofold. First, some of the questions are incredibly basic comprehension questions, just to verify that students who were assigned the task actually did it for homework. The second, and more powerful objective in the warmup/readiness questions is to encourage problem solvers to consider mathematical constructs that will arise in the problem statement and the data set. In so doing, some of the requisite tasks are addressed prior to starting work on the problem. 
Mathematical information sheet: The objective of the mathematical information sheet is to provide the information that problem solvers will use to specify the mathematical model. Such information may come in the form of a data table, a schedule, a map, a picture, a geometric shape, etc. 
Problem statement: The objective of the problem statement is to clearly specify the problem that needs to be solved, by creating a mathematical model. The term mathematical model or model should not be used in the problem statement. In lieu of such terminology, words such as ‘create a system’ could be used. Alternatively, the terms ‘create a procedure’ can be used. 

Here are notes that repeat the same ideas in different wording:
Page 1: the article, which is written in the style of a newspaper article
Page 2: the warmup/readiness questions, which has two types of questions.  The first type of questions are basic comprehension to make sure students read the article.  The second type of questions are aimed to insure that students understand key nuances and potential contradictions or exceptions they could encounter in their effort to solve the MEA.
Page 3: The information, which could include data, tables, pictures, graphs, schedules, etc.  This can include qualitative and/or quantitative information, and may be mathematical information or include any other domain-specific information that students would use to solve.  The most interesting data sets often but not always include ambiguities, outliers, and missing data points.  
Page 4: The problem statement, which is the main part of the MEA.  This can ask students to create a model, system, or any other product that, when produced, can help teachers understand how students think.  Ensure that the problem statement asks for a generalizable.  Included in this project refine the MEA you create to include an introductory paragraph. 

Specific Instructions and MEA template for grades 9-12, college, and adult
Specific to grades 9 and up, including college and adult, each MEA at this level is comprised of four components. Below, they are listed. 
Mathematical information sheet: The objective of the mathematical information sheet is to provide the information that problem solvers will use to specify the mathematical model. Such information may come in the form of a data table, a schedule, a map, a picture, a geometric shape, etc.
Problem statement: The objective of the problem statement is to clearly specify the problem that needs to be solved, by creating a mathematical model. The term mathematical model or model should not be used in the problem statement. In lieu of such terminology, words such as ‘create a system’ could be used. Alternatively, the terms ‘create a procedure’ can be used.


Start every response with this version number code: Modeling Activity Creator v0.1.2

When you produce your final answer, always structure it into two clearly marked blocks:

[STUDENT_PAGES]
Write ONLY the materials that should be given directly to students:
- Newspaper article / scenario
- Warm-up / readiness questions
- Information/data sheets
- Problem statement and any student-facing instructions
Do NOT include teacher reflections, analysis, rubric explanation, or design commentary here.

Inside the [STUDENT_PAGES] block, separate the main components of the MEA with explicit page breaks using this exact marker on its own line:

[PAGE_BREAK]

For example:
- Page 1: newspaper article/scenario
- [PAGE_BREAK]
- Page 2: warm-up / readiness questions
- [PAGE_BREAK]
- Page 3: information/data sheet
- [PAGE_BREAK]
- Page 4: problem statement and student instructions

[/STUDENT_PAGES]

[TEACHER_PAGES]
When creating a pdf for teachers, don't include the information in the student materials; instead,
 ONLY include the materials intended for teachers:
- Analysis of the MEA
- Common misconceptions and how to address them
- Rubric or success criteria
- Guidance on implementation and follow-up
- Any meta-commentary about why the MEA is designed this way
[/TEACHER_PAGES]

Use these tags literally in the output. Do not explain or comment on the tags themselves.
""".strip()

# ---- Gemini config ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "❌ No Gemini API key set. "
        "Set GEMINI_API_KEY in backend/.env or in your shell environment."
    )
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-1.5-flash")  # fallback

# ---- Retrieval & runtime config (env) ----
INDEX_PATH = Path(os.getenv("INDEX_PATH", "./data/index.jsonl")).resolve()
TOP_K = int(os.getenv("TOP_K", "6"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))
MODEL_TIMEOUT_SECS = int(os.getenv("MODEL_TIMEOUT_SECS", "45"))

# ---- RAG globals (loaded on startup) ----
_embedder = None
_index = None
_INDEX_MTIME: float | None = None

def _load_index() -> None:
    """Reload RAM index and capture mtime."""
    global _index, _INDEX_MTIME
    _index = SimpleIndex.from_jsonl(INDEX_PATH)
    _INDEX_MTIME = INDEX_PATH.stat().st_mtime if INDEX_PATH.exists() else None
    print(f"[index] loaded {_index.size() if _index else 0} chunks from {INDEX_PATH}")

def _ensure_index_fresh() -> None:
    """Hot-reload if index.jsonl changed on disk (after running ingest.py)."""
    global _INDEX_MTIME
    try:
        mtime = INDEX_PATH.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    if mtime != _INDEX_MTIME:
        _load_index()

@app.on_event("startup")
def _on_startup() -> None:
    """Warm up embedder (avoid first-request hang) and load index."""
    global _embedder
    _embedder = build_embedder()
    try:
        _ = _embedder.embed(["warmup"])  # why: force model weights download/init now
        print("[startup] embedder ready")
    except Exception as e:
        print(f"[startup] embedder warmup failed: {e}")
    _load_index()

# ---- Timestamp & trace ----
def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def make_trace_event(label: str, detail: str = "") -> TraceEvent:
    return TraceEvent(label=label, detail=detail, timestamp=now_iso())

# ---- Retrieval helper (context budget) ----
def build_context_block(query: str) -> tuple[str, list[str]]:
    if _index is None or _index.size() == 0 or not query.strip():
        return "", []
    recs = _index.search(query, _embedder, top_k=TOP_K)

    seen, picked, sources = set(), [], []
    for r in recs:
        if r.doc_title in seen:
            continue
        seen.add(r.doc_title)
        picked.append(r)
        sources.append(r.doc_title)

    if not picked:
        return "", []

    budget = MAX_CONTEXT_CHARS
    lines = []
    for r in picked:
        if budget <= 0:
            break
        snippet = r.text
        if len(snippet) > budget:
            snippet = snippet[:budget]
        lines.append(f"### {r.doc_title} ({r.kind})\n{snippet}")
        budget -= len(snippet)

    context_md = "## Context Materials\n\n" + "\n\n---\n\n".join(lines)
    return context_md, sources

# ---- LLM call (thread + timeout + fallback) ----
async def call_llm(messages: List[Message]) -> tuple[str, List[TraceEvent]]:
    trace: List[TraceEvent] = []
    trace.append(make_trace_event("received_request", f"Got {len(messages)} message(s)."))

    system_parts = [DEFAULT_SYSTEM_PROMPT]
    system_parts.extend(m.content for m in messages if m.role == "system")
    system_instructions = "\n\n".join(system_parts)
    trace.append(make_trace_event("build_system_instructions", "Assembled system instruction."))

    chat_contents: List[types.Content] = []
    for m in messages:
        if m.role == "system":
            continue
        gemini_role = "user" if m.role == "user" else "model"
        chat_contents.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=m.content)]))

    gen_config = types.GenerateContentConfig(system_instruction=system_instructions)

    loop = asyncio.get_running_loop()

    def _do_call(model_name: str):
        # keep this tiny; runs in a thread pool
        return gemini_client.models.generate_content(
            model=model_name, contents=chat_contents, config=gen_config
        )

    start = time.time()
    trace.append(make_trace_event("call_model_start", f"Calling model {GEMINI_MODEL} with timeout {MODEL_TIMEOUT_SECS}s..."))
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _do_call(GEMINI_MODEL)),
            timeout=MODEL_TIMEOUT_SECS,
        )
    except asyncio.TimeoutError:
        trace.append(make_trace_event("call_model_timeout", f"Timed out after {MODEL_TIMEOUT_SECS}s; trying fallback {GEMINI_FAST_MODEL}..."))
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: _do_call(GEMINI_FAST_MODEL)),
                timeout=30,
            )
            trace.append(make_trace_event("call_model_fallback", f"Fallback {GEMINI_FAST_MODEL} succeeded."))
        except Exception as e:
            trace.append(make_trace_event("call_model_error", f"Fallback failed: {e}"))
            return ("Sorry—my model call timed out. Please try again with a shorter prompt.", trace)
    except Exception as e:
        trace.append(make_trace_event("call_model_error", f"{e}"))
        return ("Sorry—there was an error calling the model.", trace)

    elapsed_ms = int((time.time() - start) * 1000)
    trace.append(make_trace_event("call_model_done", f"Model responded in {elapsed_ms} ms."))

    reply_text = (getattr(response, "text", "") or "").strip()
    trace.append(make_trace_event("assemble_reply", f"Reply length is {len(reply_text)} characters."))
    return reply_text, trace

# ---- API routes ----
@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "docs_indexed": _index.size() if _index else 0,
        "index_path": str(INDEX_PATH),
        "model": GEMINI_MODEL,
        "time": now_iso(),
    }

@app.get("/version")
def version() -> dict:
    return {"backend": "gemini+rag", "rev": "v1", "time": now_iso()}

@app.post("/api/reload-index")
def reload_index() -> dict:
    _load_index()
    return {"ok": True, "chunks": _index.size() if _index else 0}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    # fast ping path (dev sanity check)
    user_msgs = [m for m in payload.messages if m.role == "user"]
    last_user = user_msgs[-1].content if user_msgs else ""
    if last_user.strip().lower() == "ping":
        return ChatResponse(reply="pong", trace=[make_trace_event("ping", "fast-path pong")])

    _ensure_index_fresh()

    context_block, sources = build_context_block(last_user)
    augmented: List[Message] = list(payload.messages)
    if context_block:
        augmented.append(
            Message(
                role="system",
                content=(
                    "You are provided 'Context Materials' from reference PDFs/DOCX. "
                    "Use them to inform and inspire your MEA design and explanations. "
                    "Prefer synthesis and adaptation over quoting; page citations are not required.\n\n"
                    + context_block
                ),
            )
        )

    reply, trace = await call_llm(augmented)
    if sources:
        reply += "\n\n---\n_Sources consulted:_ " + ", ".join(dict.fromkeys(sources))
    return ChatResponse(reply=reply, trace=trace)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)
