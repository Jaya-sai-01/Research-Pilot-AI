# Research Pilot AI 🚀

Research Pilot AI is an advanced, AI-powered academic research assistant designed to streamline the exploration, retrieval, and analysis of scientific literature. It combines automated web scraping, semantic search, vector-based indexing, and conversational AI (RAG) to help researchers find relevant papers, manage workspaces, and extract insights from academic articles.

---

## 🌟 Key Features

- **Multi-Source Academic Search**: Seamlessly search and retrieve papers from multiple repositories:
  - Open Access: arXiv, PubMed, Crossref, DOAJ, OpenAlex
  - Commercial Publishers: IEEE Xplore, ACM Digital Library (scrapers included)
- **Hybrid Search Engine**: Combines traditional keyword matching with deep semantic vector search for highly relevant results.
- **RAG-Powered Chat Assistant**: Have interactive, contextual conversations with your research library powered by state-of-the-art LLMs (via Groq) and a vector store (**ChromaDB**).
- **PDF Document Upload**: Upload your own scientific papers, automatically extract their content, and index them into your active workspace.
- **Secure Authentication**: Complete auth system with user registration, secure login, workspace management, and OTP-based password resets.
- **Workspace Isolation**: Organize your literature into separate workspaces, each with its own specific papers, indexes, and chat histories.

---

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI (Python)
- **Database**: SQLite (SQLAlchemy ORM)
- **Vector Database**: ChromaDB (Semantic Embedding & Retrieval)
- **AI Engine**: Groq SDK / LLMs
- **Libraries**: PyPDF, BeautifulSoup4, HTTPX/AIOHTTP, Pydantic, Python-Jose (JWT Auth)

### Frontend
- **Framework**: React with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **Routing & State**: React Router DOM, Custom Context Providers (Auth, Chat)

---

## 📂 Project Structure

```text
research-pilot/
├── backend/
│   ├── app/
│   │   ├── core/         # Config, Database, Security settings
│   │   ├── models/       # Database schemas (User, Paper, Workspace, Chat)
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── routers/      # FastAPI API endpoints (auth, papers, chat, etc.)
│   │   └── services/     # Business logic & APIs (LLM, Vector, Scrapers)
│   └── requirements.txt  # Python packages
├── frontend/
│   ├── src/
│   │   ├── assets/       # Static assets (images, icons)
│   │   ├── components/   # Shared UI components (Sidebar, Header, ProtectedRoute)
│   │   ├── context/      # React contexts (Auth, Chat)
│   │   ├── pages/        # Main application pages
│   │   └── services/     # API request handler
│   ├── index.html
│   ├── package.json
│   └── tailwind.config.js
└── README.md             # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Groq API Key (for LLM capabilities)

---

### Backend Setup

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # On Windows
   python -m venv venv
   .\venv\Scripts\activate

   # On macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file inside the `backend` directory:
   ```env
   DATABASE_URL=sqlite:///./research_pilot.db
   SECRET_KEY=your_jwt_secret_key_here
   GROQ_API_KEY=your_groq_api_key_here
   ```

5. **Start the backend server**:
   ```bash
   uvicorn app.main:app --reload
   ```
   The backend will be running at `http://localhost:8000`. You can access the interactive API docs at `http://localhost:8000/docs`.

---

### Frontend Setup

1. **Navigate to the frontend directory**:
   ```bash
   cd ../frontend
   ```

2. **Install node packages**:
   ```bash
   npm install
   ```

3. **Start the development server**:
   ```bash
   npm run dev
   ```
   The application will be accessible at `http://localhost:5173`.

---

## 🔒 Security & Privacy

- JWT token-based session handling.
- Salted & hashed passwords using `bcrypt`.
- Workspace isolation ensures your private papers and vectors are only searchable by you.
