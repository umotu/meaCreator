# MEA Creator Web App

An AI-powered web application for generating Model-Eliciting Activities (MEAs) and concept-based educational materials.

## Getting Started (Local Development)

This project runs as two services: a FastAPI backend (Python) and a Vite + React frontend (Node.js). Both must be running at the same time.

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm

## Start the Project

From the project root, open two terminals.

**Terminal 1 – Backend**
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload
```

Backend runs at: http://127.0.0.1:8000

**Terminal 2 – Frontend**
```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## Stop the Project

Press Ctrl + C in each terminal to stop the backend or frontend.
